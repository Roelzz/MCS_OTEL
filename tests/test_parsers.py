import json
from pathlib import Path

import pytest

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
