import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import httpx
from dotenv import load_dotenv

from app.services.llm_client import ROOT_DIR

load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / "backend" / ".env")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float | None = None


@dataclass
class WebSearchResponse:
    available: bool
    results: list[SearchResult] = field(default_factory=list)
    attempted: bool = False
    success: bool = False
    elapsed_time_ms: int = 0
    fallback_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None


class WebSearchClient:
    def __init__(self) -> None:
        self.provider = os.getenv("SEARCH_PROVIDER", "generic").strip().lower()
        self.api_key = self._normalize_api_key(os.getenv("SEARCH_API_KEY", ""))
        self.base_url = (os.getenv("SEARCH_BASE_URL", "") or self._default_base_url()).strip().rstrip("/")
        self.timeout = float(os.getenv("SEARCH_TIMEOUT", "15") or "15")
        self.max_results = int(os.getenv("SEARCH_MAX_RESULTS", "5") or "5")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def status(self) -> dict:
        return {
            "search_provider": self.provider,
            "api_key_configured": bool(self.api_key),
            "base_url_configured": bool(self.base_url),
            "timeout": self.timeout,
            "max_results": self.max_results,
            "enabled": self.is_available,
        }

    def test_connection(self, query: str) -> dict:
        response = self.search(query, limit=min(self.max_results, 5))
        return {
            "success": response.success,
            "provider": self.provider,
            "query": query,
            "result_count": len(response.results),
            "results_preview": [
                {"title": item.title, "url": item.url, "snippet": item.snippet[:180]}
                for item in response.results[:3]
            ],
            "error_type": response.error_type,
            "error_message": response.error_message or response.fallback_reason,
        }

    def search(self, query: str, limit: int = 5) -> WebSearchResponse:
        if not self.api_key:
            return WebSearchResponse(
                available=False,
                fallback_reason="SEARCH_API_KEY is not configured; fallback to mock Collector.",
                error_type="missing_api_key",
                error_message="SEARCH_API_KEY is not configured.",
            )
        if not self.base_url:
            return WebSearchResponse(
                available=False,
                fallback_reason="SEARCH_BASE_URL is not configured; fallback to mock Collector.",
                error_type="missing_base_url",
                error_message="SEARCH_BASE_URL is not configured.",
            )

        start = perf_counter()
        try:
            payload = self._request(query=query, limit=limit)
            elapsed = int((perf_counter() - start) * 1000)
            return WebSearchResponse(
                available=True,
                results=self._parse_results(payload, limit),
                attempted=True,
                success=True,
                elapsed_time_ms=elapsed,
            )
        except Exception as exc:  # noqa: BLE001 - Collector must fall back instead of crashing workflow.
            elapsed = int((perf_counter() - start) * 1000)
            error_message = self._sanitize_error(str(exc))
            if isinstance(exc, httpx.HTTPStatusError):
                response_body = self._sanitize_error(exc.response.text[:500])
                error_message = f"{error_message}; response_body={response_body}"
            return WebSearchResponse(
                available=False,
                attempted=True,
                success=False,
                elapsed_time_ms=elapsed,
                fallback_reason=f"Web search failed: {error_message}",
                error_type=exc.__class__.__name__,
                error_message=error_message,
            )

    def _request(self, *, query: str, limit: int) -> dict[str, Any]:
        if self.provider == "tavily":
            response = httpx.post(
                f"{self.base_url}/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": min(limit, self.max_results),
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=self.timeout,
            )
        else:
            response = httpx.get(
                self.base_url,
                params={
                    "q": query,
                    "query": query,
                    "api_key": self.api_key,
                    "key": self.api_key,
                    "num": min(limit, self.max_results),
                },
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()

    def _parse_results(self, payload: dict[str, Any], limit: int) -> list[SearchResult]:
        candidates = (
            payload.get("organic_results")
            or payload.get("results")
            or payload.get("items")
            or payload.get("webPages", {}).get("value")
            or []
        )
        parsed: list[SearchResult] = []
        for item in candidates[:limit]:
            if not isinstance(item, dict):
                continue
            url = item.get("link") or item.get("url") or item.get("displayLink")
            snippet = item.get("snippet") or item.get("description") or item.get("summary") or item.get("content")
            title = item.get("title") or item.get("name") or "public web result"
            if url and snippet:
                parsed.append(SearchResult(title=title, url=url, snippet=snippet, score=item.get("score")))
        return parsed

    def _sanitize_error(self, error: str | None) -> str | None:
        if not error:
            return error
        return error.replace(self.api_key, "***") if self.api_key else error

    def _default_base_url(self) -> str:
        if self.provider == "tavily":
            return "https://api.tavily.com"
        return ""

    @staticmethod
    def _normalize_api_key(raw_key: str) -> str:
        key = raw_key.strip()
        if key.lower().startswith("bearer "):
            return key[7:].strip()
        return key
