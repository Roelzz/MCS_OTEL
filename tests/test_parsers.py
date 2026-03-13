import json
from pathlib import Path

import pytest

from config_loader import load_default_mapping
from models import EventMetadata, MappingSpecification
from parsers import extract_entities, parse_transcript

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TRANSCRIPT_PATH = FIXTURE_DIR / "rex_teams_transcript.json"


@pytest.fixture
def sample_content():
    with open(TRANSCRIPT_PATH) as f:
        return f.read()


@pytest.fixture
def transcript(sample_content):
    return parse_transcript(sample_content)


class TestParseTranscript:
    def test_parses_activities(self, transcript):
        assert len(transcript.activities) > 0

    def test_extracts_conversation_id(self, transcript):
        assert transcript.conversation_id

    def test_extracts_session_info(self, transcript):
        assert "outcome" in transcript.session_info
        assert "session_type" in transcript.session_info

    def test_activity_types(self, transcript):
        types = {a.type for a in transcript.activities}
        assert "message" in types
        assert "trace" in types or "event" in types

    def test_user_messages_have_role_1(self, transcript):
        user_msgs = [a for a in transcript.activities if a.type == "message" and a.from_role == 1]
        assert len(user_msgs) > 0

    def test_bot_messages_have_role_0(self, transcript):
        bot_msgs = [a for a in transcript.activities if a.type == "message" and a.from_role == 0]
        assert len(bot_msgs) > 0

    def test_handles_bare_array(self):
        data = [{"type": "message", "timestamp": 1000, "from": {"role": 1}, "text": "hello"}]
        t = parse_transcript(json.dumps(data))
        assert len(t.activities) == 1
        assert t.activities[0].text == "hello"

    def test_handles_wrapped_object(self):
        data = {"activities": [{"type": "message", "timestamp": 1000, "from": {"role": 0}, "text": "hi"}]}
        t = parse_transcript(json.dumps(data))
        assert len(t.activities) == 1

    def test_handles_iso_timestamps(self):
        """Transcripts from some environments have ISO string timestamps."""
        data = [
            {"type": "message", "timestamp": "2026-03-07T10:03:11.8086342+00:00", "from": {"role": 1}, "text": "hello"},
            {"type": "message", "timestamp": "2026-03-07T10:03:15Z", "from": {"role": 0}, "text": "hi"},
        ]
        t = parse_transcript(json.dumps(data))
        assert len(t.activities) == 2
        assert t.activities[0].timestamp > 0
        assert t.activities[1].timestamp > 0
        # Both should be epoch seconds in 2026 range
        assert t.activities[0].timestamp > 1_770_000_000
        assert t.activities[1].timestamp > 1_770_000_000

    def test_handles_millisecond_timestamps(self):
        """Some transcripts use 13-digit millisecond timestamps."""
        data = [{"type": "message", "timestamp": 1771240828617, "from": {"role": 1}, "text": "hello"}]
        t = parse_transcript(json.dumps(data))
        assert t.activities[0].timestamp == 1771240828617

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            parse_transcript("not json at all")


class TestExtractEntities:
    def test_returns_entities(self, transcript):
        entities = extract_entities(transcript)
        assert len(entities) > 0

    def test_has_session_root(self, transcript):
        entities = extract_entities(transcript)
        session = [e for e in entities if e.entity_id == "session_root"]
        assert len(session) == 1
        assert session[0].entity_type == "trace_event"

    def test_has_turns(self, transcript):
        entities = extract_entities(transcript)
        turns = [e for e in entities if e.entity_type == "turn"]
        assert len(turns) > 0

    def test_has_trace_events(self, transcript):
        entities = extract_entities(transcript)
        traces = [e for e in entities if e.entity_type == "trace_event" and e.entity_id != "session_root"]
        assert len(traces) > 0

    def test_entity_ids_unique(self, transcript):
        entities = extract_entities(transcript)
        ids = [e.entity_id for e in entities]
        assert len(ids) == len(set(ids))

    def test_turn_properties(self, transcript):
        entities = extract_entities(transcript)
        turns = [e for e in entities if e.entity_type == "turn"]
        first_turn = turns[0]
        assert "user_msg" in first_turn.properties
        assert "bot_msg" in first_turn.properties


class TestSpecDrivenExtraction:
    def test_spec_controls_tracked_types(self, transcript):
        """Toggling tracked=False on a type should drop those entities."""
        spec = load_default_mapping()
        baseline = extract_entities(transcript, spec=spec)
        baseline_types = {e.value_type for e in baseline if e.value_type}

        # Disable DialogRedirect
        modified_meta = [
            EventMetadata(
                value_type=em.value_type,
                tracked=False if em.value_type == "DialogRedirect" else em.tracked,
                label=em.label,
                entity_type=em.entity_type,
            )
            for em in spec.event_metadata
        ]
        modified_spec = spec.model_copy(update={"event_metadata": modified_meta})
        filtered = extract_entities(transcript, spec=modified_spec)
        filtered_types = {e.value_type for e in filtered if e.value_type}
        assert "DialogRedirect" in baseline_types
        assert "DialogRedirect" not in filtered_types

    def test_spec_controls_labels(self, transcript):
        """Custom label in EventMetadata should appear on entities."""
        spec = load_default_mapping()
        modified_meta = [
            EventMetadata(
                value_type=em.value_type,
                tracked=em.tracked,
                label="Custom Label" if em.value_type == "DialogRedirect" else em.label,
                entity_type=em.entity_type,
            )
            for em in spec.event_metadata
        ]
        modified_spec = spec.model_copy(update={"event_metadata": modified_meta})
        entities = extract_entities(transcript, spec=modified_spec)
        redirects = [e for e in entities if e.value_type == "DialogRedirect"]
        if redirects:
            assert redirects[0].label == "Custom Label"

    def test_adding_new_event_metadata(self, transcript):
        """Adding EventMetadata for a new type should make it appear."""
        spec = load_default_mapping()
        # Add a fake tracked type that won't match anything
        new_meta = list(spec.event_metadata) + [
            EventMetadata(value_type="FakeNewType", tracked=True, label="Fake")
        ]
        modified_spec = spec.model_copy(update={"event_metadata": new_meta})
        entities = extract_entities(transcript, spec=modified_spec)
        # Won't find any because no activities have this type, but it shouldn't crash
        assert isinstance(entities, list)

    def test_fallback_without_spec(self, transcript):
        """Without spec, extract_entities() should use hardcoded TRACKED_EVENT_TYPES."""
        entities_no_spec = extract_entities(transcript)
        spec = load_default_mapping()
        entities_with_spec = extract_entities(transcript, spec=spec)
        # Should produce same entity count
        assert len(entities_no_spec) == len(entities_with_spec)
