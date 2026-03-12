import json
import os

import pytest

from converter import apply_mapping, generate_default_mapping
from models import OTELSpanKind
from parsers import extract_entities, parse_transcript

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "zava_expense_transcript.json")
REX_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "rex_teams_transcript.json")
PVA_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "pva_studio_transcript.json")


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
        # First turn has index "0" (greeting) or "0" (first user turn if no greeting)
        assert turns[0].properties.get("turn_index") is not None


# --- Phase 6: Operation names and span kinds ---


class TestOperationNamesAndKinds:
    def test_root_span_is_invoke_agent(self, zava_trace):
        assert "invoke_agent" in zava_trace.root_span.name
        assert zava_trace.root_span.attributes["gen_ai.operation.name"] == "invoke_agent"

    def test_root_span_kind_server(self, zava_trace):
        assert zava_trace.root_span.kind == OTELSpanKind.SERVER

    def test_chat_spans_are_client(self, zava_trace):
        chat_spans = [c for c in zava_trace.root_span.children if "chat" in c.name]
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

        tool_spans = find_spans(zava_trace.root_span, "execute_tool")
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
            if span.attributes.get("mcs.mcp.tool_count"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        mcp_spans = find_spans(zava_trace.root_span)
        assert len(mcp_spans) >= 1
        assert mcp_spans[0].attributes["mcs.mcp.tool_count"] == "8"


# --- Multi-format fixtures ---


@pytest.fixture
def rex_content():
    with open(REX_FIXTURE_PATH) as f:
        return f.read()


@pytest.fixture
def rex_transcript(rex_content):
    return parse_transcript(rex_content)


@pytest.fixture
def rex_entities(rex_transcript):
    return extract_entities(rex_transcript)


@pytest.fixture
def rex_trace(rex_entities):
    spec = generate_default_mapping()
    return apply_mapping(rex_entities, spec)


@pytest.fixture
def pva_content():
    with open(PVA_FIXTURE_PATH) as f:
        return f.read()


@pytest.fixture
def pva_transcript(pva_content):
    return parse_transcript(pva_content)


@pytest.fixture
def pva_entities(pva_transcript):
    return extract_entities(pva_transcript)


@pytest.fixture
def pva_trace(pva_entities):
    spec = generate_default_mapping()
    return apply_mapping(pva_entities, spec)


# --- Fix 2: No SessionInfo fallback ---


class TestNoSessionInfo:
    def test_pva_has_no_session_info_outcome(self, pva_transcript):
        assert "outcome" not in pva_transcript.session_info

    def test_pva_still_produces_root_entity(self, pva_entities):
        roots = [e for e in pva_entities if e.entity_id == "session_root"]
        assert len(roots) == 1
        assert roots[0].properties["outcome"] == "Unknown"
        assert roots[0].properties["bot_name"] == "Troubleshoot_bluebot"

    def test_pva_root_span_is_invoke_agent(self, pva_trace):
        assert pva_trace.root_span.attributes["gen_ai.operation.name"] == "invoke_agent"
        assert pva_trace.root_span.kind == OTELSpanKind.SERVER

    def test_pva_conversation_id_in_root(self, pva_entities):
        root = [e for e in pva_entities if e.entity_id == "session_root"][0]
        assert root.properties["conversation_id"] == "pva-conv-001"


# --- Improvement 4: DynamicPlanReceived enrichment ---


class TestPlanReceivedEnrichment:
    def test_step_count_extracted(self, pva_entities):
        plans = [e for e in pva_entities if "DynamicPlanReceived_" in e.entity_id]
        assert len(plans) >= 1
        assert plans[0].properties["step_count"] == "1"

    def test_is_final_plan_extracted(self, pva_entities):
        plans = [e for e in pva_entities if "DynamicPlanReceived_" in e.entity_id]
        assert plans[0].properties["is_final_plan"] == "False"

    def test_tool_definition_count(self, pva_entities):
        plans = [e for e in pva_entities if "DynamicPlanReceived_" in e.entity_id]
        assert plans[0].properties["tool_definition_count"] == "1"

    def test_plan_step_count_in_span(self, pva_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("mcs.plan.step_count"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        plan_spans = find_spans(pva_trace.root_span)
        assert len(plan_spans) >= 1
        assert plan_spans[0].attributes["mcs.plan.step_count"] == "1"


# --- Improvement 5: DynamicPlanReceivedDebug enrichment ---


class TestPlanReceivedDebugEnrichment:
    def test_user_ask_extracted(self, pva_entities):
        debugs = [e for e in pva_entities if "DynamicPlanReceivedDebug" in e.entity_id]
        assert len(debugs) >= 1
        assert debugs[0].properties["user_ask"] == "trigger topic"

    def test_user_ask_in_span(self, pva_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("mcs.orchestrator.user_ask"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        debug_spans = find_spans(pva_trace.root_span)
        assert len(debug_spans) >= 1
        assert debug_spans[0].attributes["mcs.orchestrator.user_ask"] == "trigger topic"


# --- Improvement 6: DialogTracingInfo enrichment ---


class TestDialogTracingInfoEnrichment:
    def test_action_count_extracted(self, pva_entities):
        dialogs = [e for e in pva_entities if "DialogTracingInfo" in e.entity_id]
        assert len(dialogs) >= 1
        # Second DialogTracingInfo has 3 actions
        multi_action = [e for e in dialogs if e.properties.get("action_count") == "3"]
        assert len(multi_action) >= 1

    def test_action_types_extracted(self, pva_entities):
        dialogs = [e for e in pva_entities if "DialogTracingInfo" in e.entity_id]
        multi = [e for e in dialogs if e.properties.get("action_count") == "3"][0]
        assert "SetVariable" in multi.properties["action_types"]
        assert "HttpRequest" in multi.properties["action_types"]
        assert "SendActivity" in multi.properties["action_types"]

    def test_topic_ids_extracted(self, pva_entities):
        dialogs = [e for e in pva_entities if "DialogTracingInfo" in e.entity_id]
        multi = [e for e in dialogs if e.properties.get("action_count") == "3"][0]
        assert "copilots_header_21961.topic.Trigger" in multi.properties["topic_ids"]
        assert "copilots_header_21961.topic.Fallback" in multi.properties["topic_ids"]

    def test_exceptions_extracted(self, pva_entities):
        dialogs = [e for e in pva_entities if "DialogTracingInfo" in e.entity_id]
        multi = [e for e in dialogs if e.properties.get("action_count") == "3"][0]
        assert "Connection timeout" in multi.properties["dialog_exceptions"]

    def test_dialog_tracing_span_has_action_types(self, pva_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("mcs.dialog.action_types"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        dialog_spans = find_spans(pva_trace.root_span)
        assert len(dialog_spans) >= 1


# --- Fix 3: DynamicPlanStepTriggered mapping ---


class TestPlanStepTriggeredMapping:
    def test_thought_in_span(self, pva_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("mcs.orchestrator.thought"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        thought_spans = find_spans(pva_trace.root_span)
        assert len(thought_spans) >= 1
        assert "initiate the requested topic" in thought_spans[0].attributes["mcs.orchestrator.thought"]

    def test_step_type_in_span(self, pva_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("mcs.step.type"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        type_spans = find_spans(pva_trace.root_span)
        assert len(type_spans) >= 1
        assert type_spans[0].attributes["mcs.step.type"] == "CustomTopic"


# --- Multi-format traces ---


class TestMultiFormatTraces:
    def test_rex_has_session_info(self, rex_transcript):
        assert rex_transcript.session_info.get("outcome") == "Resolved"

    def test_rex_root_span_is_invoke_agent(self, rex_trace):
        assert rex_trace.root_span.attributes["gen_ai.operation.name"] == "invoke_agent"
        assert rex_trace.root_span.kind == OTELSpanKind.SERVER

    def test_rex_has_channel_msteams(self, rex_transcript):
        assert rex_transcript.session_info.get("channel") == "msteams"

    def test_rex_has_tenant(self, rex_transcript):
        assert rex_transcript.session_info.get("tenant") == "tenant-abc-123"

    def test_rex_bot_name_in_root(self, rex_entities):
        root = [e for e in rex_entities if e.entity_id == "session_root"][0]
        assert root.properties["bot_name"] == "Rex Bluebot"

    def test_pva_and_rex_both_valid_traces(self, pva_trace, rex_trace):
        assert pva_trace.total_spans >= 3
        assert rex_trace.total_spans >= 3
        assert pva_trace.root_span.attributes["gen_ai.operation.name"] == "invoke_agent"
        assert rex_trace.root_span.attributes["gen_ai.operation.name"] == "invoke_agent"

    def test_rex_thought_in_span(self, rex_trace):
        def find_spans(span):
            found = []
            if span.attributes.get("mcs.orchestrator.thought"):
                found.append(span)
            for child in span.children:
                found.extend(find_spans(child))
            return found

        thought_spans = find_spans(rex_trace.root_span)
        assert len(thought_spans) >= 1
        assert "refund" in thought_spans[0].attributes["mcs.orchestrator.thought"].lower()
