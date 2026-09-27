"""Test process/parser.py"""
from hgr.process.parser import LEAD, parse_article

WIKITEXT = """{{bài cùng tên|Trận Bạch Đằng}}
{{Thông tin chiến tranh
| tên = Trận Bạch Đằng (938)
| chỉ huy 2 = [[Ngô Quyền]] <br> [[Dương Tam Kha]]
| thời gian = Năm [[938]]<ref>nguồn</ref>
}}
'''Trận Bạch Đằng''' ([[chữ Hán]]: {{lang|zh|白藤江之戰}}) do [[Ngô Quyền|ông Ngô Quyền]] chỉ huy.<ref name="a">Sách [[X]]</ref>
== Diễn biến ==
Quân [[Nam Hán]] tiến vào.
=== Kết quả ===
* [[Lưu Hoằng Tháo]] tử trận.
[[Tập tin:Tranh.jpg|nhỏ|Chú thích [[Z]]]]
== Xem thêm ==
* [[Ngô Xương Văn]]
== Tham khảo ==
{{tham khảo}}
[[Thể loại:Nhà Ngô]]
[[en:Battle of Bach Dang (938)]]
"""


def test_infobox():
    infobox = parse_article(WIKITEXT)["infobox"]
    assert infobox["template"] == "Thông tin chiến tranh"
    assert infobox["fields"]["chỉ huy 2"]["links"] == ["Ngô Quyền", "Dương Tam Kha"]
    assert infobox["fields"]["thời gian"]["text"] == "Năm 938"


def test_sections_and_dropped_sections():
    sections = parse_article(WIKITEXT)["sections"]
    assert [s["path"] for s in sections] == [LEAD, "Diễn biến", "Diễn biến > Kết quả"]
    lead = sections[0]["text"]
    assert lead == "Trận Bạch Đằng (chữ Hán: 白藤江之戰) do ông Ngô Quyền chỉ huy."
    assert "Ngô Xương Văn" not in " ".join(s["text"] for s in sections)
    assert sections[2]["text"] == "Lưu Hoằng Tháo tử trận."


def test_links_and_categories():
    result = parse_article(WIKITEXT)
    targets = [link["target"] for link in result["links"]]
    assert targets == ["Chữ Hán", "Ngô Quyền", "Nam Hán", "Lưu Hoằng Tháo"]
    link = result["links"][1]
    assert (link["surface"], link["section"], link["offset"]) == ("ông Ngô Quyền", LEAD, 35)
    assert result["categories"] == ["Nhà Ngô"]


def _text(wikitext):
    return "\n".join(s["text"] for s in parse_article(wikitext)["sections"])


def test_content_templates_are_rendered():
    assert _text("Ông viết rằng {{cquote|Độc lập hay là chết!}} rồi đi.") == "Ông viết rằng\nĐộc lập hay là chết!\nrồi đi."
    assert _text("Hồ Chí Minh ({{ngày sinh|1890|5|19}} – {{ngày mất và tuổi|1969|9|2|1890|5|19}}).") == \
        "Hồ Chí Minh (19 tháng 5 năm 1890 – 2 tháng 9 năm 1969)."
    assert _text("Ông ({{Thời gian sống|1890|1969}}) thọ {{số năm theo năm và ngày|1890|5|19|1969|9|2}} tuổi.") == \
        "Ông (1890–1969) thọ 79 tuổi."
    assert _text("Tướng Lưu Hoằng Tháo {{KIA}}.") == "Tướng Lưu Hoằng Tháo (tử trận)."


def test_tables_become_labelled_rows():
    table = "{| class=wikitable\n! Thứ tự !! Tên họ !! Niên đại\n|-\n| 1 || [[Lưu Diên Hựu]] || 681-687\n|}"
    assert _text(table) == "Thứ tự: 1; Tên họ: Lưu Diên Hựu; Niên đại: 681-687"
    raw = "{{đầu bảng}}\n! Thứ tự\n! Tên họ\n|-----\n| 2\n| [[Quang Sở Khách]]\n|}"
    assert _text(raw) == "Thứ tự: 2; Tên họ: Quang Sở Khách"


def test_broken_markup_is_cleaned():
    text = _text("Sinh năm 1920.<ref Lê Quang Túy viết thiếu dấu\nCâu sau {{cquote|Trích dẫn hỏng '''đậm'''\n}} hết.")
    assert "<ref" not in text and "{{" not in text and "}}" not in text and "'''" not in text
    assert "Trích dẫn hỏng đậm" in text
