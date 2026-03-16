"""Tests for config_loader: load/save MappingSpecification from JSON."""

from pathlib import Path

import pytest

from config_loader import (
    DEFAULT_MAPPING_PATH,
    load_default_mapping,
    load_mapping_spec,
    save_mapping_spec,
    validate_mapping_spec,
)
from converter import apply_mapping
from models import (
    AttributeMapping,
    EventMetadata,
    EnrichmentRule,
    MappingSpecification,
    OTELOperationName,
    SpanMappingRule,
)
from parsers import extract_entities, parse_transcript


class TestLoadDefaultMapping:
    def test_loads_successfully(self):
        spec = load_default_mapping()
        assert isinstance(spec, MappingSpecification)

    def test_has_rules(self):
        spec = load_default_mapping()
        assert len(spec.rules) == 28

    def test_has_event_metadata(self):
        spec = load_default_mapping()
        assert len(spec.event_metadata) == 28

    def test_has_enrichment_rules(self):
        spec = load_default_mapping()
        assert len(spec.enrichment_rules) == 16

    def test_rule_ids_unique(self):
        spec = load_default_mapping()
        ids = [r.rule_id for r in spec.rules]
        assert len(ids) == len(set(ids))

    def test_has_root_rule(self):
        spec = load_default_mapping()
        root_rules = [r for r in spec.rules if r.is_root]
        assert len(root_rules) == 1

    def test_event_metadata_all_tracked(self):
        spec = load_default_mapping()
        assert all(em.tracked for em in spec.event_metadata)

    def test_event_metadata_has_labels(self):
        spec = load_default_mapping()
        labeled = [em for em in spec.event_metadata if em.label]
        assert len(labeled) == len(spec.event_metadata)


class TestLoadMappingSpec:
    def test_loads_default_path(self):
        spec = load_mapping_spec(DEFAULT_MAPPING_PATH)
        assert isinstance(spec, MappingSpecification)
        assert len(spec.rules) == 28

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_mapping_spec(tmp_path / "nonexistent.json")


class TestSaveMappingSpec:
    def test_round_trip(self, tmp_path):
        spec = load_default_mapping()
        out_path = tmp_path / "test_spec.json"
        save_mapping_spec(spec, out_path)

        loaded = load_mapping_spec(out_path)
        assert len(loaded.rules) == len(spec.rules)
        assert len(loaded.event_metadata) == len(spec.event_metadata)
        assert len(loaded.enrichment_rules) == len(spec.enrichment_rules)

    def test_creates_parent_dirs(self, tmp_path):
        out_path = tmp_path / "nested" / "dir" / "spec.json"
        spec = MappingSpecification(rules=[])
        save_mapping_spec(spec, out_path)
        assert out_path.exists()


class TestMissingFile:
    def test_raises_when_no_json(self, tmp_path, monkeypatch):
        """When default_mapping.json is missing, load_default_mapping raises."""
        monkeypatch.setattr("config_loader.DEFAULT_MAPPING_PATH", tmp_path / "missing.json")
        with pytest.raises(FileNotFoundError):
            load_default_mapping()


class TestValidateMappingSpec:
    def test_valid_spec(self):
        spec = load_default_mapping()
        issues = validate_mapping_spec(spec)
        assert issues == []

    def test_duplicate_rule_id(self):
        spec = load_default_mapping()
        dup = spec.rules[0].model_copy()
        spec.rules.append(dup)
        issues = validate_mapping_spec(spec)
        assert any("Duplicate rule_id" in i for i in issues)

    def test_bad_parent_ref(self):
        spec = MappingSpecification(
            rules=[
                SpanMappingRule(
                    rule_id="child",
                    mcs_entity_type="trace_event",
                    otel_operation_name=OTELOperationName.chain,
                    parent_rule_id="nonexistent",
                )
            ]
        )
        issues = validate_mapping_spec(spec)
        assert any("nonexistent" in i for i in issues)

    def test_unknown_enrichment_op(self):
        from models import EnrichmentOp
        spec = MappingSpecification(
            enrichment_rules=[
                EnrichmentRule(
                    value_type="Test",
                    derived_fields=[EnrichmentOp(target="x", op="bogus_op", source="y")]
                )
            ]
        )
        issues = validate_mapping_spec(spec)
        assert any("bogus_op" in i for i in issues)


class TestConfigOnlySmokeTest:
    def test_add_event_type_via_json_only(self):
        """Add a dummy event type purely through JSON config - zero Python changes."""
        spec = load_default_mapping()

        # Add new event metadata
        spec.event_metadata.append(EventMetadata(
            value_type="TestSmokeEvent",
            tracked=True,
            label="Smoke Test",
            entity_type="trace_event",
        ))

        # Add new mapping rule
        spec.rules.append(SpanMappingRule(
            rule_id="smoke_test",
            rule_name="Smoke Test Event",
            mcs_entity_type="trace_event",
            mcs_value_type="TestSmokeEvent",
            otel_operation_name=OTELOperationName.chain,
            span_name_template="chain smoke_test",
            parent_rule_id="user_turn",
            attribute_mappings=[
                AttributeMapping(
                    mcs_property="testProp",
                    otel_attribute="mcs.test.prop",
                ),
            ],
        ))

        # Create a minimal transcript with the new event type
        import json
        transcript_json = json.dumps([
            {"type": "trace", "timestamp": 1710000000000, "from": {"role": 0},
             "valueType": "SessionInfo", "value": {"outcome": "Resolved", "type": "Test"}},
            {"type": "message", "timestamp": 1710000001000, "from": {"role": 1, "name": "User"},
             "text": "hello"},
            {"type": "message", "timestamp": 1710000002000, "from": {"role": 0, "name": "Bot"},
             "text": "hi there"},
            {"type": "trace", "timestamp": 1710000003000, "from": {"role": 0},
             "valueType": "TestSmokeEvent", "value": {"testProp": "smokeValue"}},
        ])

        t = parse_transcript(transcript_json)
        entities = extract_entities(t, spec=spec)

        # Verify the new entity appears
        smoke_entities = [e for e in entities if e.value_type == "TestSmokeEvent"]
        assert len(smoke_entities) == 1
        assert smoke_entities[0].properties["testProp"] == "smokeValue"

        # Verify it produces OTEL output
        trace = apply_mapping(entities, spec)
        assert trace.total_spans > 0

        # Find the smoke test span
        def find_span(span, name_part):
            if name_part in span.name:
                return span
            for child in span.children:
                found = find_span(child, name_part)
                if found:
                    return found
            return None

        smoke_span = find_span(trace.root_span, "smoke_test")
        assert smoke_span is not None
        assert smoke_span.attributes.get("mcs.test.prop") == "smokeValue"
