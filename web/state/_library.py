"""Mapping library state mixin — scan, load, save mappings from config/mappings/."""

import json

import pydantic
import reflex as rx
from log import logger

from config_loader import list_mappings, load_mapping_by_name, save_mapping_spec, MAPPINGS_DIR
from models import MappingSpecification


class LibraryMixin(rx.State, mixin=True):
    available_mappings: list[dict] = []
    save_as_name: str = ""

    def scan_mappings(self):
        self.available_mappings = list_mappings()

    def load_library_mapping(self, name: str):
        """Load a mapping from the library by name."""
        try:
            spec = load_mapping_by_name(name)
            self.mapping_spec = spec.model_dump()
            self._rebuild_connections(spec)
            self.current_step = "connections"
            return rx.toast(f"Loaded mapping: {name}")
        except Exception as e:
            logger.error("Failed to load mapping '{}': {}", name, e)
            return rx.toast.error(f"Failed to load: {e}")

    def save_mapping_as(self):
        """Save current mapping spec to the library."""
        name = self.save_as_name.strip()
        if not name:
            return rx.toast.error("Enter a name for the mapping")
        if not self.mapping_spec:
            return rx.toast.error("No mapping to save")
        try:
            spec = MappingSpecification(**self.mapping_spec)
            path = MAPPINGS_DIR / f"{name}.json"
            save_mapping_spec(spec, path)
            self.scan_mappings()
            return rx.toast(f"Saved mapping: {name}")
        except Exception as e:
            logger.error("Failed to save mapping '{}': {}", name, e)
            return rx.toast.error(f"Save failed: {e}")

    async def handle_mapping_file_upload(self, files: list[rx.UploadFile]):
        """Upload a .json mapping file and load it."""
        if not files:
            return rx.toast.error("No file selected")
        file = files[0]
        content = await file.read()
        text = content.decode("utf-8")
        try:
            data = json.loads(text)
            spec = MappingSpecification(**data)
            self.mapping_spec = spec.model_dump()
            self._rebuild_connections(spec)
            self.current_step = "connections"
            return rx.toast("Mapping imported from file")
        except (json.JSONDecodeError, pydantic.ValidationError) as e:
            logger.warning("Invalid mapping file: {}", e)
            return rx.toast.error(f"Invalid mapping: {e}")

    def load_blank_mapping(self):
        """Initialize an empty MappingSpecification."""
        spec = MappingSpecification()
        self.mapping_spec = spec.model_dump()
        self._rebuild_connections(spec)
        self.current_step = "connections"
        return rx.toast("Started with blank mapping")
