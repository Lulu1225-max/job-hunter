from __future__ import annotations

from urllib.parse import quote

import httpx

from app.core.config import settings


class StorageError(RuntimeError):
    pass


class ResumeStorage:
    def _configuration(self) -> tuple[str, str, str]:
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise StorageError("Supabase Storage is not configured")
        return (
            settings.supabase_url.rstrip("/"),
            settings.supabase_secret_key,
            settings.supabase_resume_bucket,
        )

    def upload(self, path: str, content: bytes, content_type: str) -> str:
        base_url, service_key, bucket = self._configuration()
        encoded_path = quote(path, safe="/")
        response = httpx.post(
            f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{encoded_path}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            content=content,
            timeout=30,
        )
        if response.status_code not in {200, 201}:
            raise StorageError(f"Supabase Storage upload failed ({response.status_code})")
        return path

    def delete(self, path: str) -> None:
        base_url, service_key, bucket = self._configuration()
        response = httpx.request(
            "DELETE",
            f"{base_url}/storage/v1/object/{quote(bucket, safe='')}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "Content-Type": "application/json",
            },
            json={"prefixes": [path]},
            timeout=15,
        )
        if response.status_code not in {200, 204}:
            raise StorageError(f"Supabase Storage delete failed ({response.status_code})")


resume_storage = ResumeStorage()
