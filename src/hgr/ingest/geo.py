"""Lấy tọa độ (P625) của địa danh có QID từ Wikidata, ghi vào entities.jsonl và Neo4j. (M7)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from hgr.ingest.wikidata_client import WikidataClient

QID_RE = re.compile(r"^Q\d+$")


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def fetch_coordinates(client: WikidataClient, names: dict[str, str]) -> dict[str, tuple[float, float]]:
    """names: {qid: tên địa danh trong dữ liệu}. Chỉ nhận tọa độ khi nhãn Wikidata trùng tên,
    vì QID nối bằng tên có thể sai (vd "Tứ Xuyên" bị nối vào một địa điểm ở Đức)."""
    qids = list(names)
    coords: dict[str, tuple[float, float]] = {}
    for i in range(0, len(qids), client.batch):
        data = client._get({
            "action": "wbgetentities",
            "ids": "|".join(qids[i : i + client.batch]),
            "props": "claims|labels",
            "languages": "vi|en",
        })
        for qid, raw in data.get("entities", {}).items():
            if "missing" in raw:
                continue
            labels = {(v or {}).get("value", "") for v in (raw.get("labels") or {}).values()}
            if _norm(names[qid]) not in {_norm(x) for x in labels}:
                continue
            for statement in raw.get("claims", {}).get("P625", []):
                if statement.get("rank") == "deprecated":
                    continue
                value = (statement.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}
                if "latitude" in value and "longitude" in value:
                    coords[qid] = (value["latitude"], value["longitude"])
                    break
    return coords


def enrich_places(store, resolved_dir: str | Path, user_agent: str) -> tuple[int, int]:
    """→ (số địa danh có qid, số địa danh có tọa độ)."""
    path = Path(resolved_dir) / "entities.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    places = [r for r in rows if r.get("type") == "Place" and QID_RE.match(r.get("qid") or "")]
    client = WikidataClient(user_agent)
    coords = fetch_coordinates(client, {r["qid"]: r["name"] for r in places})

    for row in rows:
        if row.get("qid") in coords:
            row["lat"], row["lon"] = coords[row["qid"]]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    for qid, (lat, lon) in coords.items():
        store.run("MATCH (e:Entity {id: $id}) SET e.lat = $lat, e.lon = $lon", id=f"qid:{qid}", lat=lat, lon=lon)
    return len(places), len(coords)
