from pydantic import BaseModel


class OTELAttribute(BaseModel):
    key: str
    value_type: str
    description: str
    requirement_level: str = "recommended"
    example_value: str = ""


def _load_attributes() -> list[OTELAttribute]:
    """Load OTEL attributes from JSON config file."""
    from config_loader import load_otel_attributes
    return load_otel_attributes()


ALL_ATTRIBUTES: list[OTELAttribute] = _load_attributes()
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
