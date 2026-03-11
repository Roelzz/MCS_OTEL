import json
import uuid

from converter import generate_default_mapping
from models import (
    AttributeMapping,
    MappingSpecification,
    OTELOperationName,
    OTELSpanKind,
    SpanMappingRule,
    TransformType,
)


class MappingMixin:
    mapping_spec: dict = {}  # Serialized MappingSpecification
    selected_rule_id: str = ""
    selected_mcs_entity: str = ""  # Currently clicked MCS entity in connection view
    connections: list[dict] = []  # [{mcs_entity_type, otel_target, rule_id}]

    def select_mcs_entity(self, entity_type: str):
        """First click: highlight MCS entity in connection view."""
        if self.selected_mcs_entity == entity_type:
            self.selected_mcs_entity = ""  # deselect
        else:
            self.selected_mcs_entity = entity_type

    def connect_to_otel(self, otel_target: str):
        """Second click: create connection + auto-generate rule."""
        if not self.selected_mcs_entity:
            return

        # Check for existing connection
        for conn in self.connections:
            if (
                conn["mcs_entity_type"] == self.selected_mcs_entity
                and conn["otel_target"] == otel_target
            ):
                self.selected_mcs_entity = ""
                return

        rule_id = f"rule_{uuid.uuid4().hex[:8]}"

        # Determine the operation name from otel_target
        try:
            op_name = OTELOperationName(otel_target)
        except ValueError:
            op_name = OTELOperationName.chat

        # Create a new rule
        new_rule = SpanMappingRule(
            rule_id=rule_id,
            rule_name=f"{self.selected_mcs_entity} → {otel_target}",
            mcs_entity_type=self._infer_entity_type(self.selected_mcs_entity),
            mcs_value_type=self.selected_mcs_entity
            if self._infer_entity_type(self.selected_mcs_entity) == "trace_event"
            else "",
            otel_operation_name=op_name,
            span_name_template=f"{otel_target} {{}}",
        )

        # Add to spec
        spec = self._get_spec()
        spec.rules.append(new_rule)
        self.mapping_spec = spec.model_dump()

        # Add connection
        self.connections.append(
            {
                "mcs_entity_type": self.selected_mcs_entity,
                "otel_target": otel_target,
                "rule_id": rule_id,
            }
        )

        self.selected_mcs_entity = ""

    def _infer_entity_type(self, label: str) -> str:
        """Infer entity_type from the MCS entity label."""
        turn_labels = {"UserMessage", "BotMessage", "Turn"}
        if label in turn_labels:
            return "turn"
        return "trace_event"

    def _get_spec(self) -> MappingSpecification:
        """Get current spec from state dict."""
        if self.mapping_spec:
            return MappingSpecification(**self.mapping_spec)
        return MappingSpecification()

    def remove_connection(self, rule_id: str):
        """Remove connection line + rule."""
        self.connections = [c for c in self.connections if c["rule_id"] != rule_id]
        spec = self._get_spec()
        spec.rules = [r for r in spec.rules if r.rule_id != rule_id]
        self.mapping_spec = spec.model_dump()
        if self.selected_rule_id == rule_id:
            self.selected_rule_id = ""

    def select_rule(self, rule_id: str):
        """Select a rule for editing."""
        self.selected_rule_id = rule_id

    def update_rule_field(self, rule_id: str, field: str, value: str):
        """Update a single field on a rule."""
        spec = self._get_spec()
        for rule in spec.rules:
            if rule.rule_id == rule_id:
                if field == "span_name_template":
                    rule.span_name_template = value
                elif field == "parent_rule_id":
                    rule.parent_rule_id = value if value else None
                elif field == "is_root":
                    rule.is_root = value.lower() == "true"
                elif field == "rule_name":
                    rule.rule_name = value
                elif field == "otel_span_kind":
                    rule.otel_span_kind = OTELSpanKind(value)
                break
        self.mapping_spec = spec.model_dump()

    def add_attribute_mapping(self, rule_id: str):
        """Add empty attribute mapping to rule."""
        spec = self._get_spec()
        for rule in spec.rules:
            if rule.rule_id == rule_id:
                rule.attribute_mappings.append(
                    AttributeMapping(mcs_property="", otel_attribute="")
                )
                break
        self.mapping_spec = spec.model_dump()

    def remove_attribute_mapping(self, rule_id: str, idx: int):
        """Remove attribute mapping from rule by index."""
        spec = self._get_spec()
        for rule in spec.rules:
            if rule.rule_id == rule_id:
                if 0 <= idx < len(rule.attribute_mappings):
                    rule.attribute_mappings.pop(idx)
                break
        self.mapping_spec = spec.model_dump()

    def update_attribute_mapping(
        self, rule_id: str, idx: int, field: str, value: str
    ):
        """Update a field on a specific attribute mapping."""
        spec = self._get_spec()
        for rule in spec.rules:
            if rule.rule_id == rule_id:
                if 0 <= idx < len(rule.attribute_mappings):
                    am = rule.attribute_mappings[idx]
                    if field == "mcs_property":
                        am.mcs_property = value
                    elif field == "otel_attribute":
                        am.otel_attribute = value
                    elif field == "transform":
                        am.transform = TransformType(value)
                    elif field == "transform_value":
                        am.transform_value = value
                break
        self.mapping_spec = spec.model_dump()

    def load_defaults(self):
        """Populate from generate_default_mapping(), also populate connections list."""
        spec = generate_default_mapping()
        self.mapping_spec = spec.model_dump()

        # Build connections from rules
        self.connections = []
        for rule in spec.rules:
            mcs_label = (
                rule.mcs_value_type if rule.mcs_value_type else rule.mcs_entity_type
            )
            self.connections.append(
                {
                    "mcs_entity_type": mcs_label,
                    "otel_target": rule.otel_operation_name.value,
                    "rule_id": rule.rule_id,
                }
            )

    def import_mapping(self, json_str: str):
        """Import mapping from JSON string."""
        try:
            data = json.loads(json_str)
            spec = MappingSpecification(**data)
            self.mapping_spec = spec.model_dump()
            # Rebuild connections
            self.connections = []
            for rule in spec.rules:
                mcs_label = (
                    rule.mcs_value_type
                    if rule.mcs_value_type
                    else rule.mcs_entity_type
                )
                self.connections.append(
                    {
                        "mcs_entity_type": mcs_label,
                        "otel_target": rule.otel_operation_name.value,
                        "rule_id": rule.rule_id,
                    }
                )
        except Exception:
            pass

    def export_mapping(self) -> str:
        """Export mapping spec as JSON string."""
        spec = self._get_spec()
        return spec.model_dump_json(indent=2)
