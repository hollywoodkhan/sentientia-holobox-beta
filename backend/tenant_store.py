import json
import os
import re
import threading
import time
from pathlib import Path

from google.cloud import storage


TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_AVATAR_BYTES = 30 * 1024 * 1024


DEFAULT_SENTIENTIA = {
    "client_id": "sentientia",
    "company_name": "Sentientia",
    "assistant_name": "Sentientia AI",
    "tagline": "Intelligent Learning",
    "eyebrow": "Sentientia AI · Client prototype",
    "headline": "Intelligent learning starts here.",
    "description": "Talk with Sentientia's AI advisor about enterprise learning services, BlueTree LMS, Nudge AI, localization, and custom solutions.",
    "welcome_message": "Ready when you are.",
    "primary_color": "#76dc52",
    "secondary_color": "#071711",
    "persona": "You are Sentientia's official AI learning advisor. Speak as a knowledgeable representative using 'we' for Sentientia.",
    "tts_voice": "Charon",
    "tts_style": "a warm, confident Indian male learning consultant with a natural professional Mumbai accent",
    "logo_url": "",
        "avatar_url": "/assets/sentientia-avatar.glb?v=20260814-14",
    "suggested_questions": [
        "What does Sentientia do?",
        "How do BlueTree LMS and the Nudge AI platform work together?",
        "How can Sentientia support multilingual learning?"
    ],
    "enabled": True,
}


def validate_tenant_id(value: str) -> str:
    value = value.strip().lower()
    if not TENANT_ID_RE.fullmatch(value):
        raise ValueError("Client ID must contain 2-40 lowercase letters, numbers, or hyphens")
    return value


class TenantStore:
    def __init__(self) -> None:
        self.bucket_name = os.getenv("KNOWLEDGE_BUCKET", "").strip()
        self._client = storage.Client() if self.bucket_name else None
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return bool(self._client and self.bucket_name)

    def _bucket(self):
        if not self.enabled:
            raise RuntimeError("Tenant storage is not configured")
        return self._client.bucket(self.bucket_name)

    def get(self, tenant_id: str) -> dict | None:
        tenant_id = validate_tenant_id(tenant_id)
        with self._lock:
            cached = self._cache.get(tenant_id)
            if cached and time.monotonic() - cached[0] < 60:
                return dict(cached[1])
        if self.enabled:
            blob = self._bucket().blob(f"tenants/{tenant_id}/config.json")
            if blob.exists():
                data = json.loads(blob.download_as_text())
                with self._lock:
                    self._cache[tenant_id] = (time.monotonic(), data)
                return dict(data)
        if tenant_id == "sentientia":
            return dict(DEFAULT_SENTIENTIA)
        return None

    def save(self, data: dict) -> dict:
        tenant_id = validate_tenant_id(data["client_id"])
        data = {**data, "client_id": tenant_id}
        self._bucket().blob(f"tenants/{tenant_id}/config.json").upload_from_string(
            json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json")
        with self._lock:
            self._cache[tenant_id] = (time.monotonic(), data)
        return data

    def list(self) -> list[dict]:
        tenants: dict[str, dict] = {"sentientia": self.get("sentientia") or dict(DEFAULT_SENTIENTIA)}
        if self.enabled:
            for blob in self._client.list_blobs(self.bucket_name, prefix="tenants/"):
                if not blob.name.endswith("/config.json"):
                    continue
                try:
                    data = json.loads(blob.download_as_text())
                    tenants[data["client_id"]] = data
                except Exception:
                    continue
        return sorted(tenants.values(), key=lambda item: item.get("company_name", "").lower())

    def delete(self, tenant_id: str) -> bool:
        tenant_id = validate_tenant_id(tenant_id)
        if not self.enabled:
            return False
        prefix = f"tenants/{tenant_id}/"
        blobs = list(self._client.list_blobs(self.bucket_name, prefix=prefix))
        if not blobs:
            return False
        for blob in blobs:
            blob.delete()
        with self._lock:
            self._cache.pop(tenant_id, None)
        return True

    def upload_asset(self, tenant_id: str, kind: str, filename: str, content_type: str, data: bytes) -> str:
        tenant_id = validate_tenant_id(tenant_id)
        extension = Path(filename).suffix.lower()
        if kind == "logo":
            if extension not in {".png", ".jpg", ".jpeg", ".webp", ".svg"} or len(data) > MAX_LOGO_BYTES:
                raise ValueError("Logo must be PNG, JPG, WebP, or SVG and no larger than 5 MB")
        elif kind == "avatar":
            if extension not in {".glb", ".vrm", ".bin"} or len(data) > MAX_AVATAR_BYTES:
                raise ValueError("Avatar must be GLB, VRM, or BIN and no larger than 30 MB")
        else:
            raise ValueError("Unsupported asset type")
        safe_extension = extension if extension else ".bin"
        blob_name = f"tenants/{tenant_id}/assets/{kind}{safe_extension}"
        self._bucket().blob(blob_name).upload_from_string(data, content_type=content_type or "application/octet-stream")
        return f"/clients/{tenant_id}/assets/{kind}"

    def get_asset(self, tenant_id: str, kind: str) -> tuple[bytes, str] | None:
        tenant_id = validate_tenant_id(tenant_id)
        prefix = f"tenants/{tenant_id}/assets/{kind}"
        blobs = list(self._client.list_blobs(self.bucket_name, prefix=prefix, max_results=1)) if self.enabled else []
        if not blobs:
            return None
        blob = blobs[0]
        return blob.download_as_bytes(), blob.content_type or "application/octet-stream"
