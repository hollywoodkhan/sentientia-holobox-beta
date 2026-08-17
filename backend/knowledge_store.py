import io
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import storage
from pypdf import PdfReader


logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


@dataclass(frozen=True)
class UploadedDocument:
    id: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    chunks: list[str]

    def metadata(self) -> dict:
        return {"id": self.id, "filename": self.filename, "content_type": self.content_type,
                "size": self.size, "uploaded_at": self.uploaded_at, "chunk_count": len(self.chunks)}


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _chunk_text(text: str, target_chars: int = 1_200) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for piece in [paragraph[i:i + target_chars] for i in range(0, len(paragraph), target_chars)]:
            candidate = f"{current}\n\n{piece}".strip()
            if current and len(candidate) > target_chars:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 20]


def extract_text(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only PDF, TXT, and Markdown files are supported")
    if extension == ".pdf":
        try:
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        except Exception as exc:
            raise ValueError("The PDF could not be read") from exc
    else:
        text = data.decode("utf-8", errors="replace")
    text = _clean_text(text)
    if not text:
        raise ValueError("No searchable text was found; scanned PDFs need OCR first")
    return text


class KnowledgeStore:
    def __init__(self) -> None:
        self.bucket_name = os.getenv("KNOWLEDGE_BUCKET", "").strip()
        self._client = storage.Client() if self.bucket_name else None
        self._documents: dict[str, dict[str, UploadedDocument]] = {}
        self._refreshed: dict[str, float] = {}
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return bool(self._client and self.bucket_name)

    def _bucket(self):
        if not self.enabled:
            raise RuntimeError("Document storage is not configured")
        return self._client.bucket(self.bucket_name)

    @staticmethod
    def _base(tenant_id: str) -> str:
        return f"tenants/{tenant_id}"

    def refresh(self, tenant_id: str, force: bool = False) -> bool:
        if not self.enabled:
            return False
        with self._lock:
            if not force and time.monotonic() - self._refreshed.get(tenant_id, 0) < 60:
                return False
            documents: dict[str, UploadedDocument] = {}
            prefix = f"{self._base(tenant_id)}/indexes/"
            for blob in self._client.list_blobs(self.bucket_name, prefix=prefix):
                if not blob.name.endswith(".json"):
                    continue
                try:
                    payload = json.loads(blob.download_as_text())
                    document = UploadedDocument(
                        id=payload["id"], filename=payload["filename"],
                        content_type=payload["content_type"], size=int(payload["size"]),
                        uploaded_at=payload["uploaded_at"], chunks=list(payload["chunks"]),
                    )
                    documents[document.id] = document
                except Exception:
                    logger.exception("Could not load knowledge index %s", blob.name)
            self._documents[tenant_id] = documents
            self._refreshed[tenant_id] = time.monotonic()
            return True

    def list_documents(self, tenant_id: str) -> list[dict]:
        self.refresh(tenant_id)
        with self._lock:
            docs = self._documents.get(tenant_id, {}).values()
            return [doc.metadata() for doc in sorted(docs, key=lambda item: item.uploaded_at, reverse=True)]

    def knowledge_data(self, tenant_id: str) -> dict:
        self.refresh(tenant_id)
        with self._lock:
            return {"uploaded_documents": {
                doc.id: {"filename": doc.filename, "passages": doc.chunks}
                for doc in self._documents.get(tenant_id, {}).values()
            }}

    def upload(self, tenant_id: str, filename: str, content_type: str, data: bytes) -> dict:
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("File exceeds the 10 MB limit")
        chunks = _chunk_text(extract_text(filename, data))
        if not chunks:
            raise ValueError("No usable knowledge passages were extracted")
        document_id = uuid.uuid4().hex
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)[:120]
        document = UploadedDocument(document_id, Path(filename).name,
                                    content_type or "application/octet-stream", len(data),
                                    datetime.now(timezone.utc).isoformat(), chunks)
        base = self._base(tenant_id)
        bucket = self._bucket()
        bucket.blob(f"{base}/originals/{document_id}/{safe_name}").upload_from_string(
            data, content_type=document.content_type)
        bucket.blob(f"{base}/indexes/{document_id}.json").upload_from_string(
            json.dumps({**document.metadata(), "chunks": chunks}, ensure_ascii=False),
            content_type="application/json")
        with self._lock:
            self._documents.setdefault(tenant_id, {})[document_id] = document
            self._refreshed[tenant_id] = time.monotonic()
        return document.metadata()

    def delete(self, tenant_id: str, document_id: str) -> bool:
        self.refresh(tenant_id, force=True)
        with self._lock:
            document = self._documents.get(tenant_id, {}).get(document_id)
        if not document:
            return False
        base = self._base(tenant_id)
        bucket = self._bucket()
        for blob in self._client.list_blobs(self.bucket_name, prefix=f"{base}/originals/{document_id}/"):
            blob.delete()
        bucket.blob(f"{base}/indexes/{document_id}.json").delete()
        with self._lock:
            self._documents.get(tenant_id, {}).pop(document_id, None)
            self._refreshed[tenant_id] = time.monotonic()
        return True
