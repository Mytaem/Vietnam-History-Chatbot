"""MediaWiki API (vi.wikipedia.org): wikitext, revision, QID, redirects, links, categories. (M3)"""
from __future__ import annotations

from collections import deque
from typing import Iterator
from urllib.parse import quote

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from hgr.log import get_logger
from hgr.process.normalize import nfc

log = get_logger(__name__)


class _Retryable(Exception):
    pass


def _batches(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class WikiClient:
    API = "https://vi.wikipedia.org/w/api.php"
    BATCH = 50

    def __init__(self, user_agent: str, timeout: float = 60.0):
        self.user_agent = user_agent
        self._http = httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, _Retryable)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, max=30),
        reraise=True,
    )
    def _get(self, params: dict) -> dict:
        response = self._http.get(self.API, params={"format": "json", "formatversion": "2", "maxlag": "5", **params})
        if response.status_code in (429, 500, 502, 503, 504):
            raise _Retryable(f"HTTP {response.status_code}")
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            if data["error"].get("code") == "maxlag":
                raise _Retryable("maxlag")
            raise RuntimeError(f"MediaWiki API lỗi: {data['error']}")
        return data

    def _query(self, params: dict) -> Iterator[dict]:
        """Lặp qua các trang kết quả, tự xử lý `continue`."""
        cont: dict = {}
        while True:
            data = self._get({"action": "query", **params, **cont})
            yield data.get("query", {})
            if "continue" not in data:
                return
            cont = data["continue"]

    @staticmethod
    def url(title: str) -> str:
        return "https://vi.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="/:()'_,-")

    def fetch_pages(self, titles: list[str], content: bool = True) -> list[dict]:
        """→ [{page_id, title, revision_id, qid, wikitext, redirects[]}] (đã follow redirect).

        Mỗi bài có thêm `requested` (các tiêu đề đầu vào trỏ tới bài). Tiêu đề không tồn tại trả về
        `{title, requested, missing: True}`.
        """
        titles = list(dict.fromkeys(nfc(t).strip() for t in titles if t and t.strip()))
        pages: dict[str, dict] = {}
        missing: list[dict] = []
        for batch in _batches(titles, self.BATCH):
            params = {
                "titles": "|".join(batch),
                "redirects": "1",
                "prop": "revisions|pageprops",
                "rvprop": "ids|content" if content else "ids",
                "rvslots": "main",
                "ppprop": "wikibase_item",
            }
            renames: dict[str, str] = {}
            redirect_from: dict[str, list[str]] = {}
            for part in self._query(params):
                for item in part.get("normalized", []):
                    renames[item["from"]] = item["to"]
                for item in part.get("redirects", []):
                    renames[item["from"]] = item["to"]
                    redirect_from.setdefault(item["to"], []).append(item["from"])
                for raw in part.get("pages", []):
                    title = raw["title"]
                    if raw.get("missing") or raw.get("invalid"):
                        continue
                    page = pages.setdefault(title, {
                        "page_id": raw["pageid"], "title": title, "url": self.url(title),
                        "revision_id": None, "qid": None, "wikitext": None, "redirects": [], "requested": [],
                    })
                    if raw.get("revisions"):
                        revision = raw["revisions"][0]
                        page["revision_id"] = revision.get("revid")
                        if content:
                            page["wikitext"] = revision.get("slots", {}).get("main", {}).get("content")
                    if raw.get("pageprops", {}).get("wikibase_item"):
                        page["qid"] = raw["pageprops"]["wikibase_item"]

            for requested in batch:
                final = requested
                for _ in range(3):
                    final = renames.get(final, final)
                if final in pages:
                    pages[final]["requested"].append(requested)
                    pages[final]["redirects"] = sorted(set(pages[final]["redirects"]) | set(redirect_from.get(final, [])))
                else:
                    missing.append({"title": requested, "requested": [requested], "missing": True})
        return list(pages.values()) + missing

    def category_members(self, category: str, depth: int = 2) -> list[str]:
        """Bài (namespace 0) trong thể loại, duyệt thể loại con tối đa `depth` cấp."""
        name = category if ":" in category else f"Thể loại:{category}"
        seen_cats, members = {name}, []
        queue = deque([(name, 0)])
        while queue:
            current, level = queue.popleft()
            params = {"list": "categorymembers", "cmtitle": current, "cmtype": "page|subcat", "cmlimit": "max"}
            for part in self._query(params):
                for item in part.get("categorymembers", []):
                    if item["ns"] == 0:
                        members.append(item["title"])
                    elif item["ns"] == 14 and level < depth and item["title"] not in seen_cats:
                        seen_cats.add(item["title"])
                        queue.append((item["title"], level + 1))
        return list(dict.fromkeys(members))

    def outgoing_links(self, title: str) -> list[str]:
        params = {"titles": title, "prop": "links", "plnamespace": "0", "pllimit": "max", "redirects": "1"}
        links = []
        for part in self._query(params):
            for page in part.get("pages", []):
                links.extend(link["title"] for link in page.get("links", []))
        return list(dict.fromkeys(links))
