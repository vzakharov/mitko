"""CV text extraction from PDF files."""

import io

from sqlalchemy.ext.asyncio import AsyncSession


class CVParserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def extract_text(self, file_bytes: bytes) -> str:
        """Extract text from PDF bytes. Raises ValueError on parse errors."""
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(page.strip() for page in pages if page.strip())
        if not text:
            raise ValueError("No extractable text found in PDF")
        return text
