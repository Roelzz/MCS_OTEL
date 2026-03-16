import json

import reflex as rx
import yaml

from parsers import extract_entities, parse_bot_content, parse_transcript

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class UploadMixin(rx.State, mixin=True):
    paste_content: str = ""  # Frontend textarea binding
    _raw_content: str = ""  # Backend-only, not synced to client
    transcript: dict = {}  # Serialized MCSTranscript
    entities: list[dict] = []  # Serialized MCSEntity list
    upload_error: str = ""
    bot_content: dict = {}  # Parsed botContent.yml metadata

    # Entity browser state
    entity_type_filter: str = ""
    selected_entity_id: str = ""

    @rx.var(cache=True)
    def entity_types_summary(self) -> list[dict]:
        """Group entities by value_type, count per type, list unique property keys."""
        if not self.entities:
            return []
        type_map: dict[str, dict] = {}
        for e in self.entities:
            vt = e.get("value_type", "") or e.get("entity_type", "unknown")
            if vt not in type_map:
                type_map[vt] = {"value_type": vt, "count": 0, "property_keys": set()}
            type_map[vt]["count"] += 1
            for k in e.get("properties", {}).keys():
                type_map[vt]["property_keys"].add(k)
        result = []
        for vt, info in sorted(type_map.items()):
            keys = sorted(info["property_keys"])
            result.append({
                "value_type": info["value_type"],
                "count": info["count"],
                "property_keys": keys,
                "top_keys": keys[:5],
            })
        return result

    @rx.var(cache=True)
    def filtered_entities(self) -> list[dict]:
        """Entities filtered by entity_type_filter, with pre-computed property_count."""
        if not self.entities:
            return []
        source = self.entities
        if self.entity_type_filter:
            source = [
                e for e in source
                if (e.get("value_type", "") or e.get("entity_type", "")) == self.entity_type_filter
            ]
        # Pre-compute property_count so the component doesn't need to access nested dict
        return [
            {**e, "property_count": len(e.get("properties", {}))}
            for e in source
        ]

    @rx.var
    def selected_entity_detail(self) -> list[dict]:
        """Flat key-value list of all properties for selected entity, with enrichment tags."""
        if not self.selected_entity_id or not self.entities:
            return []
        enriched_keys = set(getattr(self, "enrichment_target_keys", []))
        for e in self.entities:
            if e.get("entity_id") == self.selected_entity_id:
                props = e.get("properties", {})
                return [
                    {
                        "key": k,
                        "value": str(v) if v is not None else "",
                        "is_enriched": k in enriched_keys,
                    }
                    for k, v in sorted(props.items())
                ]
        return []

    @rx.var(cache=True)
    def session_context(self) -> dict:
        """Transcript session_info for the session dashboard."""
        if not self.transcript:
            return {}
        return self.transcript.get("session_info", {})

    @rx.var(cache=True)
    def has_session_context(self) -> bool:
        return bool(self.session_context)

    @rx.var(cache=True)
    def entity_type_distribution(self) -> list[dict]:
        """Entity count per value_type for charting."""
        if not self.entities:
            return []
        counts: dict[str, int] = {}
        for e in self.entities:
            vt = e.get("value_type", "") or e.get("entity_type", "unknown")
            counts[vt] = counts.get(vt, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    @rx.var(cache=True)
    def conversation_turns(self) -> list[dict]:
        """Entities representing conversation turns, ordered by turn_index."""
        if not self.entities:
            return []
        turns = []
        for e in self.entities:
            if e.get("entity_type") != "turn":
                continue
            props = e.get("properties", {})
            turns.append({
                "turn_index": props.get("turn_index", 0),
                "user_msg": props.get("user_text", ""),
                "bot_msg": props.get("bot_text", ""),
                "topic_name": props.get("topic_name", ""),
                "action_type": props.get("action_type", ""),
                "is_greeting": props.get("is_greeting", False),
            })
        return sorted(turns, key=lambda t: t.get("turn_index", 0))

    def set_entity_type_filter(self, value_type: str):
        """Set entity type filter, or clear if same type clicked again."""
        if self.entity_type_filter == value_type:
            self.entity_type_filter = ""
        else:
            self.entity_type_filter = value_type
        self.selected_entity_id = ""

    def select_entity(self, entity_id: str):
        """Select an entity to show its detail."""
        self.selected_entity_id = (
            entity_id if self.selected_entity_id != entity_id else ""
        )

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle file upload — read first file, parse transcript."""
        self.upload_error = ""
        if not files:
            self.upload_error = "No file selected"
            return
        file = files[0]
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            self.upload_error = f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 10 MB."
            return
        text = content.decode("utf-8")
        if self._parse_content(text):
            return rx.toast("Transcript parsed successfully")

    def handle_paste(self, content: str):
        """Handle pasted JSON content."""
        self.upload_error = ""
        if self._parse_content(content):
            return rx.toast("Transcript parsed successfully")

    async def handle_bot_content_upload(self, files: list[rx.UploadFile]):
        """Handle botContent.yml upload — parse and re-extract entities."""
        self.upload_error = ""
        if not files:
            return
        file = files[0]
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            self.upload_error = f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 10 MB."
            return
        text = content.decode("utf-8")
        try:
            self.bot_content = parse_bot_content(text)
            if self.transcript:
                spec = None
                if self.mapping_spec:
                    from models import MappingSpecification

                    spec = MappingSpecification(**self.mapping_spec)
                t = parse_transcript(self._raw_content, spec=spec)
                entities = extract_entities(
                    t, bot_content=self.bot_content, spec=spec
                )
                self.entities = [e.model_dump() for e in entities]
        except (yaml.YAMLError, ValueError) as e:
            self.upload_error = f"botContent error: {e}"
        except Exception as e:
            from log import logger
            logger.exception("Unexpected error processing botContent")
            self.upload_error = f"Unexpected error: {e}"

    def _parse_content(self, content: str) -> bool:
        """Parse transcript content and extract entities. Returns True on success."""
        if len(content) > MAX_UPLOAD_SIZE:
            self.upload_error = f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum is 10 MB."
            return False
        try:
            spec = None
            if self.mapping_spec:
                from models import MappingSpecification

                spec = MappingSpecification(**self.mapping_spec)
            t = parse_transcript(content, spec=spec)
            self._raw_content = content
            self.transcript = t.model_dump()
            entities = extract_entities(
                t,
                bot_content=self.bot_content if self.bot_content else None,
                spec=spec,
            )
            self.entities = [e.model_dump() for e in entities]
            self.upload_error = ""
            return True
        except (json.JSONDecodeError, ValueError) as e:
            self.upload_error = str(e)
            self.transcript = {}
            self.entities = []
            return False
        except Exception as e:
            from log import logger
            logger.exception("Unexpected error parsing content")
            self.upload_error = f"Unexpected error: {e}"
            self.transcript = {}
            self.entities = []
            return False
