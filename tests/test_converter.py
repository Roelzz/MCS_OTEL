import json
from pathlib import Path

import pytest

from converter import apply_mapping, generate_default_mapping, to_otlp_json
from models import MappingSpecification, OTELTrace
from parsers import extract_entities, parse_transcript

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TRANSCRIPT_PATH = FIXTURE_DIR / "rex_teams_transcript.json"


@pytest.fixture
def entities():
    with open(TRANSCRIPT_PATH) as f:
        content = f.read()
    t = parse_transcript(content)
    return extract_entities(t)


@pytest.fixture
def default_spec():
    return generate_default_mapping()


@pytest.fixture
def trace(entities, default_spec):
    return apply_mapping(entities, default_spec)


class TestGenerateDefaultMapping:
    def test_returns_spec(self, default_spec):
        assert isinstance(default_spec, MappingSpecification)

    def test_has_rules(self, default_spec):
        assert len(default_spec.rules) >= 4

    def test_has_root_rule(self, default_spec):
        root_rules = [r for r in default_spec.rules if r.is_root]
        assert len(root_rules) == 1

    def test_rule_ids_unique(self, default_spec):
        ids = [r.rule_id for r in default_spec.rules]
        assert len(ids) == len(set(ids))


class TestApplyMapping:
    def test_returns_trace(self, trace):
        assert isinstance(trace, OTELTrace)

    def test_has_root_span(self, trace):
        assert trace.root_span is not None

    def test_trace_has_spans(self, trace):
        assert trace.total_spans > 0

    def test_trace_id_deterministic(self, entities, default_spec):
        trace1 = apply_mapping(entities, default_spec)
        trace2 = apply_mapping(entities, default_spec)
        assert trace1.trace_id == trace2.trace_id

    def test_root_span_is_invoke_agent(self, trace):
        assert (
            "invoke_agent" in trace.root_span.name
            or trace.root_span.attributes.get("gen_ai.operation.name") == "invoke_agent"
        )

    def test_root_has_children(self, trace):
        assert len(trace.root_span.children) > 0

    def test_all_spans_have_trace_id(self, trace):
        def check(span):
            assert span.trace_id == trace.trace_id
            for child in span.children:
                check(child)

        check(trace.root_span)


class TestToOtlpJson:
    def test_returns_dict(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        assert isinstance(result, dict)

    def test_has_resource_spans(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        assert "resourceSpans" in result
        assert len(result["resourceSpans"]) == 1

    def test_has_scope_spans(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        scope_spans = result["resourceSpans"][0]["scopeSpans"]
        assert len(scope_spans) == 1

    def test_span_count_matches(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == trace.total_spans

    def test_service_name_in_resource(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        attrs = result["resourceSpans"][0]["resource"]["attributes"]
        service_attr = [a for a in attrs if a["key"] == "service.name"]
        assert len(service_attr) == 1
        assert service_attr[0]["value"]["stringValue"] == "copilot-studio"

    def test_roundtrip_json_serializable(self, trace, default_spec):
        result = to_otlp_json(trace, default_spec.service_name)
        json_str = json.dumps(result)
        parsed = json.loads(json_str)
        assert parsed == result
