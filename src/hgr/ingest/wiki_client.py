"""MediaWiki API (vi.wikipedia.org): wikitext, revision, QID, redirects, links, categories. (M3)"""
from __future__ import annotations


class WikiClient:
    API = "https://vi.wikipedia.org/w/api.php"

    def __init__(self, user_agent: str):
        self.user_agent = user_agent

    def fetch_pages(self, titles: list[str]) -> list[dict]:
        """→ [{page_id, title, revision_id, qid, wikitext, redirects[]}] (đã follow redirect)."""
        raise NotImplementedError

    def category_members(self, category: str, depth: int = 2) -> list[str]:
        raise NotImplementedError

    def outgoing_links(self, title: str) -> list[str]:
        raise NotImplementedError
