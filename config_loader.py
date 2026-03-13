"""Config loading and saving for MappingSpecification and OTEL attributes."""

import json
import os
from pathlib import Path

from loguru import logger

from models import MappingSpecification

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="{time:DD-MM-YYYY at HH:mm:ss} | {level: <8} | {message}",
)

CONFIG_DIR = Path(__file__).parent / "config"
DEFAULT_MAPPING_PATH = CONFIG_DIR / "default_mapping.json"


def load_mapping_spec(path: str | Path) -> MappingSpecification:
    """Load and validate a MappingSpecification from JSON file."""
    path = Path(path)
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    spec = MappingSpecification.model_validate(data)
    logger.info(
        "Loaded mapping spec from {}: {} rules, {} event_metadata, {} enrichment_rules",
        path.name,
        len(spec.rules),
        len(spec.event_metadata),
        len(spec.enrichment_rules),
    )
    return spec


def load_default_mapping() -> MappingSpecification:
    """Load from config/default_mapping.json. Falls back to generate_default_mapping() if missing."""
    if DEFAULT_MAPPING_PATH.exists():
        return load_mapping_spec(DEFAULT_MAPPING_PATH)

    logger.warning(
        "Default mapping JSON not found at {}, falling back to generate_default_mapping()",
        DEFAULT_MAPPING_PATH,
    )
    from converter import generate_default_mapping

    return generate_default_mapping()


def save_mapping_spec(spec: MappingSpecification, path: str | Path) -> None:
    """Write MappingSpecification to JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = spec.model_dump_json(indent=2)
    path.write_text(content, encoding="utf-8")
    logger.info("Saved mapping spec to {}: {} rules", path, len(spec.rules))
