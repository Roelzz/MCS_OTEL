import reflex as rx

from parsers import extract_entities, parse_transcript


class UploadMixin:
    raw_content: str = ""
    transcript: dict = {}  # Serialized MCSTranscript
    entities: list[dict] = []  # Serialized MCSEntity list
    upload_error: str = ""

    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle file upload — read first file, parse transcript."""
        self.upload_error = ""
        if not files:
            self.upload_error = "No file selected"
            return
        file = files[0]
        content = await file.read()
        text = content.decode("utf-8")
        self._parse_content(text)

    def handle_paste(self, content: str):
        """Handle pasted JSON content."""
        self.upload_error = ""
        self._parse_content(content)

    def _parse_content(self, content: str):
        """Parse transcript content and extract entities."""
        try:
            t = parse_transcript(content)
            self.raw_content = content
            self.transcript = t.model_dump()
            entities = extract_entities(t)
            self.entities = [e.model_dump() for e in entities]
            self.upload_error = ""
        except Exception as e:
            self.upload_error = str(e)
            self.transcript = {}
            self.entities = []
