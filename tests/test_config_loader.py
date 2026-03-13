"""Tests for config_loader: load/save MappingSpecification from JSON."""

from pathlib import Path

import pytest

from config_loader import DEFAULT_MAPPING_PATH, load_default_mapping, load_mapping_spec, save_mapping_spec
from models import MappingSpecification


class TestLoadDefaultMapping:
    def test_loads_successfully(self):
        spec = load_default_mapping()
        assert isinstance(spec, MappingSpecification)

    def test_has_rules(self):
        spec = load_default_mapping()
        assert len(spec.rules) == 28

    def test_has_event_metadata(self):
        spec = load_default_mapping()
        assert len(spec.event_metadata) == 26

    def test_has_enrichment_rules(self):
        spec = load_default_mapping()
        assert len(spec.enrichment_rules) == 16

    def test_rule_ids_unique(self):
        spec = load_default_mapping()
        ids = [r.rule_id for r in spec.rules]
        assert len(ids) == len(set(ids))

    def test_has_root_rule(self):
        spec = load_default_mapping()
        root_rules = [r for r in spec.rules if r.is_root]
        assert len(root_rules) == 1

    def test_event_metadata_all_tracked(self):
        spec = load_default_mapping()
        assert all(em.tracked for em in spec.event_metadata)

    def test_event_metadata_has_labels(self):
        spec = load_default_mapping()
        labeled = [em for em in spec.event_metadata if em.label]
        assert len(labeled) == len(spec.event_metadata)


class TestLoadMappingSpec:
    def test_loads_default_path(self):
        spec = load_mapping_spec(DEFAULT_MAPPING_PATH)
        assert isinstance(spec, MappingSpecification)
        assert len(spec.rules) == 28

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_mapping_spec(tmp_path / "nonexistent.json")


class TestSaveMappingSpec:
    def test_round_trip(self, tmp_path):
        spec = load_default_mapping()
        out_path = tmp_path / "test_spec.json"
        save_mapping_spec(spec, out_path)

        loaded = load_mapping_spec(out_path)
        assert len(loaded.rules) == len(spec.rules)
        assert len(loaded.event_metadata) == len(spec.event_metadata)
        assert len(loaded.enrichment_rules) == len(spec.enrichment_rules)

    def test_creates_parent_dirs(self, tmp_path):
        out_path = tmp_path / "nested" / "dir" / "spec.json"
        spec = MappingSpecification(rules=[])
        save_mapping_spec(spec, out_path)
        assert out_path.exists()


class TestFallback:
    def test_fallback_when_no_json(self, tmp_path, monkeypatch):
        """When default_mapping.json is missing, falls back to generate_default_mapping()."""
        monkeypatch.setattr("config_loader.DEFAULT_MAPPING_PATH", tmp_path / "missing.json")
        spec = load_default_mapping()
        assert isinstance(spec, MappingSpecification)
        assert len(spec.rules) >= 4
