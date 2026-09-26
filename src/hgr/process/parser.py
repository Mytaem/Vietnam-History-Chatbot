"""wikitext → sections[], infobox{}, links[(surface, target)] bằng mwparserfromhell. (M3)"""
from __future__ import annotations

import re

import mwparserfromhell
from mwparserfromhell.nodes import Comment, ExternalLink, Heading, HTMLEntity, Tag, Template, Text, Wikilink
from mwparserfromhell.wikicode import Wikicode

from hgr.process.normalize import normalize_text

LEAD = "Mở đầu"
DEFAULT_DROP_SECTIONS = ("Tham khảo", "Chú thích", "Xem thêm", "Liên kết ngoài", "Đọc thêm", "Ghi chú")

_INFOBOX_PREFIXES = ("thông tin", "hộp thông tin", "infobox")
_CATEGORY_NS = {"thể loại", "category"}
_SKIP_NS = _CATEGORY_NS | {
    "tập tin", "file", "hình", "image", "wikipedia", "wp", "bản mẫu", "template", "wiktionary", "wikt",
    "commons", "wikidata", "d", "meta", "mw", "species", "s", "q", "b", "n", "v", "voy", "user", "thành viên",
    "chủ đề", "portal", "cổng thông tin", "trợ giúp", "help", "special", "đặc biệt", "media",
}
_LANG_PREFIX = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,})?$")
_SKIP_TAGS = {"ref", "references", "gallery", "table", "math", "timeline", "score", "syntaxhighlight",
              "imagemap", "mapframe", "graph", "templatestyles", "sup", "nowiki", "poem"}
# Template chỉ bọc nội dung hiển thị: giữ lại tham số vị trí cuối cùng.
_PASSTHROUGH_TEMPLATES = {"nowrap", "nobr", "small", "lang", "sic", "abbr", "không ngắt", "chữ nhỏ", "big",
                          "nihongo", "hán việt", "chú thích trong bài"}


def _target(title: str) -> str | None:
    """Chuẩn hóa đích wikilink; None nếu là liên kết ngoài không gian bài viết."""
    title = title.replace("_", " ").strip()
    if title.startswith(":"):
        return None
    if ":" in title:
        prefix = title.split(":", 1)[0].strip().lower()
        if prefix in _SKIP_NS or _LANG_PREFIX.match(prefix):
            return None
    title = title.split("#", 1)[0].strip()
    if not title:
        return None
    return normalize_text(title[0].upper() + title[1:])


def _namespace(title: str) -> str:
    return title.split(":", 1)[0].strip().lower() if ":" in title else ""


class _Renderer:
    """Chuyển wikicode thành văn bản thuần, đồng thời gom wikilink và thể loại."""

    def __init__(self) -> None:
        self.links: list[dict] = []
        self.categories: list[str] = []

    def render(self, code: Wikicode | None) -> str:
        if code is None:
            return ""
        return "".join(self._node(node) for node in code.nodes)

    def _node(self, node) -> str:
        if isinstance(node, Text):
            return str(node.value)
        if isinstance(node, Wikilink):
            return self._wikilink(node)
        if isinstance(node, Tag):
            return self._tag(node)
        if isinstance(node, Template):
            return self._template(node)
        if isinstance(node, HTMLEntity):
            return node.normalize()
        if isinstance(node, ExternalLink):
            return self.render(node.title) if node.title else ""
        if isinstance(node, Comment):
            return ""
        return ""

    def _wikilink(self, node: Wikilink) -> str:
        title = str(node.title).strip()
        namespace = _namespace(title)
        if namespace in _CATEGORY_NS:
            self.categories.append(normalize_text(title.split(":", 1)[1].split("|")[0].strip()))
            return ""
        target = _target(title)
        if target is None and namespace:
            return ""
        surface = self.render(node.text) if node.text else title.split("#", 1)[0]
        if target:
            self.links.append({"surface": surface.strip(), "target": target})
        return surface

    def _tag(self, node: Tag) -> str:
        name = str(node.tag).strip().lower()
        if name in _SKIP_TAGS:
            return ""
        if name == "br":
            return "\n"
        if name == "li":
            return "\n"
        return self.render(node.contents) if node.contents else ""

    def _template(self, node: Template) -> str:
        name = normalize_text(str(node.name).strip().replace("_", " ")).lower()
        if name in _PASSTHROUGH_TEMPLATES or name.startswith("lang-"):
            positional = [p for p in node.params if not p.showkey]
            return self.render(positional[-1].value) if positional else ""
        return ""


def _clean(text: str) -> str:
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\(\s*[,;:]?\s*\)", "", text)
    text = re.sub(r"\(\s*[,;:]\s*", "(", text)
    text = re.sub(r" +([,.;:!?)])", r"\1", text)
    text = re.sub(r"\( +", "(", text)
    lines = [line.strip(" *#:;") for line in text.split("\n")]
    return normalize_text("\n".join(line for line in lines if line))


def _is_infobox(node: Template) -> bool:
    name = normalize_text(str(node.name).strip().replace("_", " ")).lower()
    return name.startswith(_INFOBOX_PREFIXES)


def _parse_infobox(node: Template) -> dict:
    fields = {}
    for param in node.params:
        renderer = _Renderer()
        text = _clean(renderer.render(param.value))
        if not text:
            continue
        key = normalize_text(str(param.name).strip())
        fields[key] = {"text": text, "links": list(dict.fromkeys(link["target"] for link in renderer.links))}
    return {"template": normalize_text(str(node.name).strip()), "fields": fields}


def _locate_links(text: str, links: list[dict], section: str) -> list[dict]:
    located, cursor = [], 0
    for link in links:
        surface = normalize_text(link["surface"])
        if not surface:
            continue
        offset = text.find(surface, cursor)
        if offset == -1:
            offset = text.find(surface)
        if offset != -1:
            cursor = offset + len(surface)
        located.append({"surface": surface, "target": link["target"], "section": section,
                        "offset": offset if offset != -1 else None})
    return located


def parse_article(wikitext: str, drop_sections: tuple[str, ...] | list[str] = DEFAULT_DROP_SECTIONS) -> dict:
    """→ {sections: [{path, text}], infobox: {template, fields: {tên: {text, links}}},
          links: [{surface, target, section, offset}], categories: [...]}"""
    code = mwparserfromhell.parse(wikitext)
    drop = {normalize_text(s).lower() for s in drop_sections}

    infobox_node = next((t for t in code.filter_templates(recursive=False) if _is_infobox(t)), None)
    if infobox_node is None:
        infobox_node = next((t for t in code.filter_templates(recursive=True) if _is_infobox(t)), None)
    infobox = _parse_infobox(infobox_node) if infobox_node is not None else {}

    sections: list[dict] = []
    links: list[dict] = []
    categories: list[str] = []
    headings: dict[int, str] = {}
    path, dropped = LEAD, False
    renderer, buffer = _Renderer(), []

    def flush() -> None:
        categories.extend(renderer.categories)
        if dropped:
            return
        text = _clean("".join(buffer))
        if text:
            sections.append({"path": path, "text": text})
            links.extend(_locate_links(text, renderer.links, path))

    for node in code.nodes:
        if isinstance(node, Heading):
            flush()
            renderer, buffer = _Renderer(), []
            title = _clean(_Renderer().render(node.title)) or "?"
            level = node.level
            headings = {lv: t for lv, t in headings.items() if lv < level}
            headings[level] = title
            path = " > ".join(headings[lv] for lv in sorted(headings))
            dropped = headings[min(headings)].lower() in drop
            continue
        if node is infobox_node:
            continue
        buffer.append(renderer._node(node))
    flush()

    return {
        "sections": sections,
        "infobox": infobox,
        "links": links,
        "categories": list(dict.fromkeys(categories)),
    }
