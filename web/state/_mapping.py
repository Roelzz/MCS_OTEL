import json
import uuid

import pydantic
import reflex as rx

from config_loader import load_default_mapping
from models import (
    AttributeMapping,
    MappingSpecification,
    OTELOperationName,
    OTELSpanKind,
    SpanMappingRule,
    TransformType,
)

# --- React Flow node/edge generation ---

MCS_GROUPS: list[tuple[str, str, list[str]]] = [
    ("Session", "#3b82f6", ["SessionInfo"]),
    ("Turns", "#22c55e", ["turn"]),
    ("Orchestrator", "#a855f7", [
        "DynamicPlanReceived", "DynamicPlanStepTriggered",
        "DynamicPlanStepBindUpdate", "DynamicPlanStepFinished",
        "DynamicPlanFinished", "DynamicPlanReceivedDebug",
    ]),
    ("MCP", "#06b6d4", [
        "DynamicServerInitialize", "DynamicServerInitializeConfirmation",
        "DynamicServerToolsList",
    ]),
    ("Dialog & Classification", "#f59e0b", [
        "DialogTracingInfo", "DialogRedirect", "UnknownIntent",
        "VariableAssignment",
    ]),
    ("Knowledge & Skills", "#14b8a6", [
        "UniversalSearchToolTraceData", "SkillInfo", "ProtocolInfo",
    ]),
    ("Errors", "#ef4444", ["ErrorTraceData", "ErrorCode"]),
]

OTEL_TARGET_COLORS: dict[str, str] = {
    "invoke_agent": "#3b82f6",
    "chat": "#22c55e",
    "execute_tool": "#f97316",
    "knowledge.retrieval": "#14b8a6",
    "chain": "#a855f7",
    "text_completion": "#6b7280",
    "create_agent": "#06b6d4",
    "dialog_redirect": "#f59e0b",
    "intent_recognition": "#84cc16",
    "execute_node": "#ec4899",
}

_ENTITY_SHORT_LABELS: dict[str, str] = {
    "SessionInfo": "SessionInfo",
    "turn": "Turn",
    "DynamicPlanReceived": "PlanReceived",
    "DynamicPlanStepTriggered": "PlanStepTriggered",
    "DynamicPlanStepBindUpdate": "PlanStepBind",
    "DynamicPlanStepFinished": "PlanStepFinished",
    "DynamicPlanFinished": "PlanFinished",
    "DynamicPlanReceivedDebug": "PlanRecvDebug",
    "DynamicServerInitialize": "ServerInit",
    "DynamicServerInitializeConfirmation": "ServerInitConf",
    "DynamicServerToolsList": "ServerToolsList",
    "DialogTracingInfo": "DialogTracing",
    "DialogRedirect": "DialogRedirect",
    "UnknownIntent": "UnknownIntent",
    "VariableAssignment": "VarAssignment",
    "UniversalSearchToolTraceData": "KnowledgeSearch",
    "SkillInfo": "SkillInfo",
    "ProtocolInfo": "ProtocolInfo",
    "ErrorTraceData": "ErrorTrace",
    "ErrorCode": "ErrorCode",
}


def _build_flow_nodes() -> list[dict]:
    """Build React Flow nodes for MCS entities (left) and OTEL targets (right)."""
    nodes: list[dict] = []
    y = 0

    for group_name, color, entities in MCS_GROUPS:
        # Group header — non-interactive label node
        nodes.append({
            "id": f"header_{group_name}",
            "data": {"label": group_name.upper()},
            "position": {"x": 50, "y": y},
            "connectable": False,
            "selectable": False,
            "draggable": False,
            "style": {
                "background": "transparent",
                "border": "none",
                "boxShadow": "none",
                "fontSize": "10px",
                "fontWeight": "700",
                "color": color,
                "letterSpacing": "0.05em",
                "width": "230px",
                "padding": "2px 4px",
                "minHeight": "0",
            },
        })
        y += 28

        for entity in entities:
            label = _ENTITY_SHORT_LABELS.get(entity, entity)
            nodes.append({
                "id": f"mcs_{entity}",
                "type": "input",
                "data": {"label": label},
                "position": {"x": 50, "y": y},
                "sourcePosition": "right",
                "draggable": False,
                "style": {
                    "background": f"{color}18",
                    "border": f"1px solid {color}88",
                    "borderRadius": "6px",
                    "fontSize": "12px",
                    "padding": "4px 10px",
                    "width": "230px",
                    "minHeight": "0",
                },
            })
            y += 42

        y += 14

    # OTEL targets — centered vertically relative to total MCS height
    total_mcs_h = y
    otel_targets = list(OTEL_TARGET_COLORS.items())
    otel_spacing = 65
    otel_total = len(otel_targets) * otel_spacing
    otel_start_y = max(0, (total_mcs_h - otel_total) // 2)

    for i, (target, color) in enumerate(otel_targets):
        nodes.append({
            "id": f"otel_{target}",
            "type": "output",
            "data": {"label": target},
            "position": {"x": 700, "y": otel_start_y + i * otel_spacing},
            "targetPosition": "left",
            "draggable": False,
            "style": {
                "background": f"{color}20",
                "border": f"2px solid {color}",
                "borderRadius": "6px",
                "fontSize": "13px",
                "fontWeight": "500",
                "padding": "6px 12px",
                "width": "200px",
                "minHeight": "0",
            },
        })

    return nodes


def _build_flow_edges(
    connections: list[dict], rules: list[dict] | None = None
) -> list[dict]:
    """Build React Flow edges from connection list, with attr labels from rules."""
    # Build rule lookup by rule_id
    rule_map: dict[str, dict] = {}
    if rules:
        for r in rules:
            rule_map[r.get("rule_id", "")] = r

    edges: list[dict] = []
    for conn in connections:
        source = f"mcs_{conn['mcs_entity_type']}"
        target = f"otel_{conn['otel_target']}"
        rule_id = conn.get("rule_id", "")

        # Build label from attribute mappings
        label = ""
        rule = rule_map.get(rule_id)
        if rule:
            attrs = rule.get("attribute_mappings", [])
            count = len(attrs)
            if count > 0:
                names = [a.get("otel_attribute", "").split(".")[-1] for a in attrs[:2]]
                preview = ", ".join(n for n in names if n)
                suffix = "..." if count > 2 else ""
                label = f"{count} attrs: {preview}{suffix}"

        edge: dict = {
            "id": f"{source}->{target}",
            "source": source,
            "target": target,
            "animated": True,
            "style": {"stroke": "#22c55e", "strokeWidth": 2},
            "markerEnd": {"type": "arrowclosed", "color": "#22c55e"},
            "data": {"ruleId": rule_id},
        }
        if label:
            edge["label"] = label
            edge["labelStyle"] = {"fontSize": "10px", "fill": "#6b7280"}
            edge["labelBgStyle"] = {"fill": "#fff", "fillOpacity": 0.85}
            edge["labelBgPadding"] = [4, 2]
        edges.append(edge)
    return edges


DEFAULT_FLOW_NODES: list[dict] = _build_flow_nodes()


class MappingMixin(rx.State, mixin=True):
    mapping_spec: dict = {}  # Serialized MappingSpecification
    import_json_text: str = ""
    selected_rule_id: str = ""
    selected_mcs_entity: str = ""  # Currently clicked MCS entity in connection view
    connections: list[dict] = []  # [{mcs_entity_type, otel_target, rule_id}]
    _collapsed_rules: set[str] = set()
    _rule_validation_errors: dict[str, str] = {}
    rule_filter_text: str = ""

    # React Flow state
    flow_nodes: list[dict] = DEFAULT_FLOW_NODES
    flow_edges: list[dict] = []
    selected_connection_rule_id: str = ""

    def toggle_rule_collapse(self, rule_id: str):
        if rule_id in self._collapsed_rules:
            self._collapsed_rules.discard(rule_id)
        else:
            self._collapsed_rules.add(rule_id)

    def collapse_all_rules(self):
        if self.mapping_spec and "rules" in self.mapping_spec:
            self._collapsed_rules = {
                r.get("rule_id", "") for r in self.mapping_spec["rules"]
            }

    def expand_all_rules(self):
        self._collapsed_rules = set()

    @rx.var(cache=True)
    def mapping_rules(self) -> list[dict]:
        """Return the rules list from mapping_spec for foreach iteration.

        Adds attr_count, attr_summary, description, is_collapsed, and
        inline stat fields for display.
        """
        if not self.mapping_spec or "rules" not in self.mapping_spec:
            return []

        # Build stat lookup from _rule_stats (set by PreviewMixin)
        stat_map: dict[str, dict] = {}
        for s in getattr(self, "_rule_stats", []):
            stat_map[s.get("rule_id", "")] = s

        rules = []
        for rule in self.mapping_spec["rules"]:
            r = {**rule}
            mappings = rule.get("attribute_mappings", [])
            r["attr_count"] = len(mappings)
            lines = []
            for am in mappings:
                mcs = am.get("mcs_property", "")
                otel = am.get("otel_attribute", "")
                transform = am.get("transform", "direct")
                suffix = f"  [{transform}]" if transform != "direct" else ""
                lines.append(f"{mcs}  →  {otel}{suffix}")
            r["attr_summary"] = "\n".join(lines) if lines else ""
            enriched_mappings = []
            for i, am in enumerate(mappings):
                enriched_mappings.append({**am, "idx": i, "rule_id": rule.get("rule_id", "")})
            r["enriched_attribute_mappings"] = enriched_mappings
            r["description"] = rule.get("description", "")
            r["is_collapsed"] = rule.get("rule_id", "") in self._collapsed_rules

            # Merge inline stats
            st = stat_map.get(rule.get("rule_id", ""), {})
            r["stat_match_count"] = st.get("match_count", -1)
            r["stat_fill_rate"] = st.get("fill_rate", -1.0)
            r["validation_error"] = self._rule_validation_errors.get(rule.get("rule_id", ""), "")
            rules.append(r)

        if self.rule_filter_text:
            q = self.rule_filter_text.lower()
            rules = [r for r in rules if (
                q in r.get("rule_id", "").lower()
                or q in r.get("mcs_value_type", "").lower()
                or q in r.get("otel_operation_name", "").lower()
                or q in r.get("rule_name", "").lower()
            )]

        return rules

    @rx.var(cache=True)
    def total_rule_count(self) -> int:
        if not self.mapping_spec or "rules" not in self.mapping_spec:
            return 0
        return len(self.mapping_spec["rules"])

    @rx.var(cache=True)
    def has_mapping(self) -> bool:
        """Whether a mapping spec with rules exists."""
        return bool(self.mapping_spec and self.mapping_spec.get("rules"))

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
        if label.lower() in {"usermessage", "botmessage", "turn"}:
            return "turn"
        return "trace_event"

    def _get_spec(self) -> MappingSpecification:
        """Get current spec from state dict — used only for validation-heavy paths."""
        if self.mapping_spec:
            return MappingSpecification(**self.mapping_spec)
        return MappingSpecification()

    def _find_rule_dict(self, rule_id: str) -> dict | None:
        """Find a rule dict directly in mapping_spec['rules'] by rule_id."""
        if not self.mapping_spec or "rules" not in self.mapping_spec:
            return None
        for rule in self.mapping_spec["rules"]:
            if rule.get("rule_id") == rule_id:
                return rule
        return None

    def remove_connection(self, rule_id: str):
        """Remove connection line + rule."""
        self.connections = [c for c in self.connections if c["rule_id"] != rule_id]
        if self.mapping_spec and "rules" in self.mapping_spec:
            self.mapping_spec["rules"] = [
                r for r in self.mapping_spec["rules"] if r.get("rule_id") != rule_id
            ]
        if self.selected_rule_id == rule_id:
            self.selected_rule_id = ""

    def on_flow_connect(self, connection: dict):
        """Handle new connection from React Flow drag-and-drop."""
        source_id = connection.get("source", "")
        target_id = connection.get("target", "")

        mcs_entity = source_id.removeprefix("mcs_")
        otel_target = target_id.removeprefix("otel_")

        # Check for existing connection
        for conn in self.connections:
            if conn["mcs_entity_type"] == mcs_entity and conn["otel_target"] == otel_target:
                return

        # Reuse connect_to_otel logic
        self.selected_mcs_entity = mcs_entity
        self.connect_to_otel(otel_target)

        # Rebuild flow edges
        self.flow_edges = _build_flow_edges(
            self.connections, self.mapping_spec.get("rules") if self.mapping_spec else None
        )

    def on_flow_edge_delete(self, edge_id: str):
        """Handle edge deletion from React Flow."""
        parts = edge_id.split("->")
        if len(parts) != 2:
            return

        source_id, target_id = parts
        mcs_entity = source_id.removeprefix("mcs_")
        otel_target = target_id.removeprefix("otel_")

        for conn in self.connections:
            if conn["mcs_entity_type"] == mcs_entity and conn["otel_target"] == otel_target:
                self.remove_connection(conn["rule_id"])
                break

        self.flow_edges = _build_flow_edges(
            self.connections, self.mapping_spec.get("rules") if self.mapping_spec else None
        )

    @rx.var(cache=True)
    def rule_validation_errors(self) -> dict[str, str]:
        return self._rule_validation_errors

    @rx.var(cache=True)
    def rule_hierarchy_nodes(self) -> list[dict]:
        """React Flow nodes for rule hierarchy visualization."""
        if not self.mapping_spec or "rules" not in self.mapping_spec:
            return []
        rules = self.mapping_spec["rules"]
        # Build stat lookup
        stat_map: dict[str, dict] = {}
        for s in getattr(self, "_rule_stats", []):
            stat_map[s.get("rule_id", "")] = s

        # BFS-style layout: group by depth (root → children → grandchildren)
        children_map: dict[str, list[str]] = {}
        root_ids: list[str] = []
        rule_by_id: dict[str, dict] = {}
        for r in rules:
            rid = r.get("rule_id", "")
            rule_by_id[rid] = r
            parent = r.get("parent_rule_id")
            if r.get("is_root") or not parent:
                root_ids.append(rid)
            else:
                children_map.setdefault(parent, []).append(rid)

        nodes: list[dict] = []
        x_spacing = 280
        y_spacing = 100
        # BFS to assign positions
        queue = [(rid, 0) for rid in root_ids]
        col_counts: dict[int, int] = {}
        while queue:
            rid, depth = queue.pop(0)
            r = rule_by_id.get(rid)
            if not r:
                continue
            row = col_counts.get(depth, 0)
            col_counts[depth] = row + 1

            vt = r.get("mcs_value_type", "") or r.get("mcs_entity_type", "")
            op = r.get("otel_operation_name", "")
            output_type = r.get("output_type", "span")
            st = stat_map.get(rid, {})
            match_count = st.get("match_count", -1)
            fill_rate = st.get("fill_rate", 0.0)

            # Color based on fill rate
            if match_count < 0:
                border_color = "#6b7280"
            elif fill_rate >= 80:
                border_color = "#22c55e"
            elif fill_rate >= 50:
                border_color = "#f59e0b"
            else:
                border_color = "#ef4444"

            is_event = output_type == "event"
            label = f"{rid[:12]}\n{vt} → {op}"
            match_label = f" [{match_count}]" if match_count >= 0 else ""

            nodes.append({
                "id": f"rule_{rid}",
                "data": {"label": f"{label}{match_label}"},
                "position": {"x": depth * x_spacing + 50, "y": row * y_spacing + 50},
                "draggable": False,
                "style": {
                    "background": "#fef9c3" if is_event else "#f0fdf4",
                    "border": f"2px solid {border_color}",
                    "borderRadius": "8px",
                    "fontSize": "11px",
                    "padding": "8px",
                    "width": "240px",
                    "whiteSpace": "pre-line",
                    "minHeight": "0",
                },
            })
            for child_id in children_map.get(rid, []):
                queue.append((child_id, depth + 1))

        return nodes

    @rx.var(cache=True)
    def rule_hierarchy_edges(self) -> list[dict]:
        """React Flow edges for rule parent-child relationships."""
        if not self.mapping_spec or "rules" not in self.mapping_spec:
            return []
        edges: list[dict] = []
        for r in self.mapping_spec["rules"]:
            parent = r.get("parent_rule_id")
            if parent:
                rid = r.get("rule_id", "")
                edges.append({
                    "id": f"rule_{parent}->rule_{rid}",
                    "source": f"rule_{parent}",
                    "target": f"rule_{rid}",
                    "style": {"stroke": "#22c55e", "strokeWidth": 1.5},
                    "markerEnd": {"type": "arrowclosed", "color": "#22c55e"},
                })
        return edges

    @rx.var(cache=True)
    def enrichment_summary(self) -> list[dict]:
        """Summary of enrichment rules with operation details."""
        if not self.mapping_spec:
            return []
        rules = self.mapping_spec.get("enrichment_rules", [])
        if not rules:
            return []

        # Count entities per value_type
        entity_counts: dict[str, int] = {}
        for e in getattr(self, "entities", []):
            vt = e.get("value_type", "")
            if vt:
                entity_counts[vt] = entity_counts.get(vt, 0) + 1

        result = []
        for er in rules:
            vt = er.get("value_type", "")
            ops = er.get("derived_fields", [])
            op_types = list({o.get("op", "") for o in ops})
            field_names = [o.get("target", "") for o in ops]
            result.append({
                "value_type": vt,
                "op_count": len(ops),
                "op_types": op_types,
                "field_names": field_names,
                "entity_count": entity_counts.get(vt, 0),
            })
        return result

    @rx.var(cache=True)
    def enrichment_target_keys(self) -> list[str]:
        """All target field names from enrichment rules — used to tag enriched properties."""
        if not self.mapping_spec:
            return []
        rules = self.mapping_spec.get("enrichment_rules", [])
        targets: list[str] = []
        for er in rules:
            for op in er.get("derived_fields", []):
                t = op.get("target", "")
                if t and t not in targets:
                    targets.append(t)
        return targets

    @rx.var(cache=True)
    def event_metadata_list(self) -> list[dict]:
        """Event metadata enriched with entity counts and rule coverage."""
        if not self.mapping_spec:
            return []
        meta = self.mapping_spec.get("event_metadata", [])
        if not meta:
            return []

        # Count entities per value_type
        entity_counts: dict[str, int] = {}
        for e in getattr(self, "entities", []):
            vt = e.get("value_type", "")
            if vt:
                entity_counts[vt] = entity_counts.get(vt, 0) + 1

        # Build rule lookup by value_type
        rule_lookup: dict[str, str] = {}
        for r in self.mapping_spec.get("rules", []):
            vt = r.get("mcs_value_type", "")
            if vt:
                rule_lookup[vt] = r.get("rule_id", "")

        result = []
        for em in meta:
            vt = em.get("value_type", "")
            ec = entity_counts.get(vt, 0)
            rid = rule_lookup.get(vt, "")
            has_rule = bool(rid)
            # Status: green=entities+rule, orange=entities but no rule, gray=rule but no entities, red=neither
            if ec > 0 and has_rule:
                status = "covered"
            elif ec > 0 and not has_rule:
                status = "gap"
            elif ec == 0 and has_rule:
                status = "unused"
            else:
                status = "inactive"
            result.append({
                "value_type": vt,
                "label": em.get("label", vt),
                "description": em.get("description", ""),
                "entity_count": ec,
                "default_output_type": em.get("default_output_type", ""),
                "has_rule": has_rule,
                "rule_id": rid,
                "status": status,
            })
        return result

    def noop_dict(self, _data: dict):
        """No-op handler for dict event specs."""
        pass

    def noop_str(self, _data: str):
        """No-op handler for str event specs."""
        pass

    def select_connection_rule(self, rule_id: str):
        """Select a connection edge to show its detail."""
        self.selected_connection_rule_id = (
            rule_id if self.selected_connection_rule_id != rule_id else ""
        )

    @rx.var(cache=True)
    def selected_connection_detail(self) -> list[dict]:
        """Attribute mappings for the selected connection's rule."""
        if not self.selected_connection_rule_id or not self.mapping_spec:
            return []
        for rule in self.mapping_spec.get("rules", []):
            if rule.get("rule_id") == self.selected_connection_rule_id:
                result = []
                for am in rule.get("attribute_mappings", []):
                    result.append({
                        "mcs_property": am.get("mcs_property", ""),
                        "otel_attribute": am.get("otel_attribute", ""),
                        "transform": am.get("transform", "direct"),
                    })
                return result
        return []

    @rx.var(cache=True)
    def selected_connection_rule_name(self) -> str:
        """Name of the selected connection's rule."""
        if not self.selected_connection_rule_id or not self.mapping_spec:
            return ""
        for rule in self.mapping_spec.get("rules", []):
            if rule.get("rule_id") == self.selected_connection_rule_id:
                return rule.get("rule_name", rule.get("rule_id", ""))
        return ""

    def select_rule(self, rule_id: str):
        """Select a rule for editing."""
        self.selected_rule_id = rule_id

    def update_rule_field(self, rule_id: str, field: str, value: str):
        """Update a single field on a rule."""
        rule = self._find_rule_dict(rule_id)
        if not rule:
            return
        if field == "span_name_template":
            rule["span_name_template"] = value
            if not value.strip():
                self._rule_validation_errors[rule_id] = "Span name template cannot be empty"
            else:
                self._rule_validation_errors.pop(rule_id, None)
        elif field == "parent_rule_id":
            rule["parent_rule_id"] = value if value else None
            if value:
                known_ids = {
                    r.get("rule_id", "")
                    for r in (self.mapping_spec or {}).get("rules", [])
                }
                if value not in known_ids:
                    self._rule_validation_errors[rule_id] = f"Unknown parent: {value}"
                else:
                    self._rule_validation_errors.pop(rule_id, None)
            else:
                self._rule_validation_errors.pop(rule_id, None)
        elif field == "is_root":
            rule["is_root"] = value.lower() == "true"
        elif field == "rule_name":
            rule["rule_name"] = value
        elif field == "otel_span_kind":
            rule["otel_span_kind"] = OTELSpanKind(value).value
        elif field == "output_type":
            rule["output_type"] = value if value in ("span", "event") else "span"

    def add_attribute_mapping(self, rule_id: str):
        """Add empty attribute mapping to rule."""
        rule = self._find_rule_dict(rule_id)
        if not rule:
            return
        if "attribute_mappings" not in rule:
            rule["attribute_mappings"] = []
        rule["attribute_mappings"].append(
            {"mcs_property": "", "otel_attribute": "", "transform": "direct", "transform_value": ""}
        )

    def remove_attribute_mapping(self, rule_id: str, idx: int):
        """Remove attribute mapping from rule by index."""
        rule = self._find_rule_dict(rule_id)
        if not rule:
            return
        mappings = rule.get("attribute_mappings", [])
        if 0 <= idx < len(mappings):
            mappings.pop(idx)

    def update_attribute_mapping(
        self, rule_id: str, idx: int, field: str, value: str
    ):
        """Update a field on a specific attribute mapping."""
        rule = self._find_rule_dict(rule_id)
        if not rule:
            return
        mappings = rule.get("attribute_mappings", [])
        if 0 <= idx < len(mappings):
            am = mappings[idx]
            if field == "mcs_property":
                am["mcs_property"] = value
            elif field == "otel_attribute":
                am["otel_attribute"] = value
            elif field == "transform":
                am["transform"] = TransformType(value).value
            elif field == "transform_value":
                am["transform_value"] = value

    def _rebuild_connections(self, spec: MappingSpecification):
        """Rebuild connections and flow edges from a spec's rules."""
        self.connections = []
        for rule in spec.rules:
            mcs_label = rule.mcs_value_type if rule.mcs_value_type else rule.mcs_entity_type
            self.connections.append({
                "mcs_entity_type": mcs_label,
                "otel_target": rule.otel_operation_name.value,
                "rule_id": rule.rule_id,
            })
        self.flow_edges = _build_flow_edges(
            self.connections,
            [r.model_dump() for r in spec.rules] if spec.rules else None,
        )

    def load_defaults(self):
        """Populate from config/default_mapping.json, also populate connections and flow edges."""
        spec = load_default_mapping()
        self.mapping_spec = spec.model_dump()
        self._rebuild_connections(spec)
        return rx.toast("Default mapping loaded")

    def import_mapping(self, json_str: str):
        """Import mapping from JSON string."""
        try:
            data = json.loads(json_str)
            spec = MappingSpecification(**data)
            self.mapping_spec = spec.model_dump()
            self._rebuild_connections(spec)
            return rx.toast("Mapping imported")
        except (json.JSONDecodeError, pydantic.ValidationError) as e:
            from log import logger
            logger.warning("Invalid mapping JSON: {}", e)
            return rx.toast.error(f"Invalid mapping: {e}")
        except Exception as e:
            from log import logger
            logger.exception("Unexpected error importing mapping")
            return rx.toast.error(f"Import failed: {e}")

    def export_mapping(self) -> str:
        """Export mapping spec as JSON string."""
        spec = self._get_spec()
        return spec.model_dump_json(indent=2)

    def download_mapping(self):
        """Trigger download of mapping spec JSON."""
        data = self.export_mapping()
        return rx.download(data=data, filename="mapping_spec.json")
