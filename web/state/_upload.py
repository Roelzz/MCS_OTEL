import reflex as rx

from parsers import extract_entities, parse_bot_content, parse_transcript


class UploadMixin(rx.State, mixin=True):
    raw_content: str = ""
    transcript: dict = {}  # Serialized MCSTranscript
    entities: list[dict] = []  # Serialized MCSEntity list
    upload_error: str = ""
    bot_content: dict = {}  # Parsed botContent.yml metadata

    def set_raw_content(self, value: str):
        """Set the raw content text area value."""
        self.raw_content = value

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle file upload — read first file, parse transcript."""
        self.upload_error = ""
        if not files:
            self.upload_error = "No file selected"
            return
        file = files[0]
        content = await file.read()
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
        text = content.decode("utf-8")
        try:
            self.bot_content = parse_bot_content(text)
            # Re-extract entities with bot_content if transcript is loaded
            if self.transcript:
                t = parse_transcript(self.raw_content)
                entities = extract_entities(t, bot_content=self.bot_content)
                self.entities = [e.model_dump() for e in entities]
        except Exception as e:
            self.upload_error = f"botContent error: {e}"

    def _parse_content(self, content: str) -> bool:
        """Parse transcript content and extract entities. Returns True on success."""
        try:
            t = parse_transcript(content)
            self.raw_content = content
            self.transcript = t.model_dump()
            entities = extract_entities(
                t, bot_content=self.bot_content if self.bot_content else None
            )
            self.entities = [e.model_dump() for e in entities]
            self.upload_error = ""
            return True
        except Exception as e:
            self.upload_error = str(e)
            self.transcript = {}
            self.entities = []
            return False
