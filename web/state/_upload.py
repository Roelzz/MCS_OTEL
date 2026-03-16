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
