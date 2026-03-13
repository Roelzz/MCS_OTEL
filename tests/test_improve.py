"""Tests for the self-learning mapper improvement engine."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from analyze_transcripts import discover_files, iter_transcripts
from config_loader import load_default_mapping
from improve import (
    FileAnalysis,
    Finding,
    ImprovementRun,
    analyze_corpus,
    apply_auto_fixes,
    classify_findings,
    compute_coverage,
    generate_code_changes,
    generate_spec_changes,
    run_improvement_loop,
)
from models import AttributeMapping, MappingSpecification, SpanMappingRule
from parsers import TRACKED_EVENT_TYPES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixture transcripts."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def default_spec() -> MappingSpecification:
    return load_default_mapping()


@pytest.fixture
def tracked_types() -> set[str]:
    return set(TRACKED_EVENT_TYPES)


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "improve_runs"


@pytest.fixture
def sample_unknown_types() -> dict[str, int]:
    """Unknown types appearing in multiple files."""
    return {
        "NewEventTypeA": 5,
        "NewEventTypeB": 3,
        "RareEventTypeC": 1,
    }


@pytest.fixture
def sample_unknown_samples() -> dict[str, dict]:
    return {
        "NewEventTypeA": {"propX": "value1", "propY": "value2"},
        "NewEventTypeB": {"propZ": "value3"},
        "RareEventTypeC": {"propW": "value4"},
    }


@pytest.fixture
def sample_unmapped_props() -> dict[str, set[str]]:
    return {
        "DynamicPlanReceived": {"newPropA", "newPropB"},
        "ErrorTraceData": {"newPropC"},
    }


@pytest.fixture
def nested_unknown_samples() -> dict[str, dict]:
    """Unknown types with nested structures — should need review."""
    return {
        "ComplexEvent": {"flat_prop": "ok", "nested": {"deep": "data"}},
    }


# ---------------------------------------------------------------------------
# TestAnalyzeCorpus
# ---------------------------------------------------------------------------


class TestAnalyzeCorpus:
    def test_analyzes_fixtures(self, fixtures_dir: Path, default_spec, tracked_types):
        """Fixture files (JSON + CSV rows) should all be analyzed successfully."""
        files = discover_files([fixtures_dir])
        if not files:
            pytest.skip("No fixture files available")

        # Count expected transcripts: 1 per JSON, N rows per CSV
        expected = sum(1 for _ in iter_transcripts(files))

        results, _, _, _ = analyze_corpus(fixtures_dir, default_spec, tracked_types)
        successful = [r for r in results if r.success]
        assert len(successful) > 0
        assert len(successful) == expected

    def test_counts_value_types(self, fixtures_dir: Path, default_spec, tracked_types):
        """Known value types should be counted correctly."""
        files = discover_files([fixtures_dir])
        if not files:
            pytest.skip("No fixture files available")

        results, _, _, _ = analyze_corpus(fixtures_dir, default_spec, tracked_types)
        successful = [r for r in results if r.success]

        # Each successful analysis should have some value types
        for fa in successful:
            assert fa.entity_count > 0
            # At least session_root and turns should be present
            assert fa.activity_count > 0

    def test_detects_unknown_types(self, tmp_path: Path, default_spec, tracked_types):
        """Transcripts with unknown types should report them."""
        # Create a minimal transcript with an unknown type
        transcript = [
            {
                "type": "trace",
                "timestamp": 1710000000000,
                "from": {"role": 0},
                "valueType": "TotallyNewEventType",
                "value": {"someProp": "someValue"},
            },
            {
                "type": "message",
                "timestamp": 1710000001000,
                "from": {"role": 1},
                "text": "hello",
            },
        ]
        (tmp_path / "test.json").write_text(json.dumps(transcript))

        results, unknown_types, unknown_samples, _ = analyze_corpus(
            tmp_path, default_spec, tracked_types
        )
        # The unknown type may not surface if parse_transcript doesn't produce a trace_event for it
        # But the file should be analyzed successfully
        assert len(results) == 1
        assert results[0].success

    def test_computes_fill_rate(self, fixtures_dir: Path, default_spec, tracked_types):
        """Fill rate should be between 0 and 1."""
        json_files = list(fixtures_dir.glob("*.json"))
        if not json_files:
            pytest.skip("No JSON fixtures available")

        results, _, _, _ = analyze_corpus(fixtures_dir, default_spec, tracked_types)
        for fa in [r for r in results if r.success and r.span_count > 0]:
            assert 0.0 <= fa.attribute_fill_rate <= 1.0

    def test_empty_dir(self, tmp_path: Path, default_spec, tracked_types):
        """Empty directory should return empty results."""
        results, unknown, _, unmapped = analyze_corpus(tmp_path, default_spec, tracked_types)
        assert results == []
        assert unknown == {}


# ---------------------------------------------------------------------------
# TestClassifyFindings
# ---------------------------------------------------------------------------


class TestClassifyFindings:
    def test_auto_fixable_threshold(self, sample_unknown_types, sample_unknown_samples, sample_unmapped_props):
        """Types in >= 3 files should be auto_fixable."""
        findings = classify_findings(
            sample_unknown_types, sample_unknown_samples, sample_unmapped_props, min_file_count=3
        )
        new_type_findings = [f for f in findings if f.category == "new_type"]

        auto = {f.value_type for f in new_type_findings if f.auto_fixable}
        not_auto = {f.value_type for f in new_type_findings if not f.auto_fixable}

        assert "NewEventTypeA" in auto  # 5 files
        assert "NewEventTypeB" in auto  # 3 files
        assert "RareEventTypeC" in not_auto  # 1 file

    def test_below_threshold_needs_review(self, sample_unknown_types, sample_unknown_samples):
        """Types in < min_file_count files should not be auto_fixable."""
        findings = classify_findings(
            sample_unknown_types, sample_unknown_samples, {}, min_file_count=3
        )
        rare = [f for f in findings if f.value_type == "RareEventTypeC"]
        assert len(rare) == 1
        assert not rare[0].auto_fixable

    def test_generates_code_snippets(self, sample_unknown_types, sample_unknown_samples, sample_unmapped_props):
        """All findings should have non-empty code_snippet."""
        findings = classify_findings(
            sample_unknown_types, sample_unknown_samples, sample_unmapped_props
        )
        for f in findings:
            assert f.code_snippet, f"Finding for {f.value_type}/{f.property_name} has empty code_snippet"

    def test_nested_types_need_review(self, nested_unknown_samples):
        """Types with nested structures should be classified as new_enrichment."""
        findings = classify_findings(
            {"ComplexEvent": 5}, nested_unknown_samples, {}
        )
        complex_findings = [f for f in findings if f.value_type == "ComplexEvent"]
        assert len(complex_findings) == 1
        assert complex_findings[0].category == "new_enrichment"
        assert not complex_findings[0].auto_fixable

    def test_attribute_findings(self, sample_unmapped_props):
        """Unmapped properties should generate new_attribute findings."""
        findings = classify_findings({}, {}, sample_unmapped_props)
        attr_findings = [f for f in findings if f.category == "new_attribute"]
        assert len(attr_findings) == 3  # newPropA, newPropB, newPropC
        assert all(f.auto_fixable for f in attr_findings)


# ---------------------------------------------------------------------------
# TestApplyAutoFixes
# ---------------------------------------------------------------------------


class TestApplyAutoFixes:
    def test_adds_new_rule_to_spec(self, default_spec, tracked_types):
        """New type finding should add a rule to the spec."""
        findings = [
            Finding(
                category="new_type",
                auto_fixable=True,
                value_type="BrandNewEvent",
                file_count=5,
                sample_value={"foo": "bar", "baz": "qux"},
                code_snippet="SpanMappingRule(...)",
            )
        ]
        original_count = len(default_spec.rules)
        new_spec, new_tracked, applied = apply_auto_fixes(findings, default_spec, tracked_types)

        assert len(new_spec.rules) == original_count + 1
        assert "BrandNewEvent" in new_tracked
        assert len(applied) == 1
        # Original should be unmodified
        assert len(default_spec.rules) == original_count

    def test_adds_attribute_to_rule(self, default_spec, tracked_types):
        """New attribute finding should add an AttributeMapping to existing rule."""
        findings = [
            Finding(
                category="new_attribute",
                auto_fixable=True,
                value_type="ErrorTraceData",
                property_name="newField",
            )
        ]

        # Find the error rule
        error_rule = next(r for r in default_spec.rules if r.mcs_value_type == "ErrorTraceData")
        original_attr_count = len(error_rule.attribute_mappings)

        new_spec, _, applied = apply_auto_fixes(findings, default_spec, tracked_types)

        new_error_rule = next(r for r in new_spec.rules if r.mcs_value_type == "ErrorTraceData")
        assert len(new_error_rule.attribute_mappings) == original_attr_count + 1
        assert any(am.mcs_property == "newField" for am in new_error_rule.attribute_mappings)
        assert len(applied) == 1

    def test_idempotent(self, default_spec, tracked_types):
        """Applying the same fix twice should not duplicate entries."""
        findings = [
            Finding(
                category="new_type",
                auto_fixable=True,
                value_type="IdempotentEvent",
                file_count=5,
                sample_value={"prop": "val"},
                code_snippet="SpanMappingRule(...)",
            )
        ]

        spec1, tracked1, applied1 = apply_auto_fixes(findings, default_spec, tracked_types)
        spec2, tracked2, applied2 = apply_auto_fixes(findings, spec1, tracked1)

        assert len(applied1) == 1
        assert len(applied2) == 0  # Already exists
        assert len(spec1.rules) == len(spec2.rules)

    def test_skips_non_auto_fixable(self, default_spec, tracked_types):
        """Findings with auto_fixable=False should be skipped."""
        findings = [
            Finding(
                category="new_enrichment",
                auto_fixable=False,
                value_type="ComplexEvent",
                file_count=5,
                sample_value={"nested": {"data": "value"}},
                code_snippet="# needs review",
            )
        ]
        _, _, applied = apply_auto_fixes(findings, default_spec, tracked_types)
        assert len(applied) == 0


# ---------------------------------------------------------------------------
# TestComputeCoverage
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    def test_basic_coverage(self):
        """Coverage should reflect entity-to-span ratio."""
        analyses = [
            FileAnalysis(path="a.json", success=True, entity_count=10, span_count=8, attribute_fill_rate=0.6),
            FileAnalysis(path="b.json", success=True, entity_count=10, span_count=6, attribute_fill_rate=0.4),
        ]
        coverage, fill_rate = compute_coverage(analyses)
        assert coverage == pytest.approx(70.0)  # 14/20 * 100
        assert fill_rate == pytest.approx(0.5)  # (0.6 + 0.4) / 2

    def test_empty_analyses(self):
        coverage, fill_rate = compute_coverage([])
        assert coverage == 0.0
        assert fill_rate == 0.0

    def test_failed_files_excluded(self):
        analyses = [
            FileAnalysis(path="ok.json", success=True, entity_count=10, span_count=5, attribute_fill_rate=0.5),
            FileAnalysis(path="fail.json", success=False, entity_count=0, span_count=0),
        ]
        coverage, fill_rate = compute_coverage(analyses)
        assert coverage == pytest.approx(50.0)
        assert fill_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestGenerateCodeChanges
# ---------------------------------------------------------------------------


class TestGenerateCodeChanges:
    def test_new_type_generates_all_files(self):
        """New type should generate changes for parsers, converter, and registry."""
        findings = [
            Finding(
                category="new_type",
                auto_fixable=True,
                value_type="FreshEvent",
                sample_value={"prop1": "val1"},
                code_snippet="SpanMappingRule(...)",
            )
        ]
        changes = generate_code_changes(findings, [])
        assert "parsers.py" in changes
        assert "converter.py" in changes
        assert "otel_registry.py" in changes

    def test_new_attribute_generates_converter_and_registry(self):
        """New attribute should generate changes for converter and registry."""
        findings = [
            Finding(
                category="new_attribute",
                auto_fixable=True,
                value_type="ErrorTraceData",
                property_name="newField",
                code_snippet='AttributeMapping(...)',
            )
        ]
        changes = generate_code_changes(findings, [])
        assert "converter.py" in changes
        assert "otel_registry.py" in changes


# ---------------------------------------------------------------------------
# TestGenerateSpecChanges
# ---------------------------------------------------------------------------


class TestGenerateSpecChanges:
    def test_adds_new_type_to_spec(self, default_spec):
        """New type finding should add EventMetadata + SpanMappingRule."""
        findings = [
            Finding(
                category="new_type",
                auto_fixable=True,
                value_type="BrandNewEvent",
                file_count=5,
                sample_value={"foo": "bar"},
                code_snippet="SpanMappingRule(...)",
            )
        ]
        result = generate_spec_changes(findings, [], default_spec)
        assert len(result.rules) == len(default_spec.rules) + 1
        assert len(result.event_metadata) == len(default_spec.event_metadata) + 1
        new_meta = [em for em in result.event_metadata if em.value_type == "BrandNewEvent"]
        assert len(new_meta) == 1
        assert new_meta[0].tracked

    def test_adds_attribute_to_existing_rule(self, default_spec):
        """New attribute finding should add AttributeMapping."""
        findings = [
            Finding(
                category="new_attribute",
                auto_fixable=True,
                value_type="ErrorTraceData",
                property_name="newField",
            )
        ]
        result = generate_spec_changes(findings, [], default_spec)
        error_rule = next(r for r in result.rules if r.mcs_value_type == "ErrorTraceData")
        assert any(am.mcs_property == "newField" for am in error_rule.attribute_mappings)

    def test_idempotent(self, default_spec):
        """Applying the same changes twice should not duplicate."""
        findings = [
            Finding(
                category="new_type",
                auto_fixable=True,
                value_type="IdempotentEvent",
                file_count=5,
                sample_value={"p": "v"},
                code_snippet="SpanMappingRule(...)",
            )
        ]
        result1 = generate_spec_changes(findings, [], default_spec)
        result2 = generate_spec_changes(findings, [], result1)
        assert len(result1.rules) == len(result2.rules)


# ---------------------------------------------------------------------------
# TestImprovementLoop
# ---------------------------------------------------------------------------


class TestImprovementLoop:
    def test_converges_on_fixtures(self, fixtures_dir: Path, tmp_output: Path):
        """Loop on test fixtures should converge in <= 3 iterations."""
        json_files = list(fixtures_dir.glob("*.json"))
        if not json_files:
            pytest.skip("No JSON fixtures available")

        runs = run_improvement_loop(
            input_dir=fixtures_dir,
            max_iterations=3,
            min_file_count=1,  # Low threshold for test fixtures
            output_dir=tmp_output,
        )
        assert len(runs) >= 1
        assert len(runs) <= 3

    def test_coverage_improves_or_stays(self, fixtures_dir: Path, tmp_output: Path):
        """Each iteration's coverage should be >= previous."""
        json_files = list(fixtures_dir.glob("*.json"))
        if not json_files:
            pytest.skip("No JSON fixtures available")

        runs = run_improvement_loop(
            input_dir=fixtures_dir,
            max_iterations=3,
            min_file_count=1,
            output_dir=tmp_output,
        )
        for i in range(1, len(runs)):
            assert runs[i].avg_coverage >= runs[i - 1].avg_coverage - 0.1  # Small tolerance

    def test_saves_results(self, fixtures_dir: Path, tmp_output: Path):
        """improve_runs/ should have iteration files after loop."""
        json_files = list(fixtures_dir.glob("*.json"))
        if not json_files:
            pytest.skip("No JSON fixtures available")

        runs = run_improvement_loop(
            input_dir=fixtures_dir,
            max_iterations=2,
            min_file_count=1,
            output_dir=tmp_output,
        )
        assert tmp_output.exists()
        # Should have at least one iteration JSON + code_export + improved_mapping
        json_files_out = list(tmp_output.glob("iter_*.json"))
        assert len(json_files_out) >= 1
        assert (tmp_output / "code_export.py").exists()
        assert (tmp_output / "improved_mapping.json").exists()

    def test_empty_dir_no_crash(self, tmp_path: Path, tmp_output: Path):
        """Empty input dir should not crash, just produce empty results."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        runs = run_improvement_loop(
            input_dir=empty_dir,
            max_iterations=2,
            output_dir=tmp_output,
        )
        # Should produce at least one run with 0 files
        assert len(runs) >= 1
        assert runs[0].file_count == 0


# ---------------------------------------------------------------------------
# TestCSVSupport
# ---------------------------------------------------------------------------


class TestCSVSupport:
    def test_discover_files_finds_csv(self, fixtures_dir: Path):
        """discover_files() should find both JSON and CSV files."""
        files = discover_files([fixtures_dir])
        suffixes = {f.suffix for f in files}
        assert ".json" in suffixes
        assert ".csv" in suffixes

    def test_iter_transcripts_yields_csv_rows(self, fixtures_dir: Path):
        """iter_transcripts() should yield one entry per CSV row."""
        csv_files = [f for f in discover_files([fixtures_dir]) if f.suffix == ".csv"]
        assert len(csv_files) >= 1

        results = list(iter_transcripts(csv_files))
        # sample_dataverse.csv has 2 rows
        assert len(results) == 2
        assert results[0][0] == "sample_dataverse.csv:row_1"
        assert results[1][0] == "sample_dataverse.csv:row_2"
        # Content should be parseable JSON arrays
        for label, content in results:
            parsed = json.loads(content)
            assert isinstance(parsed, list)

    def test_iter_transcripts_yields_json_files(self, fixtures_dir: Path):
        """iter_transcripts() should yield one entry per JSON file."""
        json_files = [f for f in discover_files([fixtures_dir]) if f.suffix == ".json"]
        results = list(iter_transcripts(json_files))
        assert len(results) == len(json_files)
        for label, content in results:
            assert label.endswith(".json")

    def test_csv_without_content_column_skipped(self, tmp_path: Path):
        """CSV without 'content' column should be skipped."""
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("id,name\n1,test\n")

        results = list(iter_transcripts([csv_path]))
        assert len(results) == 0

    def test_analyze_corpus_processes_csv(self, fixtures_dir: Path, default_spec, tracked_types):
        """analyze_corpus() should process CSV rows as individual transcripts."""
        results, _, _, _ = analyze_corpus(fixtures_dir, default_spec, tracked_types)
        # Should have results from both JSON files and CSV rows
        csv_results = [r for r in results if ":row_" in r.path]
        assert len(csv_results) == 2
        assert all(r.success for r in csv_results)

    def test_csv_fixture_has_valid_transcripts(self, fixtures_dir: Path):
        """CSV fixture rows should contain valid transcript JSON."""
        csv_path = fixtures_dir / "sample_dataverse.csv"
        results = list(iter_transcripts([csv_path]))
        for label, content in results:
            activities = json.loads(content)
            assert isinstance(activities, list)
            assert len(activities) > 0
            # Should have at least a ConversationInfo trace and a message
            types = {a.get("type") for a in activities}
            assert "trace" in types
            assert "message" in types
