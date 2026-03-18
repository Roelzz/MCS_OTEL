"""Config loading and saving for MappingSpecification and OTEL attributes."""

import json
from pathlib import Path

from log import logger
from models import MappingSpecification

CONFIG_DIR = Path(__file__).parent / "config"
MAPPINGS_DIR = CONFIG_DIR / "mappings"
DEFAULT_MAPPING_PATH = MAPPINGS_DIR / "default.json"
OTEL_ATTRIBUTES_PATH = CONFIG_DIR / "otel_attributes.json"


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
    """Load from config/mappings/default.json."""
    return load_mapping_spec(DEFAULT_MAPPING_PATH)


def list_mappings() -> list[dict]:
    """Scan MAPPINGS_DIR and return metadata for each mapping file."""
    MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(MAPPINGS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result.append({
                "name": path.stem,
                "path": str(path),
                "version": data.get("version", ""),
                "rule_count": len(data.get("rules", [])),
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping invalid mapping file {}: {}", path.name, e)
    return result


def load_mapping_by_name(name: str) -> MappingSpecification:
    """Load a mapping from MAPPINGS_DIR by stem name."""
    path = MAPPINGS_DIR / f"{name}.json"
    return load_mapping_spec(path)


def delete_mapping_file(name: str) -> None:
    """Delete a mapping file from MAPPINGS_DIR."""
    path = MAPPINGS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Mapping '{name}' not found")
    path.unlink()
    logger.info("Deleted mapping file: {}", path)


def save_mapping_spec(spec: MappingSpecification, path: str | Path) -> None:
    """Write MappingSpecification to JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = spec.model_dump_json(indent=2)
    path.write_text(content, encoding="utf-8")
    logger.info("Saved mapping spec to {}: {} rules", path, len(spec.rules))


KNOWN_OPS = {"extract_path", "len", "join", "join_unique_sorted", "json_dump", "str_coerce", "rename", "template", "conditional"}


def validate_mapping_spec(spec: MappingSpecification) -> list[str]:
    """Validate a MappingSpecification. Returns list of issues (empty = valid)."""
    issues: list[str] = []

    # Check duplicate rule_ids
    rule_ids = [r.rule_id for r in spec.rules]
    seen = set()
    for rid in rule_ids:
        if rid in seen:
            issues.append(f"Duplicate rule_id: {rid}")
        seen.add(rid)

    # Check parent_rule_id references resolve
    rule_id_set = set(rule_ids)
    for rule in spec.rules:
        if rule.parent_rule_id and rule.parent_rule_id not in rule_id_set:
            issues.append(f"Rule '{rule.rule_id}' references unknown parent '{rule.parent_rule_id}'")

    # Check enrichment op types
    for er in spec.enrichment_rules:
        for op in er.derived_fields:
            if op.op not in KNOWN_OPS:
                issues.append(f"Unknown enrichment op '{op.op}' in rule for {er.value_type}")

    # Check value_type in rules has matching event_metadata (warning)
    # SessionInfo is handled specially as session_root, so skip it
    meta_vts = {em.value_type for em in spec.event_metadata}
    meta_vts.add("SessionInfo")  # Always valid — handled as root
    for rule in spec.rules:
        if rule.mcs_value_type and rule.mcs_value_type not in meta_vts:
            issues.append(f"Rule '{rule.rule_id}' value_type '{rule.mcs_value_type}' has no event_metadata entry")

    return issues


def load_otel_attributes(path: str | Path | None = None) -> list:
    """Load OTEL attribute definitions from JSON file."""
    from otel_registry import OTELAttribute

    path = Path(path) if path else OTEL_ATTRIBUTES_PATH
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    attributes = [OTELAttribute.model_validate(item) for item in data]
    logger.info("Loaded {} OTEL attributes from {}", len(attributes), path.name)
    return attributes
