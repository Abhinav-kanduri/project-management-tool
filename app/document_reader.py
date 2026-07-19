from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

MAX_INPUT_CHARACTERS = 100_000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def _extract_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Supported document types are .txt, .md, .pdf, and .docx.",
        )
    try:
        if extension in {".txt", ".md"}:
            return content.decode("utf-8")
        if extension == ".pdf":
            return "\n".join(
                page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages
            )
        return "\n".join(
            paragraph.text for paragraph in Document(BytesIO(content)).paragraphs
        )
    except Exception as error:
        raise HTTPException(status_code=422, detail="The document could not be read.") from error


async def source_text(text: str | None, file: UploadFile | None) -> str:
    clean_text = text.strip() if text else ""
    if bool(clean_text) == bool(file):
        raise HTTPException(status_code=422, detail="Provide exactly one of text or file.")
    if file:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        await file.close()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Document exceeds the 5 MB limit.")
        clean_text = _extract_text(file.filename or "", content).strip()
    if not clean_text:
        raise HTTPException(status_code=422, detail="The supplied content contains no readable text.")
    if len(clean_text) > MAX_INPUT_CHARACTERS:
        raise HTTPException(status_code=413, detail="Extracted text exceeds 100,000 characters.")
    return clean_text
