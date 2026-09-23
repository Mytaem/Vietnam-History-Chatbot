"""Wikidata wbgetentities: label/alias vi+en, P31, thời gian, quan hệ có cấu trúc. (M3)"""
from __future__ import annotations

TIME_PROPS = ["P569", "P570", "P571", "P576", "P580", "P582", "P585"]
REL_PROPS = ["P22", "P25", "P26", "P1365", "P1366", "P276", "P710", "P112", "P36"]


class WikidataClient:
    API = "https://www.wikidata.org/w/api.php"

    def __init__(self, user_agent: str, batch: int = 50):
        self.user_agent = user_agent
        self.batch = batch

    def get_entities(self, qids: list[str]) -> dict[str, dict]:
        raise NotImplementedError
