from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.acquisition.schemas import DamCandidate


class NominatimClient:
    _rate_lock = threading.Lock()
    _last_global_request = 0.0
    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = "HydroShield/0.1 (dam-break flood modelling)",
        min_interval_s: float = 1.05,
        timeout_s: int = 20,
        cache_dir: Path | None = None,
        cache_ttl_s: int = 86_400,
    ):
        self.base_url = base_url.rstrip("?")
        self.user_agent = user_agent
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir
        self.cache_ttl_s = cache_ttl_s
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, country_code: str | None = None, limit: int = 5) -> list[DamCandidate]:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": str(min(limit, 10)),
            "addressdetails": "1",
            "extratags": "1",
            "namedetails": "1",
        }
        if country_code:
            params["countrycodes"] = country_code.lower()
        cache_key = __import__("hashlib").sha256(urlencode(params).encode("utf-8")).hexdigest()
        cache_file = self.cache_dir / f"{cache_key}.json" if self.cache_dir else None
        if cache_file and self.cache_ttl_s > 0 and cache_file.exists():
            try:
                age = time.time() - cache_file.stat().st_mtime
                if age <= self.cache_ttl_s:
                    payload = json.loads(cache_file.read_text(encoding="utf-8"))
                    return [DamCandidate(**item) for item in payload]
            except (OSError, ValueError, TypeError):
                pass
        with NominatimClient._rate_lock:
            delay = self.min_interval_s - (time.monotonic() - NominatimClient._last_global_request)
            if delay > 0:
                time.sleep(delay)
            request = Request(
                f"{self.base_url}?{urlencode(params)}",
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            )
            try:
                with urlopen(request, timeout=self.timeout_s) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"Dam/place search provider is unavailable: {exc}") from exc
            NominatimClient._last_global_request = time.monotonic()

        candidates: list[DamCandidate] = []
        for item in payload:
            try:
                display_name = str(item.get("display_name") or query)
                namedetails = item.get("namedetails") or {}
                name = str(namedetails.get("name") or item.get("name") or display_name.split(",", 1)[0]).strip()
                category = str(item.get("class") or "") or None
                object_type = str(item.get("type") or "") or None
                candidates.append(
                    DamCandidate(
                        display_name=display_name,
                        name=name,
                        latitude=float(item["lat"]),
                        longitude=float(item["lon"]),
                        osm_type=item.get("osm_type"),
                        osm_id=int(item["osm_id"]) if item.get("osm_id") else None,
                        category=category,
                        object_type=object_type,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if cache_file:
            try:
                cache_file.write_text(
                    json.dumps([candidate.model_dump(mode="json") for candidate in candidates], ensure_ascii=False),
                    encoding="utf-8",
                )
            except OSError:
                pass
        return candidates
