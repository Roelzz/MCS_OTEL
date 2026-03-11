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

MCS_CUSTOM_ATTRIBUTES: list[OTELAttribute] = [
    OTELAttribute(
        key="copilot_studio.topic_name",
        value_type="string",
        description="Name of the Copilot Studio topic triggered",
        example_value="Greeting",
    ),
    OTELAttribute(
        key="copilot_studio.session_outcome",
        value_type="string",
        description="Outcome of the session (resolved, escalated, abandoned)",
        example_value="resolved",
    ),
    OTELAttribute(
        key="copilot_studio.action_type",
        value_type="string",
        description="Type of action executed within a topic",
        example_value="plugin",
    ),
    OTELAttribute(
        key="copilot_studio.plan_identifier",
        value_type="string",
        description="Identifier for the orchestrator plan being executed",
        example_value="plan-001",
    ),
    OTELAttribute(
        key="copilot_studio.step_type",
        value_type="string",
        description="Type of step within an orchestrator plan",
        example_value="action",
    ),
    OTELAttribute(
        key="copilot_studio.thought",
        value_type="string",
        description="Orchestrator reasoning or chain-of-thought content",
        example_value="User is asking about refund policy, searching knowledge base.",
    ),
    OTELAttribute(
        key="copilot_studio.execution_time",
        value_type="string",
        description="Execution time of the step in milliseconds",
        example_value="1250",
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
    + MCS_CUSTOM_ATTRIBUTES
)

ATTRIBUTE_BY_KEY: dict[str, OTELAttribute] = {attr.key: attr for attr in ALL_ATTRIBUTES}

OTEL_TARGETS: list[str] = [
    "invoke_agent",
    "chat",
    "execute_tool",
    "chain",
    "text_completion",
    "create_agent",
]
