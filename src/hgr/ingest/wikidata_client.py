"""Wikidata wbgetentities: label/alias vi+en, P31, thời gian, quan hệ có cấu trúc. (M3)"""
from __future__ import annotations

import re

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

TIME_PROPS = ["P569", "P570", "P571", "P576", "P580", "P582", "P585"]
REL_PROPS = ["P22", "P25", "P26", "P1365", "P1366", "P276", "P710", "P112", "P36"]
START_PROPS = ["P569", "P571", "P580", "P585"]
END_PROPS = ["P570", "P576", "P582", "P585"]
LANGS = ("vi", "en")


class _Retryable(Exception):
    pass


def _time_bounds(value: dict) -> tuple[int, int] | None:
    """Giá trị time của Wikidata → (năm đầu, năm cuối) theo độ chính xác. Năm TCN âm, không có năm 0."""
    m = re.match(r"([+-])(\d+)-", value.get("time", ""))
    if not m:
        return None
    year = int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
    if year == 0:
        return None
    precision = value.get("precision", 9)
    bce = year < 0
    size = {6: 1000, 7: 100, 8: 10}.get(precision)
    if size is None:
        return year, year
    if size == 10:
        lo = (year // 10) * 10
        return lo, lo + 9
    n = (abs(year) - 1) // size + 1
    if bce:
        return -(n * size), -((n - 1) * size + 1)
    return (n - 1) * size + 1, n * size


def year_range(entity: dict) -> tuple[int | None, int | None]:
    """Khoảng năm của thực thể từ sinh/mất, thành lập/giải thể, bắt đầu/kết thúc, thời điểm."""
    times = entity.get("times", {})
    starts = [b[0] for p in START_PROPS for b in times.get(p, [])]
    ends = [b[1] for p in END_PROPS for b in times.get(p, [])]
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    if start is None and end is not None:
        start = min(b[0] for p in END_PROPS for b in times.get(p, []))
    if end is None and start is not None:
        end = start
    return start, end


class WikidataClient:
    API = "https://www.wikidata.org/w/api.php"

    def __init__(self, user_agent: str, batch: int = 50, timeout: float = 60.0):
        self.user_agent = user_agent
        self.batch = batch
        self._http = httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, _Retryable)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def _get(self, params: dict) -> dict:
        response = self._http.get(self.API, params={"format": "json", "maxlag": "5", **params})
        if response.status_code in (429, 500, 502, 503, 504):
            raise _Retryable(f"HTTP {response.status_code}")
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            if data["error"].get("code") == "maxlag":
                raise _Retryable("maxlag")
            raise RuntimeError(f"Wikidata API lỗi: {data['error']}")
        return data

    def get_entities(self, qids: list[str]) -> dict[str, dict]:
        """→ {qid: {qid, labels, aliases, descriptions, p31[], times{P: [(đầu, cuối)]}, rels{P: [qid]}, sitelink_vi}}"""
        qids = list(dict.fromkeys(q for q in qids if q))
        result: dict[str, dict] = {}
        for i in range(0, len(qids), self.batch):
            data = self._get({
                "action": "wbgetentities",
                "ids": "|".join(qids[i : i + self.batch]),
                "props": "labels|aliases|descriptions|claims|sitelinks",
                "languages": "|".join(LANGS),
                "sitefilter": "viwiki",
            })
            for key, raw in data.get("entities", {}).items():
                if "missing" in raw:
                    continue
                result[key] = self._compact(raw)
        return result

    @staticmethod
    def _compact(raw: dict) -> dict:
        claims = raw.get("claims", {})

        def values(prop: str) -> list[dict]:
            out = []
            for statement in claims.get(prop, []):
                if statement.get("rank") == "deprecated":
                    continue
                snak = statement.get("mainsnak", {})
                if snak.get("snaktype") == "value":
                    out.append(snak["datavalue"]["value"])
            return out

        times = {}
        for prop in TIME_PROPS:
            bounds = [b for v in values(prop) if isinstance(v, dict) and (b := _time_bounds(v))]
            if bounds:
                times[prop] = bounds
        rels = {}
        for prop in REL_PROPS:
            ids = [v["id"] for v in values(prop) if isinstance(v, dict) and "id" in v]
            if ids:
                rels[prop] = ids

        return {
            "qid": raw.get("id"),
            "labels": {lang: v["value"] for lang, v in raw.get("labels", {}).items()},
            "aliases": {lang: [a["value"] for a in vs] for lang, vs in raw.get("aliases", {}).items()},
            "descriptions": {lang: v["value"] for lang, v in raw.get("descriptions", {}).items()},
            "p31": [v["id"] for v in values("P31") if isinstance(v, dict) and "id" in v],
            "times": times,
            "rels": rels,
            "sitelink_vi": raw.get("sitelinks", {}).get("viwiki", {}).get("title"),
        }
