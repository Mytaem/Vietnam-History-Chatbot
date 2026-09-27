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
_SKIP_TAGS = {"ref", "references", "gallery", "math", "timeline", "score", "syntaxhighlight",
              "imagemap", "mapframe", "graph", "templatestyles", "sup", "nowiki"}
# Template chỉ bọc nội dung hiển thị: giữ lại tham số vị trí cuối cùng.
_PASSTHROUGH_TEMPLATES = {"nowrap", "nobr", "small", "lang", "langx", "sic", "abbr", "không ngắt", "chữ nhỏ", "big",
                          "nihongo", "hán việt", "chú thích trong bài", "flag", "flagcountry", "hn", "zh", "ruby",
                          "tooltip", "nobold", "vertical"}
_QUOTE_TEMPLATES = {"cquote", "quote", "pull quote", "trích dẫn", "blockquote", "quotation", "rquote",
                    "câu trích", "quote box", "trích"}
_DATE_TEMPLATES = {"ngày sinh", "ngày sinh và tuổi", "birth date", "birth date and age", "ngày mất",
                   "ngày mất và tuổi", "death date", "death date and age", "ngày", "date", "start date", "end date",
                   "ngày bắt đầu", "ngày kết thúc", "năm sinh và tuổi", "birth year and age", "death year and age"}
_SPAN_TEMPLATES = {"thời gian sống", "lifespan", "khoảng thời gian"}
_AGE_TEMPLATES = {"số năm theo năm và ngày", "tuổi", "age", "số năm"}
_CONCAT_TEMPLATES = {"linktext"}
_FIXED_TEXT = {"kia": "(tử trận)", "!": "|", "mdash": "—", "ndash": "–", "snd": " – "}


def _numbers(node: Template) -> list[int]:
    out = []
    for param in node.params:
        if param.showkey:
            continue
        value = str(param.value).strip()
        if re.fullmatch(r"-?\d{1,5}", value):
            out.append(int(value))
    return out


def _date_text(nums: list[int]) -> str:
    if len(nums) >= 3 and 1 <= nums[1] <= 12 and 1 <= nums[2] <= 31:
        return f"{nums[2]} tháng {nums[1]} năm {nums[0]}"
    if len(nums) >= 2 and 1 <= nums[1] <= 12:
        return f"tháng {nums[1]} năm {nums[0]}"
    return f"năm {nums[0]}" if nums else ""


def _years_between(nums: list[int]) -> str:
    if len(nums) >= 6:
        y1, m1, d1, y2, m2, d2 = nums[:6]
        return str(y2 - y1 - ((m2, d2) < (m1, d1)))
    if len(nums) >= 2:
        return str(nums[-1] - nums[0])
    return ""


def _table_lines(table: list[tuple[bool, list[str]]]) -> list[str]:
    """Hàng có số ô khớp hàng tiêu đề → 'Cột: giá trị; …' để mỗi dòng tự giải thích khi bảng bị chia qua nhiều đoạn."""
    lines, header = [], None
    for is_header, cells in table:
        captions = [c.lstrip("+").strip() for c in cells if c.startswith("+")]
        lines.extend(captions)
        cells = [c.strip() for c in cells if not c.startswith("+")]
        if is_header:
            header = [c for c in cells if c]
            continue
        if header and len(header) == len(cells):
            lines.append("; ".join(f"{h}: {c}" for h, c in zip(header, cells) if c))
        else:
            lines.append(" | ".join(c for c in cells if c))
    return [line for line in lines if line]


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
        if name == "table":
            return self._table(node)
        inner = self.render(node.contents) if node.contents else ""
        if name in ("br", "li", "p", "div", "dd", "dt"):
            return "\n" + inner
        if name in ("blockquote", "poem"):
            return "\n" + inner + "\n"
        return inner

    def _table(self, node: Tag) -> str:
        """Bảng → mỗi hàng một dòng 'ô | ô | ô' (danh sách vua, quan đô hộ… là dữ kiện có giá trị)."""
        if node.contents is None:
            return ""
        rows, loose = [], []
        for child in node.contents.nodes:
            if not isinstance(child, Tag):
                continue
            tag = str(child.tag).strip().lower()
            if tag == "tr":
                children = child.contents.nodes if child.contents else []
                rows.append([c for c in children if isinstance(c, Tag) and str(c.tag).strip().lower() in ("td", "th")])
            elif tag in ("td", "th"):
                loose.append(child)
            elif tag == "caption":
                rows.append([child])
        if loose:
            rows.insert(0, loose)
        table: list[tuple[bool, list[str]]] = []
        for cells in rows:
            texts = [" ".join(self.render(c.contents).split()) if c.contents is not None else "" for c in cells]
            is_header = bool(cells) and all(str(c.tag).strip().lower() == "th" for c in cells)
            if any(texts):
                table.append((is_header, texts))
        return "\n" + "\n".join(_table_lines(table)) + "\n"

    def _template(self, node: Template) -> str:
        name = normalize_text(str(node.name).strip().replace("_", " ")).lower()
        positional = [p for p in node.params if not p.showkey]
        if name in _FIXED_TEXT:
            return _FIXED_TEXT[name]
        if name in _QUOTE_TEMPLATES:
            text = next((p for p in node.params if str(p.name).strip() in ("text", "nội dung", "quote", "1")), None)
            return "\n" + (self.render(text.value) if text else "") + "\n"
        if name in _DATE_TEMPLATES:
            return _date_text(_numbers(node))
        if name in _SPAN_TEMPLATES:
            nums = _numbers(node)
            return f"{nums[0]}–{nums[1]}" if len(nums) >= 2 else ""
        if name in _AGE_TEMPLATES:
            return _years_between(_numbers(node))
        if name in _CONCAT_TEMPLATES:
            return "".join(self.render(p.value) for p in positional)
        if name in _PASSTHROUGH_TEMPLATES or name.startswith("lang-"):
            if positional:
                return self.render(positional[-1].value)
            return self.render(node.params[0].value) if node.params else ""
        return ""


_QUOTE_OPEN = "|".join(re.escape(n) for n in sorted(_QUOTE_TEMPLATES, key=len, reverse=True))
# Markup còn sót khi wikitext sai cú pháp (thẻ ref thiếu '>', template thiếu '}}'…) — thư viện coi là văn bản thường.
_RESIDUE = [
    (re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S | re.I), ""),
    (re.compile(r"<ref\b[^\n]*", re.I), ""),
    (re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*\b[^<>\n]*>"), ""),
    (re.compile(r"\{\{\s*(?:" + _QUOTE_OPEN + r")\s*\|", re.I), "\n"),
    (re.compile(r"\{\{[^{}\n]*\}\}"), ""),
    (re.compile(r"\{\{[^|{}\n]*\|?"), ""),
    (re.compile(r"\|*\s*\}\}"), ""),
    (re.compile(r"'{2,}"), ""),
    (re.compile(r"\[\[(?:[^\[\]|]*\|)?([^\[\]]*)\]\]"), r"\1"),
    (re.compile(r"\[https?://\S+\s*([^\]]*)\]"), r"\1"),
    (re.compile(r"\|\s*(?:author|tác giả|nguồn|source)\s*=\s*", re.I), " — "),
    (re.compile(r"\{\|[^\n]*"), ""),
    (re.compile(r"\[\[|\]\]"), ""),
    (re.compile(r",(?:\s*,)+"), ","),
]
_TABLE_EDGE = re.compile(r"^\s*(?:\{\||\|\}|\|\+)")
_TABLE_ROW = re.compile(r"^\s*\|-")
_TABLE_CELL = re.compile(r"^\s*[|!](?![|}])")
_CELL_ATTR = re.compile(r'^\s*(?:[a-z-]+\s*=\s*"[^"]*"\s*)+\|(?!\|)', re.I)
_PARAM_LEAK = re.compile(r"^\s*[\w\s-]{1,30}=")


def _flatten_raw_tables(lines: list[str]) -> list[str]:
    """Bảng wikitext không được nhận dạng (vd mở bằng {{đầu bảng}}) → dòng 'ô | ô'; bỏ tham số template rò ra."""
    out: list[str] = []
    table: list[tuple[bool, list[str]]] = []
    row: list[str] = []
    row_is_header = True

    def end_row() -> None:
        nonlocal row_is_header
        cells = [c for c in row if not _PARAM_LEAK.match(c)]
        if any(cells):
            table.append((row_is_header, cells))
        row.clear()
        row_is_header = True

    def end_table() -> None:
        end_row()
        out.extend(_table_lines(table))
        table.clear()

    for line in lines:
        if _TABLE_EDGE.match(line) or _TABLE_ROW.match(line):
            end_row()
        elif _TABLE_CELL.match(line):
            stripped = line.strip()
            row_is_header = row_is_header and stripped.startswith("!")
            for cell in re.split(r"\|\||!!", stripped[1:]):
                row.append(_CELL_ATTR.sub("", cell).strip())
        else:
            end_table()
            out.append(line)
    end_table()
    return out


def _clean(text: str) -> str:
    for pattern, repl in _RESIDUE:
        text = pattern.sub(repl, text)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\(\s*[,;:]?\s*\)", "", text)
    text = re.sub(r"\(\s*[,;:]\s*", "(", text)
    text = re.sub(r" +([,.;:!?)])", r"\1", text)
    text = re.sub(r"\( +", "(", text)
    lines = [line.strip(" *#:;") for line in _flatten_raw_tables(text.split("\n"))]
    return normalize_text("\n".join(line for line in lines if re.search(r"[^\W_]", line)))


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
