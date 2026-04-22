from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional
from xml.dom import minidom
from xml.etree import ElementTree as ET


MEDIAWIKI_NS = {"mw": "http://www.mediawiki.org/xml/export-0.11/"}


@dataclass(frozen=True)
class Listing:
    kind: str  # see/do/eat/...
    name: str
    lat: Optional[str] = None
    lon: Optional[str] = None
    address: Optional[str] = None
    url: Optional[str] = None
    content: Optional[str] = None


MAPFRAME_RE = re.compile(
    r"\{\{\s*Mapframe\s*\|\s*(?P<lat>-?\d+(?:\.\d+)?)\s*\|\s*(?P<lon>-?\d+(?:\.\d+)?)(?P<rest>[^}]*)\}\}",
    re.IGNORECASE,
)
ZOOM_RE = re.compile(r"(?:\||\s)zoom\s*=\s*(\d+)", re.IGNORECASE)


LISTING_START_RE = re.compile(r"\{\{\s*(see|do|eat|drink|buy|sleep|go)\b", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*\|\s*([a-zA-Z_]+)\s*=\s*(.*)\s*$")


def normalize_city_id(name: str) -> str:
    # Stable ASCII-ish id for DTD ID constraints.
    n = unicodedata.normalize("NFKD", name)
    n = "".join(ch for ch in n if not unicodedata.combining(ch))
    n = re.sub(r"[^A-Za-z0-9]+", "-", n).strip("-").lower()
    if not n:
        n = "city"
    if n[0].isdigit():
        n = f"c-{n}"
    return n


def strip_wiki_markup(text: str) -> str:
    # Keep it intentionally simple: remove common constructs, keep readable plain text.
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # non-nested templates
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)  # [[a|b]] -> b
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)  # [[a]] -> a
    text = re.sub(r"''+", "", text)  # bold/italic
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_mapframe_template(tpl: str) -> Optional[tuple[str, str, Optional[str]]]:
    inner = tpl.strip()
    if inner.startswith("{{"):
        inner = inner[2:]
    if inner.endswith("}}"):
        inner = inner[:-2]
    parts = [p.strip() for p in inner.split("|")]
    if not parts:
        return None
    if parts[0].strip().lower() != "mapframe":
        return None

    lat = lon = None
    zoom = None
    for p in parts[1:]:
        if not p:
            continue
        # positional coordinates: first two float-like tokens
        if lat is None and re.fullmatch(r"-?\d+(?:\.\d+)?", p):
            lat = p
            continue
        if lat is not None and lon is None and re.fullmatch(r"-?\d+(?:\.\d+)?", p):
            lon = p
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            if k.strip().lower() == "zoom":
                zoom = v.strip()
    if lat and lon:
        return (lat, lon, zoom)
    return None


def find_first_mapframe(wikitext: str) -> Optional[tuple[str, str, Optional[str]]]:
    # Fast path for the common {{Mapframe|lat|lon|zoom=...}} variant
    m = MAPFRAME_RE.search(wikitext)
    if m:
        rest = m.group("rest") or ""
        z = None
        zm = ZOOM_RE.search(rest)
        if zm:
            z = zm.group(1)
        return (m.group("lat"), m.group("lon"), z)

    # Robust path for variants like: {{mapframe | name=... | 52.250 | 21.000 | zoom=11 }}
    for tpl in iter_templates(wikitext):
        if not re.match(r"\{\{\s*mapframe\b", tpl, flags=re.IGNORECASE):
            continue
        parsed = _parse_mapframe_template(tpl)
        if parsed:
            return parsed
    return None


def iter_templates(text: str) -> Iterable[str]:
    """
    Yields top-level {{...}} template strings using brace counting.
    Designed for Wikivoyage listings which may span multiple lines.
    """
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i : i + 2] != "{{":
            i += 1
            continue
        depth = 0
        j = i
        while j < n - 1:
            if text[j : j + 2] == "{{":
                depth += 1
                j += 2
                continue
            if text[j : j + 2] == "}}":
                depth -= 1
                j += 2
                if depth == 0:
                    yield text[i:j]
                    i = j
                    break
                continue
            j += 1
        else:
            break


def parse_listing_template(tpl: str) -> Optional[Listing]:
    """
    Parse Wikivoyage listing templates like {{see| name=... | lat=... | long=... | content=...}}.
    Some exports place multiple parameters on the same line; splitting by '|' is more robust.
    """
    m = LISTING_START_RE.match(tpl)
    if not m:
        return None
    kind = m.group(1).lower()

    # Drop outer braces.
    inner = tpl.strip()
    if inner.startswith("{{"):
        inner = inner[2:]
    if inner.endswith("}}"):
        inner = inner[:-2]

    parts = [p.strip() for p in inner.split("|")]
    # parts[0] is template name (see/do/...)
    params = parts[1:] if parts else []

    name = None
    lat = lon = address = url = content = None
    for p in params:
        if "=" not in p:
            continue
        key, val = p.split("=", 1)
        key = key.strip().lower()
        val = val.strip()
        if key == "name":
            name = strip_wiki_markup(val) if val else None
        elif key == "lat":
            lat = val if val else None
        elif key in ("long", "lon"):
            lon = val if val else None
        elif key == "address":
            address = strip_wiki_markup(val) if val else None
        elif key == "url":
            url = val if val else None
        elif key == "content":
            content = strip_wiki_markup(val) if val else None

    if not name:
        return None
    return Listing(kind=kind, name=name, lat=lat, lon=lon, address=address, url=url, content=content)


def extract_intro(wikitext: str, max_chars: int = 500) -> Optional[str]:
    # Remove banners/images quickly, then take first non-empty paragraph-ish.
    t = re.sub(r"^\{\{pagebanner[^}]*\}\}\s*", "", wikitext, flags=re.IGNORECASE | re.MULTILINE)
    t = re.sub(r"^\[\[(?:Image|File):[^\]]+\]\]\s*", "", t, flags=re.IGNORECASE | re.MULTILINE)
    # Cut at first section header.
    t = re.split(r"\n==[^=].*?==\n", t, maxsplit=1)[0]
    lines = [strip_wiki_markup(x) for x in t.splitlines()]
    lines = [x for x in lines if x]
    if not lines:
        return None
    intro = " ".join(lines[:3]).strip()
    if len(intro) > max_chars:
        intro = intro[: max_chars - 1].rstrip() + "…"
    return intro or None


def load_city_stats(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    out: dict[str, dict[str, str]] = {}
    for row in data.get("capitali", []):
        city = row.get("city")
        if not city:
            continue
        out[city] = {
            "safety": str(row.get("safety")) if row.get("safety") is not None else "",
            "cost_of_living": str(row.get("cost_of_living")) if row.get("cost_of_living") is not None else "",
            "green_score": str(row.get("green_score")) if row.get("green_score") is not None else "",
        }
    return out


def prettify_xml(elem: ET.Element, doctype: str) -> str:
    raw = ET.tostring(elem, encoding="utf-8")
    parsed = minidom.parseString(raw)
    pretty = parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    # minidom adds xml declaration; we want to inject the doctype right after it.
    lines = pretty.splitlines()
    if lines and lines[0].startswith("<?xml"):
        return "\n".join([lines[0], doctype, *lines[1:]]) + "\n"
    return doctype + "\n" + pretty


def build_city_guide(
    *,
    city_name: str,
    source_file: str,
    generated_at: str,
    lat: str,
    lon: str,
    zoom: Optional[str],
    intro: Optional[str],
    listings_by_kind: dict[str, list[Listing]],
    stats: Optional[dict[str, str]],
) -> ET.Element:
    root = ET.Element("cityGuide", {"id": normalize_city_id(city_name), "name": city_name})

    meta = ET.SubElement(root, "meta")
    ET.SubElement(meta, "sourceFile").text = source_file
    ET.SubElement(meta, "generatedAt").text = generated_at

    loc_attrs = {"lat": lat, "lon": lon}
    if zoom:
        loc_attrs["zoom"] = zoom
    ET.SubElement(root, "location", loc_attrs)

    if intro:
        ET.SubElement(root, "intro").text = intro

    if stats:
        stats_el = ET.SubElement(root, "stats")
        if stats.get("safety"):
            ET.SubElement(stats_el, "safety").text = stats["safety"]
        if stats.get("cost_of_living"):
            ET.SubElement(stats_el, "costOfLiving").text = stats["cost_of_living"]
        if stats.get("green_score"):
            ET.SubElement(stats_el, "greenScore").text = stats["green_score"]

    sections = ET.SubElement(root, "sections")
    order = ["see", "do", "eat", "drink", "buy", "sleep", "go"]
    for kind in order:
        items = listings_by_kind.get(kind) or []
        if not items:
            continue
        section = ET.SubElement(sections, "section", {"type": kind})
        ET.SubElement(section, "heading").text = kind.upper()
        for it in items:
            attrs = {"type": kind}
            if it.lat and it.lon:
                attrs["lat"] = it.lat
                attrs["lon"] = it.lon
            poi = ET.SubElement(section, "poi", attrs)
            ET.SubElement(poi, "name").text = it.name
            if it.address:
                ET.SubElement(poi, "address").text = it.address
            if it.url:
                ET.SubElement(poi, "url").text = it.url
            if it.content:
                ET.SubElement(poi, "description").text = it.content

    return root


def extract_wikitext_pages(mediawiki_xml_path: Path) -> list[str]:
    tree = ET.parse(mediawiki_xml_path)
    root = tree.getroot()
    texts: list[str] = []
    for page in root.findall("mw:page", MEDIAWIKI_NS):
        text_el = page.find(".//mw:text", MEDIAWIKI_NS)
        if text_el is not None and (text_el.text or "").strip():
            texts.append(text_el.text or "")
    return texts


def main() -> int:
    base = Path(__file__).resolve().parent
    input_dir = base / "Progetto_Elaborazione"
    out_dir = base / "clean_xml"
    out_dir.mkdir(parents=True, exist_ok=True)

    stats = load_city_stats(input_dir / "city_indices.json")

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seen_ids: set[str] = set()

    for xml_path in sorted(input_dir.glob("*.xml")):
        city_name = xml_path.stem
        # Avoid Unicode lookalike duplicates (e.g., Reykjavik variants).
        city_key = unicodedata.normalize("NFC", city_name)
        cid = normalize_city_id(city_key)
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        texts = extract_wikitext_pages(xml_path)
        joined = "\n\n".join(texts)

        intro = extract_intro(joined)

        listings_by_kind: dict[str, list[Listing]] = {}
        for tpl in iter_templates(joined):
            listing = parse_listing_template(tpl)
            if not listing:
                continue
            listings_by_kind.setdefault(listing.kind, []).append(listing)

        mf = find_first_mapframe(joined)

        # If Mapframe is missing, fallback to the first POI with coordinates.
        if not mf:
            for kind_items in listings_by_kind.values():
                for it in kind_items:
                    if it.lat and it.lon:
                        mf = (it.lat, it.lon, None)
                        break
                if mf:
                    break

        if not mf:
            # No coordinates at all -> skip.
            continue

        lat, lon, zoom = mf

        # Keep pages lightweight: cap per section.
        for kind, items in list(listings_by_kind.items()):
            listings_by_kind[kind] = items[:50]

        guide = build_city_guide(
            city_name=city_key,
            source_file=xml_path.name,
            generated_at=generated_at,
            lat=lat,
            lon=lon,
            zoom=zoom,
            intro=intro,
            listings_by_kind=listings_by_kind,
            stats=stats.get(city_key),
        )

        doctype = '<!DOCTYPE cityGuide SYSTEM "../team_dataset.dtd">'
        out_xml = prettify_xml(guide, doctype=doctype)
        out_path = out_dir / f"{city_key}.xml"
        out_path.write_text(out_xml, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

