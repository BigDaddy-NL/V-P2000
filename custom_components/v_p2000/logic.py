"""Pure helpers for V-P2000 (no Home Assistant imports, testable standalone)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from typing import Any

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
_DATE_RE = re.compile(r"(\d{1,2})-(\d{1,2})")
_LINE_RE = re.compile(r"^(?P<naam>[^:=]+?)\s*[:=]\s*(?P<codes>.*)$")
_CAPCODE_RE = re.compile(r"\d{6,9}")


class GroepenError(ValueError):
    """Invalid group definition; key is a translation key, detail the offending text."""

    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(f"{key}: {detail}")
        self.key = key
        self.detail = detail


def slugify(text: str) -> str:
    """'t Zand Noord -> t_zand_noord (same result as HA's slugify for plain names)."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def norm_capcode(code: Any) -> str:
    """Capcode for comparison: digits without leading zeros (001234567 == 1234567)."""
    s = str(code).strip().lstrip("0")
    return s or "0"


def api_capcode(code: Any) -> str:
    """Capcode for the API query (the API itself ignores leading zeros)."""
    s = str(code).strip()
    if len(s) == 9 and s.startswith("00"):
        s = s[2:]
    return s


def parse_groepen(text: str) -> list[dict[str, Any]]:
    """Parse one group per line: 'naam: capcode, capcode'. Lines starting with # are ignored."""
    groepen: list[dict[str, Any]] = []
    slugs: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m or not m["naam"].strip():
            raise GroepenError("ongeldige_regel", line)
        naam = m["naam"].strip()
        codes = [c for c in re.split(r"[\s,;]+", m["codes"]) if c]
        if not codes:
            raise GroepenError("geen_capcodes", naam)
        bad = [c for c in codes if not _CAPCODE_RE.fullmatch(c)]
        if bad:
            raise GroepenError("ongeldige_capcode", ", ".join(bad))
        slug = slugify(naam)
        if not slug:
            raise GroepenError("ongeldige_regel", line)
        if slug in slugs:
            raise GroepenError("dubbele_naam", naam)
        slugs.add(slug)
        uniek = list(dict.fromkeys(api_capcode(c) for c in codes))
        groepen.append({"naam": naam, "slug": slug, "capcodes": uniek})
    if not groepen:
        raise GroepenError("geen_groepen")
    return groepen


def groepen_to_text(groepen: Iterable[dict[str, Any]]) -> str:
    return "\n".join(f"{g['naam']}: {', '.join(g['capcodes'])}" for g in groepen)


def iter_items(meldingen: Iterable[Any]) -> Iterator[tuple[dict, dict]]:
    """Yield (item, group) for every main melding and each of its subitems."""
    for m in meldingen or []:
        if not isinstance(m, dict):
            continue
        yield m, m
        for sub in m.get("subitems") or []:
            if isinstance(sub, dict):
                yield sub, m


def item_capcodes(item: dict) -> set[str]:
    out: set[str] = set()
    for c in item.get("capcodes") or []:
        if isinstance(c, dict) and c.get("capcode"):
            out.add(norm_capcode(c["capcode"]))
        elif isinstance(c, (str, int)):
            out.add(norm_capcode(c))
    return out


def item_time(item: dict, now: datetime) -> datetime | None:
    """Latest HH:MM in item['tijd'] on item['datum'] (dd-mm), in now's timezone."""
    times = _TIME_RE.findall(str(item.get("tijd") or ""))
    dm = _DATE_RE.match(str(item.get("datum") or ""))
    if not times or not dm:
        return None
    day, month = int(dm.group(1)), int(dm.group(2))
    hh, mm = (int(x) for x in times[-1])
    try:
        t = now.replace(month=month, day=day, hour=hh, minute=mm, second=0, microsecond=0)
    except ValueError:
        return None
    if t - now > timedelta(days=1):  # e.g. "31-12" seen on 1 January
        try:
            t = t.replace(year=t.year - 1)
        except ValueError:
            return None
    return t


def find_matches(meldingen: Iterable[Any], groepen: list[dict[str, Any]]) -> list[dict]:
    """One event dict per (sub)item that contains a capcode of a configured group.

    Groups are reported in config order; the result is sorted oldest id first.
    """
    sets = [(g, {norm_capcode(c) for c in g["capcodes"]}) for g in groepen]
    done: set[str] = set()
    out: list[dict] = []
    for item, group in iter_items(meldingen):
        iid = str(item.get("id") or "")
        if not iid or iid in done:
            continue
        caps = item_capcodes(item)
        hit = [(g, caps & codes) for g, codes in sets if caps & codes]
        if not hit:
            continue
        done.add(iid)

        def pick(key: str) -> Any:
            val = item.get(key)
            return val if val not in (None, "") else group.get(key)

        out.append(
            {
                "groep": hit[0][0]["slug"],
                "groep_naam": hit[0][0]["naam"],
                "groepen": [g["slug"] for g, _ in hit],
                "capcodes": sorted({c for _, cs in hit for c in cs}),
                "id": iid,
                "groep_id": str(group.get("id") or ""),
                "melding": pick("melding") or "",
                "tekstmelding": pick("tekstmelding") or "",
                "dienst": pick("dienst"),
                "regio": pick("regio"),
                "plaats": pick("plaats"),
                "straat": pick("straat"),
                "datum": pick("datum"),
                "tijd": pick("tijd"),
                "prio1": pick("prio1"),
                "latitude": pick("lat"),
                "longitude": pick("lon"),
                "bron": "alarmeringdroid",
            }
        )
    out.sort(key=lambda e: int(e["id"]) if e["id"].isdigit() else 0)
    return out
