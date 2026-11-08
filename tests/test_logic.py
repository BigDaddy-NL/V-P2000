"""Standalone tests for custom_components/v_p2000/logic.py (no Home Assistant needed).

Run: python3 tests/test_logic.py
"""

import importlib.util
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

_path = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "v_p2000" / "logic.py"
_spec = importlib.util.spec_from_file_location("v_p2000_logic", _path)
logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logic)

TZ = ZoneInfo("Europe/Amsterdam")

# Trimmed real AlarmeringDroid response (8 Nov 2026): 's Gravenmoer was paged in a subitem
# of a group that started for Waspik one minute earlier.
SAMPLE = [
    {
        "id": "26318858", "datum": "08-11", "tijd": "00:44 - 00:45", "dienst": "Brandweer",
        "melding": "P 1 BZB-01 BR container Luiten Ambachtstraat Raamsdonk 207134",
        "tekstmelding": "Brandweer met spoed naar Luiten Ambachtstraat, Raamsdonk",
        "lat": "51.68", "lon": "4.91",
        "capcodes": [{"capcode": "1200907"}, {"capcode": "1201511"}, {"capcode": "1201999"}],
        "subitems": [
            {"id": "26318863", "datum": "08-11", "tijd": "00:45", "dienst": "Brandweer",
             "melding": "P 1 BZB-01 BR container Luiten Ambachtstraat Raamsdonk 207332",
             "capcodes": [{"capcode": "1200268"}, {"capcode": "1201507"}, {"capcode": "1201999"}]},
        ],
    },
    {"id": "26251947", "datum": "25-10", "tijd": "08:41", "melding": "P 2 Stormschade Oosteind",
     "capcodes": [{"capcode": "1200268"}, {"capcode": "1201600"}], "subitems": []},
]


def test_parse_groepen():
    g = logic.parse_groepen("'s Gravenmoer: 1200268, 1201507 1201940\n# opmerking\n\nTDV = 001201600;1201224\n")
    assert [x["slug"] for x in g] == ["s_gravenmoer", "tdv"]
    assert g[0]["naam"] == "'s Gravenmoer"
    assert g[1]["capcodes"] == ["1201600", "1201224"]
    assert logic.groepen_to_text(g).splitlines()[0] == "'s Gravenmoer: 1200268, 1201507, 1201940"
    for text, key in [("", "geen_groepen"), ("zonder dubbele punt", "ongeldige_regel"),
                      ("A: 12ab34", "ongeldige_capcode"), ("A:", "geen_capcodes"),
                      ("A: 1200268\na: 1201507", "dubbele_naam"), (": 1200268", "ongeldige_regel")]:
        try:
            logic.parse_groepen(text)
        except logic.GroepenError as err:
            assert err.key == key, (text, err.key)
        else:
            raise AssertionError(f"no error for {text!r}")


def test_find_matches_subitem_and_order():
    groepen = logic.parse_groepen("'s Gravenmoer: 1200268, 1201507\nTDV: 1201600")
    ms = logic.find_matches(SAMPLE, groepen)
    assert [m["id"] for m in ms] == ["26251947", "26318863"]  # oldest first
    sub = ms[1]
    assert sub["groep"] == "s_gravenmoer" and sub["groep_naam"] == "'s Gravenmoer"
    assert sub["groep_id"] == "26318858"
    assert sub["melding"].endswith("207332")  # the page with our own vehicle, not Waspik's
    assert sub["latitude"] == "51.68"  # falls back to the main melding
    assert ms[0]["groepen"] == ["s_gravenmoer", "tdv"]  # one event for an item hitting two groups


def test_item_time():
    now = datetime(2026, 11, 8, 0, 46, 10, tzinfo=TZ)
    assert logic.item_time({"datum": "08-11", "tijd": "00:44 - 00:45"}, now) == datetime(2026, 11, 8, 0, 45, tzinfo=TZ)
    assert logic.item_time({"datum": "31-12", "tijd": "23:59"}, datetime(2027, 1, 1, 0, 1, tzinfo=TZ)).year == 2026
    assert logic.item_time({"datum": "", "tijd": "x"}, now) is None
    assert logic.item_time({"datum": "31-02", "tijd": "10:00"}, now) is None


def test_capcodes():
    assert logic.api_capcode("001200268") == "1200268"
    assert logic.api_capcode("0101001") == "0101001"
    assert logic.norm_capcode("0101001") == logic.norm_capcode("101001")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
