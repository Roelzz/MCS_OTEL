import json
import os

import pytest

from converter import apply_mapping, generate_default_mapping
from models import OTELSpanKind
from parsers import extract_entities, parse_transcript

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "zava_expense_transcript.json")


@pytest.fixture
def zava_content():
    with open(FIXTURE_PATH) as f:
        return f.read()


@pytest.fixture
def zava_transcript(zava_content):
    return parse_transcript(zava_content)


@pytest.fixture
def zava_entities(zava_transcript):
    return extract_entities(zava_transcript)


@pytest.fixture
def zava_trace(zava_entities):
    spec = generate_default_mapping()
    return apply_mapping(zava_entities, spec)


# --- Phase 1: DynamicPlanStepBindUpdate enrichment ---


class TestBindUpdateEnrichment:
    def test_search_query_extracted(self, zava_entities):
        binds = [e for e in zava_entities if "DynamicPlanStepBindUpdate" in e.entity_id]
        search_binds = [e for e in binds if e.properties.get("search_query")]
        assert len(search_binds) >= 2
        assert "expense policy" in search_binds[0].properties["search_query"].lower()

    def test_search_keywords_extracted(self, zava_entities):
        binds = [e for e in zava_entities if "DynamicPlanStepBindUpdate" in e.entity_id]
        kw_binds = [e for e in binds if e.properties.get("search_keywords")]
        assert len(kw_binds) >= 1

    def test_arguments_json_present(self, zava_entities):
        binds = [e for e in zava_entities if "DynamicPlanStepBindUpdate" in e.entity_id]
        assert all(e.properties.get("arguments_json") for e in binds)
        # Should be valid JSON
        for e in binds:
            parsed = json.loads(e.properties["arguments_json"])
            assert isinstance(parsed, dict)

    def test_mcp_tool_name_extracted(self, zava_entities):
        binds = [e for e in zava_entities if "DynamicPlanStepBindUpdate" in e.entity_id]
        mcp_binds = [e for e in binds if e.properties.get("mcp_tool_name")]
        assert len(mcp_binds) >= 2
        tool_names = {e.properties["mcp_tool_name"] for e in mcp_binds}
        assert "create_new_expense_report" in tool_names
        assert "add_new_line_item" in tool_names


# --- Phase 2: DynamicPlanStepFinished observation enrichment ---


class TestStepFinishedEnrichment:
    def test_mcp_tool_result_extracted(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        mcp_results = [e for e in finished if e.properties.get("tool_result_text")]
        assert len(mcp_results) >= 2
        assert "SUCCESS" in mcp_results[0].properties["tool_result_text"]

    def test_tool_is_error_flag(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        mcp_results = [e for e in finished if e.properties.get("tool_is_error")]
        assert len(mcp_results) >= 1
        assert mcp_results[0].properties["tool_is_error"] == "False"

    def test_search_result_documents_extracted(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        search_results = [e for e in finished if e.properties.get("retrieval_document_count")]
        assert len(search_results) >= 1
        assert int(search_results[0].properties["retrieval_document_count"]) >= 1

    def test_retrieval_document_names(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        with_docs = [e for e in finished if e.properties.get("retrieval_document_names")]
        assert len(with_docs) >= 1
        assert "Zava Expense policy" in with_docs[0].properties["retrieval_document_names"]

    def test_connector_result_url(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        with_url = [e for e in finished if e.properties.get("connector_result_url")]
        assert len(with_url) >= 1
        assert "teams.microsoft.com" in with_url[0].properties["connector_result_url"]

    def test_hitl_responder_id(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        with_hitl = [e for e in finished if e.properties.get("hitl_responder_id")]
        assert len(with_hitl) >= 1

    def test_observation_json_present(self, zava_entities):
        finished = [e for e in zava_entities if "DynamicPlanStepFinished" in e.entity_id]
        assert all(e.properties.get("observation_json") for e in finished)


# --- Phase 3: UniversalSearchToolTraceData enrichment ---


class TestKnowledgeSearchEnrichment:
    def test_knowledge_sources(self, zava_entities):
        ks = [e for e in zava_entities if "UniversalSearchToolTraceData" in e.entity_id]
        assert len(ks) >= 2
        assert ks[0].properties.get("knowledge_sources")
        assert "," in ks[0].properties["knowledge_sources"]  # Multiple sources

    def test_knowledge_source_count(self, zava_entities):
        ks = [e for e in zava_entities if "UniversalSearchToolTraceData" in e.entity_id]
        assert int(ks[0].properties["knowledge_source_count"]) >= 2

    def test_output_knowledge_sources(self, zava_entities):
        ks = [e for e in zava_entities if "UniversalSearchToolTraceData" in e.entity_id]
        assert ks[0].properties.get("output_knowledge_sources")


# --- Phase 4: DynamicServerToolsList enrichment ---


class TestMCPToolsEnrichment:
    def test_tool_count(self, zava_entities):
        tools = [e for e in zava_entities if "DynamicServerToolsList" in e.entity_id]
        assert len(tools) >= 1
        assert tools[0].properties["tool_count"] == "8"

    def test_tool_names(self, zava_entities):
        tools = [e for e in zava_entities if "DynamicServerToolsList" in e.entity_id]
        names = tools[0].properties["tool_names"]
        assert "create_new_expense_report" in names
        assert "add_new_line_item" in names

    def test_dynamic_server_init_tracked(self, zava_entities):
        inits = [e for e in zava_entities if "DynamicServerInitialize" in e.entity_id]
        assert len(inits) >= 1


# --- Phase 5: Session context ---


class TestSessionContext:
    def test_channel_in_session_info(self, zava_transcript):
        assert zava_transcript.session_info.get("channel") == "pva-studio"

    def test_turn_index_present(self, zava_entities):
        turns = [e for e in zava_entities if e.entity_type == "turn"]
        assert len(turns) >= 1
        assert turns[0].properties.get("turn_index") == "0"


# --- Phase 6: Operation names and span kinds ---


class TestOperationNamesAndKinds:
    def test_root_span_is_agent_turn(self, zava_trace):
        assert "agent.turn" in zava_trace.root_span.name
        assert zava_trace.root_span.attributes["gen_ai.operation.name"] == "agent.turn"

    def test_root_span_kind_server(self, zava_trace):
        assert zava_trace.root_span.kind == OTELSpanKind.SERVER

    def test_chat_spans_are_client(self, zava_trace):
        chat_spans = [c for c in zava_trace.root_span.children if "gen_ai.chat" in c.name]
        assert len(chat_spans) >= 1
        for s in chat_spans:
            assert s.kind == OTELSpanKind.CLIENT

    def test_knowledge_retrieval_spans(self, zava_trace):
        def find_spans(span, name_part):
            found = []
            if name_part in span.name:
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child, name_part))
            return found

        kr_spans = find_spans(zava_trace.root_span, "knowledge.retrieval")
        assert len(kr_spans) >= 1
        for s in kr_spans:
            assert s.attributes["gen_ai.operation.name"] == "knowledge.retrieval"
            assert s.kind == OTELSpanKind.CLIENT

    def test_tool_execute_spans(self, zava_trace):
        def find_spans(span, op_name):
            found = []
            if span.attributes.get("gen_ai.operation.name") == op_name:
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child, op_name))
            return found

        tool_spans = find_spans(zava_trace.root_span, "tool.execute")
        assert len(tool_spans) >= 1
        for s in tool_spans:
            assert s.kind == OTELSpanKind.CLIENT


# --- Integration: Full trace richness ---


class TestTraceRichness:
    def test_total_span_count(self, zava_trace):
        assert zava_trace.total_spans >= 10

    def test_mcp_tool_results_in_spans(self, zava_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("gen_ai.tool.call.result"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        result_spans = find_spans(zava_trace.root_span)
        assert len(result_spans) >= 1
        assert "SUCCESS" in result_spans[0].attributes["gen_ai.tool.call.result"]

    def test_search_query_in_spans(self, zava_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("gen_ai.retrieval.query.text"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        query_spans = find_spans(zava_trace.root_span)
        assert len(query_spans) >= 1

    def test_tool_arguments_in_spans(self, zava_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("gen_ai.tool.call.arguments"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        arg_spans = find_spans(zava_trace.root_span)
        assert len(arg_spans) >= 1
        # Arguments should be valid JSON
        for s in arg_spans:
            parsed = json.loads(s.attributes["gen_ai.tool.call.arguments"])
            assert isinstance(parsed, dict)

    def test_mcp_tool_count_in_spans(self, zava_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("copilot_studio.mcp_tool_count"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        mcp_spans = find_spans(zava_trace.root_span)
        assert len(mcp_spans) >= 1
        assert mcp_spans[0].attributes["copilot_studio.mcp_tool_count"] == "8"
