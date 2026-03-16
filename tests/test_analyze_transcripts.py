"""Tests for analyze_transcripts suggestion helpers."""

from analyze_transcripts import suggest_attribute_mappings_json, suggest_mapping_rule_json


class TestJsonSuggestions:
    def test_suggest_mapping_rule_json(self):
        result = suggest_mapping_rule_json("TestType", {"prop1", "prop2"})
        assert result["rule_id"] == "test_type"
        assert result["mcs_value_type"] == "TestType"
        assert len(result["attribute_mappings"]) == 2
        assert result["attribute_mappings"][0]["mcs_property"] == "prop1"

    def test_suggest_attribute_mappings_json(self):
        result = suggest_attribute_mappings_json({"a", "b", "timestamp"}, {"a"})
        assert len(result) == 1
        assert result[0]["mcs_property"] == "b"
