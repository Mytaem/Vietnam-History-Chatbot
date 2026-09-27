"""Test resolve/resolver.py"""
from hgr.resolve.resolver import EntityResolver, _slug


def test_resolver_uses_curated_historical_place_aliases():
    resolver = EntityResolver()
    resolver.add_aliases("local:ha_noi", ["Hà Nội", "Thăng Long", "Đông Kinh"])

    assert resolver.resolve({"name": "thăng long"}, [], "ly") == "local:ha_noi"
    assert _slug("Đại Việt") == "dai-viet"


def test_resolver_keeps_same_named_events_in_different_years_separate():
    resolver = EntityResolver()

    battle_938 = resolver.resolve({"name": "Trận Bạch Đằng 938"}, [], "ngo")
    battle_981 = resolver.resolve({"name": "Trận Bạch Đằng 981"}, [], "tienle")
    battle_1288 = resolver.resolve({"name": "Trận Bạch Đằng 1288"}, [], "tran")

    assert len({battle_938, battle_981, battle_1288}) == 3


def test_resolver_prefers_wikidata_id():
    resolver = EntityResolver()

    assert resolver.resolve({"name": "Hồ Chí Minh", "qid": "Q7186"}, [], "candai") == "qid:Q7186"
