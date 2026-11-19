"""Тонкий синхронный клиент Keitaro Admin API v1."""

import logging
import threading
import time
from typing import Any

import httpx

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


class KeitaroError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class KeitaroClient:
    GET_RETRIES = 2

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        if http is None:
            if not settings.keitaro_url or not settings.keitaro_api_key:
                raise KeitaroError("KEITARO_URL и KEITARO_API_KEY не заданы в .env")
            http = httpx.Client(
                base_url=settings.keitaro_api_base,
                timeout=settings.keitaro_timeout,
                headers={"Api-Key": settings.keitaro_api_key, "Accept": "application/json"},
            )
        self.http = http
        self._offers_cache: tuple[float, list[dict]] | None = None
        self._offers_lock = threading.Lock()

    # --- транспорт -------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> Any:
        attempts = 1 + (self.GET_RETRIES if method == "GET" else 0)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self.http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
                log.warning("keitaro %s %s transport error: %s", method, path, exc)
                time.sleep(0.4 * (attempt + 1))
                continue
            if resp.status_code >= 500 and attempt < attempts - 1:
                time.sleep(0.4 * (attempt + 1))
                continue
            return self._parse(method, path, resp)
        raise KeitaroError(f"Keitaro недоступен: {last_exc}", status=None)

    @staticmethod
    def _parse(method: str, path: str, resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                body = resp.json()
                if isinstance(body, dict):
                    detail = body.get("error") or body.get("message") or body.get("errors") or detail
            except ValueError:
                pass
            if resp.status_code == 401:
                detail = "неверный API-ключ"
            raise KeitaroError(f"Keitaro {method} {path} → {resp.status_code}: {detail}", status=resp.status_code)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise KeitaroError(f"Keitaro {method} {path}: ответ не JSON") from exc

    # --- справочники -----------------------------------------------------

    def domains(self) -> list[dict]:
        return [d for d in self._request("GET", "/domains") or [] if d.get("state", "active") == "active"]

    def groups(self, kind: str = "campaigns") -> list[dict]:
        return self._request("GET", "/groups", params={"type": kind}) or []

    def traffic_sources(self) -> list[dict]:
        return [s for s in self._request("GET", "/traffic_sources") or [] if s.get("state", "active") == "active"]

    def offers(self, *, fresh: bool = False) -> list[dict]:
        with self._offers_lock:
            now = time.monotonic()
            if not fresh and self._offers_cache and now - self._offers_cache[0] < self.settings.offers_cache_ttl:
                return self._offers_cache[1]
            data = [o for o in self._request("GET", "/offers") or [] if o.get("state", "active") == "active"]
            self._offers_cache = (now, data)
            return data

    def offer(self, offer_id: int) -> dict:
        return self._request("GET", f"/offers/{offer_id}")

    # --- кампании и потоки ----------------------------------------------

    def campaigns(self) -> list[dict]:
        return [c for c in self._request("GET", "/campaigns") or [] if c.get("state") != "deleted"]

    def campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def delete_campaign(self, campaign_id: int) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    def streams(self, campaign_id: int) -> list[dict]:
        items = self._request("GET", f"/campaigns/{campaign_id}/streams") or []
        return [s for s in items if s.get("state") != "deleted"]

    def stream(self, stream_id: int) -> dict:
        return self._request("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", json=payload)

    # --- отчёты ----------------------------------------------------------

    def report(self, payload: dict) -> dict:
        return self._request("POST", "/report/build", json=payload) or {}


_client: KeitaroClient | None = None
_client_lock = threading.Lock()


def get_keitaro() -> KeitaroClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = KeitaroClient(get_settings())
        return _client


def set_keitaro(client: KeitaroClient | None) -> None:
    global _client
    with _client_lock:
        _client = client
