"""wikitext → sections[], infobox{}, links[(surface, target)] bằng mwparserfromhell. (M3)"""
from __future__ import annotations


def parse_article(wikitext: str) -> dict:
    """→ {sections: [{path, text}], infobox: {template, fields}, links: [{surface, target, offset}]}"""
    raise NotImplementedError
