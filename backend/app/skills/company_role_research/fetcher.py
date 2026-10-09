from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.skills.company_role_research.evidence import clean_html_text
from app.skills.company_role_research.schemas import FetchedSource, WebSearchSource


Resolver = Callable[..., list[tuple]]


class UnsafeSourceURL(ValueError):
    pass


class SourceFetcher:
    """Fetches bounded public HTML and validates every redirect against SSRF."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver = socket.getaddrinfo,
        timeout_seconds: float = 8.0,
        max_response_bytes: int = 2 * 1024 * 1024,
        max_text_length: int = 20_000,
        min_text_length: int = 80,
        max_redirects: int = 3,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_text_length = max_text_length
        self.min_text_length = max(1, min_text_length)
        self.max_redirects = max_redirects
        self.resolver = resolver
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )

    def fetch_source(self, source: WebSearchSource) -> FetchedSource:
        source_id = self._source_id(source.url)
        current_url = source.url
        try:
            for redirect_count in range(self.max_redirects + 1):
                self._validate_public_url(current_url)
                with self.client.stream(
                    "GET",
                    current_url,
                    headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "JobHunterResearch/1.0"},
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return self._result(source, source_id, "failed", error="redirect_without_location")
                        if redirect_count >= self.max_redirects:
                            return self._result(source, source_id, "failed", error="too_many_redirects")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code >= 400:
                        return self._result(
                            source,
                            source_id,
                            "failed",
                            content_type=response.headers.get("content-type"),
                            error=f"http_{response.status_code}",
                        )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        return self._result(
                            source,
                            source_id,
                            "skipped",
                            content_type=content_type or None,
                            error="unsupported_content_type",
                        )
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self.max_response_bytes:
                        return self._result(
                            source,
                            source_id,
                            "skipped",
                            content_type=content_type,
                            error="response_too_large",
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_response_bytes:
                            return self._result(
                                source,
                                source_id,
                                "skipped",
                                content_type=content_type,
                                error="response_too_large",
                            )
                    encoding = response.encoding or "utf-8"
                    try:
                        html = bytes(body).decode(encoding, errors="replace")
                    except LookupError:
                        html = bytes(body).decode("utf-8", errors="replace")
                    text = clean_html_text(html, max_length=self.max_text_length)
                    if not text:
                        return self._result(
                            source,
                            source_id,
                            "unavailable",
                            content_type=content_type,
                            error="empty_content",
                        )
                    if len(text) < self.min_text_length:
                        return self._result(
                            source,
                            source_id,
                            "unavailable",
                            content_type=content_type,
                            error="insufficient_content",
                        )
                    return self._result(
                        source,
                        source_id,
                        "success",
                        content_type=content_type,
                        extracted_text=text,
                    )
        except UnsafeSourceURL as exc:
            error = "redirect_rejected" if current_url != source.url else str(exc)
            return self._result(source, source_id, "skipped", error=error)
        except httpx.TimeoutException:
            return self._result(source, source_id, "failed", error="timeout")
        except (httpx.HTTPError, UnicodeError, ValueError, OSError):
            return self._result(source, source_id, "failed", error="fetch_error")
        return self._result(source, source_id, "failed", error="fetch_error")

    def failed_result(self, source: WebSearchSource, error: str = "fetch_error") -> FetchedSource:
        return self._result(source, self._source_id(source.url), "failed", error=error)

    def _validate_public_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise UnsafeSourceURL("unsupported_url_scheme")
        if not parsed.hostname or parsed.username or parsed.password:
            raise UnsafeSourceURL("invalid_url_host")
        if parsed.port and parsed.port not in {80, 443}:
            raise UnsafeSourceURL("unsupported_url_port")
        hostname = parsed.hostname.rstrip(".").casefold()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise UnsafeSourceURL("localhost_not_allowed")
        try:
            addresses = {ipaddress.ip_address(hostname)}
        except ValueError:
            try:
                records = self.resolver(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            except socket.gaierror as exc:
                raise UnsafeSourceURL("dns_resolution_failed") from exc
            addresses = {ipaddress.ip_address(record[4][0]) for record in records}
        if not addresses or any(not self._is_public_address(address) for address in addresses):
            raise UnsafeSourceURL("non_public_address")

    @staticmethod
    def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return not any((
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ))

    @staticmethod
    def _source_id(url: str) -> str:
        return f"source_{sha256(url.encode()).hexdigest()[:20]}"

    @staticmethod
    def _result(
        source: WebSearchSource,
        source_id: str,
        status: str,
        *,
        content_type: str | None = None,
        extracted_text: str = "",
        error: str | None = None,
    ) -> FetchedSource:
        return FetchedSource(
            source_id=source_id,
            title=source.title,
            url=source.url,
            source_type=source.source_type,
            published_at=source.published_at,
            content_type=content_type,
            extracted_text=extracted_text,
            fetch_status=status,
            error=error,
        )
