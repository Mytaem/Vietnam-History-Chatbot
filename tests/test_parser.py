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
