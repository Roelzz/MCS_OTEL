import json

import reflex as rx

from converter import apply_mapping, to_otlp_json
from models import MappingSpecification, MCSEntity, OTELSpan


class PreviewMixin(rx.State, mixin=True):
    preview_spans: list[dict] = []  # Flattened span tree with depth
    preview_trace_id: str = ""
    preview_total_spans: int = 0
    preview_duration_ms: float = 0.0
    preview_total_events: int = 0
    selected_span_id: str = ""
    span_filter_text: str = ""
    preview_loading: bool = False
    # Per-rule match stats after preview
    _rule_stats: list[dict] = []
    _cached_otlp: str = ""

    @rx.var(cache=True)
    def total_span_count(self) -> int:
        return len(self.preview_spans)

    @rx.var(cache=True)
    def filtered_preview_spans(self) -> list[dict]:
        if not self.span_filter_text:
            return self.preview_spans
        q = self.span_filter_text.lower()
        matched_ids: set[str] = set()
        for span in self.preview_spans:
            if q in span.get("name", "").lower():
                matched_ids.add(span.get("span_id", ""))
        # Include parent spans to maintain tree context
        result = []
        parent_stack: list[str] = []
        for span in self.preview_spans:
            depth = span.get("depth", 0)
            span_id = span.get("span_id", "")
            # Maintain parent stack
            while len(parent_stack) > depth:
                parent_stack.pop()
            if span_id in matched_ids:
                # Add missing ancestors
                for pi, ps in enumerate(parent_stack):
                    if not any(r.get("span_id") == ps for r in result):
                        for orig in self.preview_spans:
                            if orig.get("span_id") == ps:
                                result.append(orig)
                                break
                result.append(span)
            if len(parent_stack) <= depth:
                parent_stack.append(span_id)
            else:
                parent_stack[depth] = span_id
        return result

    @rx.var
    def selected_span_detail(self) -> dict:
        """Return full span dict for the selected span."""
        if not self.selected_span_id:
            return {}
        for span in self.preview_spans:
            if span.get("span_id") == self.selected_span_id:
                return span
        return {}

    @rx.var
    def selected_span_attrs(self) -> list[dict]:
        """Attribute list for the selected span as [{key, value}]."""
        detail = self.selected_span_detail
        if not detail:
            return []
        attrs = detail.get("attributes", {})
        return [
            {"key": k, "value": str(v) if v else ""}
            for k, v in sorted(attrs.items())
        ]

    @rx.var
    def rule_stats(self) -> list[dict]:
        return self._rule_stats

    def refresh_preview(self):
        """Apply mapping to entities, flatten tree, update state."""
        self.preview_loading = True
        if not self.entities or not self.mapping_spec:
            self.preview_spans = []
            self._rule_stats = []
            self._cached_otlp = ""
            self.preview_loading = False
            return

        try:
            entities = [MCSEntity(**e) for e in self.entities]
            spec = MappingSpecification(**self.mapping_spec)
            trace = apply_mapping(entities, spec)

            self.preview_trace_id = trace.trace_id
            self.preview_total_spans = trace.total_spans
            self.preview_duration_ms = trace.duration_ms

            # Flatten tree with depth metadata
            self.preview_spans = self._flatten_tree(trace.root_span, 0)
            self.preview_total_events = sum(
                1 for s in self.preview_spans if s.get("is_event")
            )

            # Compute per-rule match stats
            self._rule_stats = self._compute_rule_stats(spec, self.preview_spans)

            # Cache OTLP JSON for export
            otlp = to_otlp_json(trace, spec.service_name)
            self._cached_otlp = json.dumps(otlp, indent=2)
        except (ValueError, KeyError) as e:
            from log import logger
            logger.warning("Preview refresh failed: {}", e)
            self.preview_spans = []
            self._rule_stats = []
            self._cached_otlp = ""
        except Exception as e:
            from log import logger
            logger.exception("Unexpected error refreshing preview")
            self.preview_spans = []
            self._rule_stats = []
            self._cached_otlp = ""
        finally:
            self.preview_loading = False

    def _flatten_tree(self, span: OTELSpan, depth: int) -> list[dict]:
        """Recursively flatten span tree with depth metadata, including events."""
        # Detect generating rule from gen_ai.operation.name attribute
        rule_id = ""
        attrs = span.attributes
        op_name = attrs.get("gen_ai.operation.name", "")
        if op_name and self.mapping_spec:
            for rule in self.mapping_spec.get("rules", []):
                if rule.get("otel_operation_name") == op_name:
                    # Match by span name heuristic
                    tpl = rule.get("span_name_template", "")
                    if tpl and span.name.startswith(tpl.split("{")[0].strip()):
                        rule_id = rule.get("rule_id", "")
                        break

        dur_ms = (span.end_time_ns - span.start_time_ns) / 1_000_000
        if dur_ms == 0:
            dur_display = "—"
        elif dur_ms < 1:
            dur_display = "< 1 ms"
        elif dur_ms >= 1000:
            dur_display = f"{dur_ms / 1000:.1f}s"
        else:
            dur_display = f"{dur_ms:.0f} ms"

        result = [
            {
                "span_id": span.span_id,
                "name": span.name,
                "kind": span.kind.value
                if hasattr(span.kind, "value")
                else str(span.kind),
                "start_time_ns": span.start_time_ns,
                "end_time_ns": span.end_time_ns,
                "duration_ms": dur_ms,
                "duration_display": dur_display,
                "depth": depth,
                "attributes": span.attributes,
                "status": span.status,
                "child_count": len(span.children),
                "is_event": False,
                "event_count": len(span.events),
                "rule_id": rule_id,
                "index": 0,
            }
        ]
        # Show events on this span (indented one level deeper)
        for evt in span.events:
            result.append({
                "span_id": f"{span.span_id}_evt_{evt.get('name', '')}",
                "name": evt.get("name", "event"),
                "kind": "EVENT",
                "start_time_ns": evt.get("timeUnixNano", 0),
                "end_time_ns": evt.get("timeUnixNano", 0),
                "duration_ms": 0.0,
                "duration_display": "—",
                "depth": depth + 1,
                "attributes": evt.get("attributes", {}),
                "status": "OK",
                "child_count": 0,
                "is_event": True,
                "event_count": 0,
                "rule_id": "",
                "index": 0,
            })
        for child in span.children:
            result.extend(self._flatten_tree(child, depth + 1))

        # Assign index for zebra striping (only at top-level call, depth==0)
        if depth == 0:
            for i, item in enumerate(result):
                item["index"] = i

        return result

    def _compute_rule_stats(
        self, spec: MappingSpecification, flat_spans: list[dict]
    ) -> list[dict]:
        """Compute per-rule match count and attribute fill rate."""
        stats: list[dict] = []
        for rule in spec.rules:
            rule_id = rule.rule_id
            op_name = (
                rule.otel_operation_name.value
                if hasattr(rule.otel_operation_name, "value")
                else str(rule.otel_operation_name)
            )
            tpl_prefix = rule.span_name_template.split("{")[0].strip() if rule.span_name_template else ""

            # Count matching spans
            matched_spans = []
            for s in flat_spans:
                if s.get("is_event"):
                    continue
                s_op = s.get("attributes", {}).get("gen_ai.operation.name", "")
                if s_op == op_name and tpl_prefix and s.get("name", "").startswith(tpl_prefix):
                    matched_spans.append(s)

            match_count = len(matched_spans)

            # Compute attribute fill rate across matched spans
            expected_attrs = len(rule.attribute_mappings)
            if expected_attrs > 0 and matched_spans:
                filled_total = 0
                expected_total = 0
                for s in matched_spans:
                    attrs = s.get("attributes", {})
                    for am in rule.attribute_mappings:
                        expected_total += 1
                        val = attrs.get(am.otel_attribute, "")
                        if val:
                            filled_total += 1
                fill_rate = round(filled_total / expected_total * 100, 1) if expected_total > 0 else 0.0
            else:
                fill_rate = 0.0

            vt = rule.mcs_value_type or rule.mcs_entity_type
            stats.append({
                "rule_id": rule_id,
                "value_type": vt,
                "otel_op": op_name,
                "match_count": match_count,
                "attr_count": expected_attrs,
                "fill_rate": fill_rate,
            })
        return stats

    def select_span(self, span_id: str):
        """Select a span to show detail."""
        self.selected_span_id = (
            span_id if self.selected_span_id != span_id else ""
        )

    def export_otlp_json(self) -> str:
        """Export OTLP JSON for download."""
        if self._cached_otlp:
            return self._cached_otlp
        if not self.entities or not self.mapping_spec:
            return "{}"
        entities = [MCSEntity(**e) for e in self.entities]
        spec = MappingSpecification(**self.mapping_spec)
        trace = apply_mapping(entities, spec)
        otlp = to_otlp_json(trace, spec.service_name)
        return json.dumps(otlp, indent=2)

    def download_otlp(self):
        """Trigger download of OTLP JSON."""
        data = self.export_otlp_json()
        return rx.download(data=data, filename="otlp_trace.json")
