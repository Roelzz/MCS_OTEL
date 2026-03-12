import json

import reflex as rx

from converter import apply_mapping, to_otlp_json
from models import MappingSpecification, MCSEntity, OTELSpan


class PreviewMixin(rx.State, mixin=True):
    preview_spans: list[dict] = []  # Flattened span tree with depth
    preview_trace_id: str = ""
    preview_total_spans: int = 0
    preview_duration_ms: float = 0.0
    selected_span_id: str = ""

    def refresh_preview(self):
        """Apply mapping to entities, flatten tree, update state."""
        if not self.entities or not self.mapping_spec:
            self.preview_spans = []
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
        except Exception as e:
            from loguru import logger
            logger.error("Failed to refresh preview: {}", e)
            self.preview_spans = []

    def _flatten_tree(self, span: OTELSpan, depth: int) -> list[dict]:
        """Recursively flatten span tree with depth metadata, including events."""
        result = [
            {
                "span_id": span.span_id,
                "name": span.name,
                "kind": span.kind.value
                if hasattr(span.kind, "value")
                else str(span.kind),
                "start_time_ns": span.start_time_ns,
                "end_time_ns": span.end_time_ns,
                "duration_ms": (span.end_time_ns - span.start_time_ns) / 1_000_000,
                "depth": depth,
                "attributes": span.attributes,
                "status": span.status,
                "child_count": len(span.children),
                "is_event": False,
                "event_count": len(span.events),
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
                "depth": depth + 1,
                "attributes": evt.get("attributes", {}),
                "status": "OK",
                "child_count": 0,
                "is_event": True,
                "event_count": 0,
            })
        for child in span.children:
            result.extend(self._flatten_tree(child, depth + 1))
        return result

    def select_span(self, span_id: str):
        """Select a span to show detail."""
        self.selected_span_id = (
            span_id if self.selected_span_id != span_id else ""
        )

    def export_otlp_json(self) -> str:
        """Export OTLP JSON for download."""
        if not self.entities or not self.mapping_spec:
            return "{}"
        entities = [MCSEntity(**e) for e in self.entities]
        spec = MappingSpecification(**self.mapping_spec)
        trace = apply_mapping(entities, spec)
        service_name = spec.service_name
        otlp = to_otlp_json(trace, service_name)
        return json.dumps(otlp, indent=2)

    def download_otlp(self):
        """Trigger download of OTLP JSON."""
        data = self.export_otlp_json()
        return rx.download(data=data, filename="otlp_trace.json")
