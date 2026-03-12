from pydantic import BaseModel


class OTELAttribute(BaseModel):
    key: str
    value_type: str
    description: str
    requirement_level: str = "recommended"
    example_value: str = ""


GENERAL_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.operation.name",
        value_type="string",
        description="Name of the GenAI operation (chat, invoke_agent, etc.)",
        requirement_level="required",
        example_value="chat",
    ),
    OTELAttribute(
        key="gen_ai.system",
        value_type="string",
        description="GenAI system provider identifier",
        requirement_level="required",
        example_value="copilot_studio",
    ),
    OTELAttribute(
        key="gen_ai.provider.name",
        value_type="string",
        description="Human-readable name of the GenAI provider",
        requirement_level="recommended",
        example_value="Microsoft Copilot Studio",
    ),
]

AGENT_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.agent.name",
        value_type="string",
        description="Name of the agent handling the request",
        example_value="Customer Support Bot",
    ),
    OTELAttribute(
        key="gen_ai.agent.id",
        value_type="string",
        description="Unique identifier of the agent",
        example_value="bot-abc123",
    ),
    OTELAttribute(
        key="gen_ai.conversation.id",
        value_type="string",
        description="Unique identifier for the conversation session",
        example_value="conv-xyz789",
    ),
]

USAGE_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.usage.input_tokens",
        value_type="int",
        description="Number of input tokens consumed",
        example_value="150",
    ),
    OTELAttribute(
        key="gen_ai.usage.output_tokens",
        value_type="int",
        description="Number of output tokens generated",
        example_value="320",
    ),
]

TOOL_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.tool.name",
        value_type="string",
        description="Name of the tool being invoked",
        example_value="SearchKnowledgeBase",
    ),
    OTELAttribute(
        key="gen_ai.tool.type",
        value_type="string",
        description="Type of tool (function, plugin, connector)",
        example_value="function",
    ),
    OTELAttribute(
        key="gen_ai.tool.call.id",
        value_type="string",
        description="Unique identifier for the tool call",
        example_value="call-001",
    ),
    OTELAttribute(
        key="gen_ai.tool.call.arguments",
        value_type="string",
        description="JSON-encoded arguments passed to the tool",
        example_value='{"query": "refund policy"}',
    ),
    OTELAttribute(
        key="gen_ai.tool.call.result",
        value_type="string",
        description="JSON-encoded result returned by the tool",
        example_value='{"documents": [...]}',
    ),
]

MESSAGE_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.input.messages",
        value_type="string",
        description="JSON-encoded input messages sent to the model",
        example_value='[{"role": "user", "content": "Hello"}]',
    ),
    OTELAttribute(
        key="gen_ai.output.messages",
        value_type="string",
        description="JSON-encoded output messages from the model",
        example_value='[{"role": "assistant", "content": "Hi there!"}]',
    ),
    OTELAttribute(
        key="gen_ai.system_instructions",
        value_type="string",
        description="System prompt or instructions provided to the model",
        example_value="You are a helpful customer support agent.",
    ),
]

REQUEST_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.request.model",
        value_type="string",
        description="Model identifier used for the request",
        example_value="gpt-4o",
    ),
    OTELAttribute(
        key="gen_ai.request.temperature",
        value_type="float",
        description="Temperature parameter for generation",
        example_value="0.7",
    ),
    OTELAttribute(
        key="gen_ai.request.max_tokens",
        value_type="int",
        description="Maximum number of tokens to generate",
        example_value="1024",
    ),
]

RESPONSE_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.response.id",
        value_type="string",
        description="Unique identifier for the model response",
        example_value="resp-abc123",
    ),
    OTELAttribute(
        key="gen_ai.response.finish_reasons",
        value_type="string[]",
        description="Reasons the model stopped generating",
        example_value='["stop"]',
    ),
]

CONTEXT_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="mcs.channel",
        value_type="string",
        description="Communication channel (e.g. pva-studio, msteams)",
        example_value="pva-studio",
    ),
    OTELAttribute(
        key="mcs.environment",
        value_type="string",
        description="Deployment environment (design or production)",
        example_value="design",
    ),
    OTELAttribute(
        key="mcs.tenant",
        value_type="string",
        description="Azure AD tenant identifier",
        example_value="abc-def-123",
    ),
    OTELAttribute(
        key="mcs.turn.index",
        value_type="string",
        description="Turn index within the conversation",
        example_value="0",
    ),
    OTELAttribute(
        key="mcs.topic.name",
        value_type="string",
        description="Topic or dialog that was triggered",
        example_value="Greeting",
    ),
    OTELAttribute(
        key="user.message_preview",
        value_type="string",
        description="Plain text preview of the user message",
        example_value="I need help with expenses",
    ),
    OTELAttribute(
        key="assistant.message_preview",
        value_type="string",
        description="Plain text preview of the assistant response",
        example_value="I can help with that!",
    ),
    OTELAttribute(
        key="enduser.timezone",
        value_type="string",
        description="User's local timezone from message activity",
        example_value="Europe/Amsterdam",
    ),
    OTELAttribute(
        key="enduser.locale",
        value_type="string",
        description="User's locale from message activity",
        example_value="en-US",
    ),
    OTELAttribute(
        key="enduser.id",
        value_type="string",
        description="User's AAD object ID",
        example_value="6173da01-d84e-4dbd-beef-12fadce152f1",
    ),
]

RETRIEVAL_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="gen_ai.data_source.id",
        value_type="string",
        description="Identifier of the data source queried",
        example_value="kb-001",
    ),
    OTELAttribute(
        key="gen_ai.retrieval.query.text",
        value_type="string",
        description="The search query text sent to the retrieval system",
        example_value="expense policy for meals",
    ),
    OTELAttribute(
        key="gen_ai.retrieval.documents",
        value_type="string",
        description="JSON-encoded list of retrieved documents",
        example_value='[{"name": "policy.txt"}]',
    ),
    OTELAttribute(
        key="mcs.knowledge.sources",
        value_type="string",
        description="Comma-separated list of knowledge sources queried",
        example_value="file.policy.txt, file.team.txt",
    ),
    OTELAttribute(
        key="mcs.retrieval.document_count",
        value_type="string",
        description="Number of documents retrieved",
        example_value="3",
    ),
    OTELAttribute(
        key="mcs.retrieval.documents",
        value_type="string",
        description="Comma-separated names of retrieved documents",
        example_value="policy.txt, team.txt",
    ),
    OTELAttribute(
        key="mcs.retrieval.source_type",
        value_type="string",
        description="Types of retrieval sources used",
        example_value="DataverseSearch",
    ),
    OTELAttribute(
        key="mcs.retrieval.errors",
        value_type="string",
        description="JSON-encoded search errors if any",
        example_value="[]",
    ),
    OTELAttribute(
        key="mcs.knowledge.output_sources",
        value_type="string",
        description="Knowledge sources that produced output",
        example_value="file.policy.txt",
    ),
]

MCS_CUSTOM_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="mcs.session.outcome",
        value_type="string",
        description="Outcome of the session (resolved, escalated, abandoned)",
        example_value="resolved",
    ),
    OTELAttribute(
        key="mcs.action.type",
        value_type="string",
        description="Type of action executed within a topic",
        example_value="plugin",
    ),
    OTELAttribute(
        key="mcs.plan.id",
        value_type="string",
        description="Identifier for the orchestrator plan being executed",
        example_value="plan-001",
    ),
    OTELAttribute(
        key="mcs.plan.was_cancelled",
        value_type="string",
        description="Whether the plan was cancelled before completion",
        example_value="False",
    ),
    OTELAttribute(
        key="mcs.step.type",
        value_type="string",
        description="Type of step within an orchestrator plan",
        example_value="action",
    ),
    OTELAttribute(
        key="mcs.tool.step_state",
        value_type="string",
        description="State of plan step execution (completed, failed)",
        example_value="completed",
    ),
    OTELAttribute(
        key="mcs.orchestrator.thought",
        value_type="string",
        description="Orchestrator reasoning or chain-of-thought content",
        example_value="User is asking about refund policy, searching knowledge base.",
    ),
    OTELAttribute(
        key="mcs.tool.execution_time",
        value_type="string",
        description="Execution time of the step",
        example_value="00:00:01.234",
    ),
    OTELAttribute(
        key="mcs.search.keywords",
        value_type="string",
        description="Search keywords used in knowledge retrieval",
        example_value="expense policy, meals",
    ),
    OTELAttribute(
        key="mcs.tool.is_error",
        value_type="string",
        description="Whether the tool call returned an error",
        example_value="False",
    ),
    OTELAttribute(
        key="mcs.connector.result_url",
        value_type="string",
        description="URL returned by a connector action",
        example_value="https://teams.microsoft.com/...",
    ),
    OTELAttribute(
        key="mcs.hitl.responder_id",
        value_type="string",
        description="AAD object ID of the human-in-the-loop responder",
        example_value="6173da01-...",
    ),
    OTELAttribute(
        key="mcs.mcp.tool_name",
        value_type="string",
        description="Name of the MCP tool being called",
        example_value="create_new_expense_report",
    ),
    OTELAttribute(
        key="mcs.mcp.tool_count",
        value_type="string",
        description="Number of tools available on the MCP server",
        example_value="8",
    ),
    OTELAttribute(
        key="mcs.mcp.tool_names",
        value_type="string",
        description="Comma-separated names of available MCP tools",
        example_value="list_reports, create_report",
    ),
    OTELAttribute(
        key="mcs.plan.step_count",
        value_type="string",
        description="Number of steps in orchestrator plan",
        example_value="3",
    ),
    OTELAttribute(
        key="mcs.plan.is_final",
        value_type="string",
        description="Whether this is the final plan iteration",
        example_value="True",
    ),
    OTELAttribute(
        key="mcs.orchestrator.user_ask",
        value_type="string",
        description="User query as interpreted by orchestrator",
        example_value="trigger topic",
    ),
    OTELAttribute(
        key="mcs.orchestrator.plan_summary",
        value_type="string",
        description="Orchestrator's summary of the plan",
        example_value="Search knowledge base for policy",
    ),
    OTELAttribute(
        key="mcs.dialog.action_types",
        value_type="string",
        description="Comma-separated dialog action types",
        example_value="SendActivity, SetVariable",
    ),
    OTELAttribute(
        key="mcs.dialog.topic_ids",
        value_type="string",
        description="Topic IDs referenced in dialog actions",
        example_value="copilots_header.topic.ConversationStart",
    ),
    OTELAttribute(
        key="mcs.dialog.exceptions",
        value_type="string",
        description="Exceptions from dialog execution",
        example_value="Error in dialog step",
    ),
    OTELAttribute(
        key="mcs.dialog.action_count",
        value_type="string",
        description="Number of dialog actions executed",
        example_value="3",
    ),
    OTELAttribute(
        key="mcs.mcp.server_name",
        value_type="string",
        description="Name of the MCP server",
        example_value="Zava Expense Assistant",
    ),
    OTELAttribute(
        key="mcs.mcp.server_version",
        value_type="string",
        description="Version of the MCP server",
        example_value="2.13.1",
    ),
    OTELAttribute(
        key="mcs.mcp.protocol_version",
        value_type="string",
        description="MCP protocol version used",
        example_value="2024-11-05",
    ),
    OTELAttribute(
        key="mcs.mcp.session_id",
        value_type="string",
        description="MCP session identifier",
        example_value="56823f4f1af746e284a5221da035e332",
    ),
    OTELAttribute(
        key="mcs.mcp.capabilities",
        value_type="string",
        description="JSON-encoded MCP server capabilities",
        example_value='{"tools": {"listChanged": true}}',
    ),
    OTELAttribute(
        key="mcs.mcp.dialog_schema",
        value_type="string",
        description="Dialog schema name for MCP server",
        example_value="rrs_agent_orchestrator.topic.ZavaExpenseMCP",
    ),
    OTELAttribute(
        key="mcs.orchestrator.think_time_ms",
        value_type="string",
        description="Idle time in ms between plan finished and next plan received",
        example_value="1500",
    ),
    OTELAttribute(
        key="mcs.plan.used_outputs",
        value_type="string",
        description="JSON-encoded outputs passed between plan steps",
        example_value='{"key": "value"}',
    ),
    OTELAttribute(
        key="mcs.auth.mode",
        value_type="string",
        description="Bot authentication mode",
        example_value="Integrated",
    ),
    OTELAttribute(
        key="mcs.knowledge.configured_sources",
        value_type="string",
        description="JSON-encoded list of configured knowledge sources from botContent",
        example_value='["Expense policy", "Team Members"]',
    ),
    OTELAttribute(
        key="mcs.knowledge.full_result_count",
        value_type="string",
        description="Number of full results from knowledge search",
        example_value="5",
    ),
    OTELAttribute(
        key="mcs.knowledge.filtered_result_count",
        value_type="string",
        description="Number of filtered results from knowledge search",
        example_value="3",
    ),
    OTELAttribute(
        key="mcs.knowledge.source_count",
        value_type="string",
        description="Number of knowledge sources queried",
        example_value="2",
    ),
    OTELAttribute(
        key="mcs.mcp.connector_name",
        value_type="string",
        description="Name of the MCP connector from botContent",
        example_value="Zava Expense MCP Connector",
    ),
    OTELAttribute(
        key="mcs.plan.parent_id",
        value_type="string",
        description="Parent plan identifier for nested plan execution",
        example_value="plan-abc-123",
    ),
    OTELAttribute(
        key="mcs.plan.parent_step_id",
        value_type="string",
        description="Parent plan step identifier for nested plan execution",
        example_value="step-xyz-456",
    ),
    OTELAttribute(
        key="mcs.plan.step_id",
        value_type="string",
        description="Unique step identifier within a plan",
        example_value="step-001",
    ),
    OTELAttribute(
        key="mcs.step.state",
        value_type="string",
        description="Current state of a plan step",
        example_value="Triggered",
    ),
    OTELAttribute(
        key="mcs.step.has_recommendations",
        value_type="string",
        description="Whether the step produced recommendations",
        example_value="True",
    ),
    OTELAttribute(
        key="mcs.step.auto_filled_arguments",
        value_type="string",
        description="Arguments auto-filled by the orchestrator for a plan step",
        example_value='{"query": "expense policy"}',
    ),
    OTELAttribute(
        key="mcs.topic.type",
        value_type="string",
        description="Type of dialog redirect target",
        example_value="Topic",
    ),
    OTELAttribute(
        key="mcs.variable.id",
        value_type="string",
        description="Identifier of the variable being assigned",
        example_value="bot.userName",
    ),
    OTELAttribute(
        key="mcs.variable.new_value",
        value_type="string",
        description="New value assigned to the variable",
        example_value="John Doe",
    ),
    OTELAttribute(
        key="mcs.error.sub_code",
        value_type="string",
        description="Sub-error code for more specific error classification",
        example_value="ActionExecutionTimeout",
    ),
]

ALL_ATTRIBUTES: list[OTELAttribute] = (
    GENERAL_ATTRIBUTES
    + AGENT_ATTRIBUTES
    + USAGE_ATTRIBUTES
    + TOOL_ATTRIBUTES
    + MESSAGE_ATTRIBUTES
    + REQUEST_ATTRIBUTES
    + RESPONSE_ATTRIBUTES
    + CONTEXT_ATTRIBUTES
    + RETRIEVAL_ATTRIBUTES
    + MCS_CUSTOM_ATTRIBUTES
)

ATTRIBUTE_BY_KEY: dict[str, OTELAttribute] = {attr.key: attr for attr in ALL_ATTRIBUTES}

OTEL_TARGETS: list[str] = [
    "invoke_agent",
    "chat",
    "execute_tool",
    "knowledge.retrieval",
    "chain",
    "text_completion",
    "create_agent",
    "dialog_redirect",
    "intent_recognition",
    "execute_node",
]
