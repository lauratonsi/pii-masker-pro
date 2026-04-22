from __future__ import annotations

import html
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class CityStats:
    safety: Optional[float] = None
    cost_of_living: Optional[float] = None
    green_score: Optional[float] = None


@dataclass(frozen=True)
class City:
    city_id: str
    name: str
    lat: float
    lon: float
    zoom: Optional[int]
    intro: Optional[str]
    stats: CityStats
    sections: list["Section"]
    source_xml_relpath: str


@dataclass(frozen=True)
class Poi:
    kind: str
    name: str
    lat: Optional[float]
    lon: Optional[float]
    address: Optional[str]
    url: Optional[str]
    description: Optional[str]


@dataclass(frozen=True)
class Section:
    kind: str
    heading: str
    pois: list[Poi]


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    t = (el.text or "").strip()
    return t or None


def _float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_city(xml_path: Path, *, xml_relpath_from_site: str) -> City:
    root = ET.parse(xml_path).getroot()
    city_id = root.attrib["id"]
    name = root.attrib["name"]

    loc = root.find("location")
    if loc is None:
        raise ValueError(f"Missing <location> in {xml_path}")
    lat = float(loc.attrib["lat"])
    lon = float(loc.attrib["lon"])
    zoom = _int(loc.attrib.get("zoom"))

    intro = _text(root.find("intro"))

    stats_el = root.find("stats")
    stats = CityStats(
        safety=_float(_text(stats_el.find("safety")) if stats_el is not None else None),
        cost_of_living=_float(_text(stats_el.find("costOfLiving")) if stats_el is not None else None),
        green_score=_float(_text(stats_el.find("greenScore")) if stats_el is not None else None),
    )

    sections: list[Section] = []
    sections_el = root.find("sections")
    if sections_el is not None:
        for s in sections_el.findall("section"):
            kind = s.attrib.get("type", "other")
            heading = _text(s.find("heading")) or kind.upper()
            pois: list[Poi] = []
            for p in s.findall("poi"):
                pk = p.attrib.get("type", kind)
                pois.append(
                    Poi(
                        kind=pk,
                        name=_text(p.find("name")) or "Unknown",
                        lat=_float(p.attrib.get("lat")),
                        lon=_float(p.attrib.get("lon")),
                        address=_text(p.find("address")),
                        url=_text(p.find("url")),
                        description=_text(p.find("description")),
                    )
                )
            sections.append(Section(kind=kind, heading=heading, pois=pois))

    return City(
        city_id=city_id,
        name=name,
        lat=lat,
        lon=lon,
        zoom=zoom,
        intro=intro,
        stats=stats,
        sections=sections,
        source_xml_relpath=xml_relpath_from_site,
    )


def escape(s: str) -> str:
    return html.escape(s, quote=True)


def osm_embed_url(*, lat: float, lon: float, zoom: Optional[int]) -> str:
    # bbox size is a heuristic; higher zoom -> smaller bbox.
    # Keep it stable even when zoom is missing.
    z = zoom if zoom is not None else 12
    # Zoom in OSM is 0..19; translate to degrees delta.
    # This is an approximation that produces nice iframes without JS.
    delta = 180.0 / (2 ** (z + 1))
    delta = max(0.01, min(0.25, delta * 6))
    left = lon - delta
    right = lon + delta
    top = lat + delta
    bottom = lat - delta
    return (
        "https://www.openstreetmap.org/export/embed.html"
        f"?bbox={left:.6f}%2C{bottom:.6f}%2C{right:.6f}%2C{top:.6f}"
        f"&layer=mapnik&marker={lat:.6f}%2C{lon:.6f}"
    )


def format_score(x: Optional[float]) -> str:
    if x is None or math.isnan(x):
        return "—"
    # Safety/cost are already on 0-100-ish scale, keep 1 decimal if needed.
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.1f}"


def city_page(city: City) -> str:
    map_url = osm_embed_url(lat=city.lat, lon=city.lon, zoom=city.zoom)
    safe = format_score(city.stats.safety)
    col = format_score(city.stats.cost_of_living)
    green = format_score(city.stats.green_score)

    # Microdata: Place with GeoCoordinates; POIs as TouristAttraction (generic enough)
    # Requirement is "at least one document" — applying it everywhere is fine.
    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="it">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append(f"  <title>{escape(city.name)} — City Guide</title>")
    parts.append('  <link rel="stylesheet" href="../stile.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <header class="topbar">')
    parts.append('    <a class="brand" href="../index.html">City Guides</a>')
    parts.append('    <nav class="topnav">')
    parts.append('      <a href="../index.html">Indice</a>')
    parts.append('      <a href="../report.html">Report</a>')
    parts.append("    </nav>")
    parts.append("  </header>")

    parts.append(f'  <main class="page" itemscope itemtype="https://schema.org/Place">')
    parts.append('    <section class="hero">')
    parts.append('      <div class="hero__text">')
    parts.append(f'        <h1 class="title" itemprop="name">{escape(city.name)}</h1>')
    parts.append('        <div class="metaRow">')
    parts.append(f'          <a class="chip" href="{escape(city.source_xml_relpath)}" download>Scarica XML</a>')
    parts.append('          <span class="chip chip--muted">Fonte: Wikivoyage (export MediaWiki → XML pulito)</span>')
    parts.append("        </div>")
    if city.intro:
        parts.append(f'        <p class="intro" itemprop="description">{escape(city.intro)}</p>')
    parts.append('        <dl class="stats">')
    parts.append(f'          <div class="stat"><dt>Safety</dt><dd>{escape(safe)}</dd></div>')
    parts.append(f'          <div class="stat"><dt>Cost of living</dt><dd>{escape(col)}</dd></div>')
    parts.append(f'          <div class="stat"><dt>Green score</dt><dd>{escape(green)}</dd></div>')
    parts.append("        </dl>")
    parts.append("      </div>")

    parts.append('      <div class="hero__map">')
    parts.append('        <div class="mapCard">')
    parts.append(
        f'          <iframe class="mapFrame" title="Mappa di {escape(city.name)}" '
        f'src="{escape(map_url)}" loading="lazy"></iframe>'
    )
    parts.append('          <div class="mapBar">')
    parts.append(
        f'            <a class="mapLink" href="https://www.openstreetmap.org/?mlat={city.lat:.6f}&mlon={city.lon:.6f}#map={city.zoom or 12}/{city.lat:.6f}/{city.lon:.6f}" target="_blank" rel="noreferrer">Apri in OpenStreetMap</a>'
    )
    parts.append("          </div>")
    parts.append("        </div>")
    parts.append("      </div>")
    parts.append("    </section>")

    parts.append('    <div class="content">')
    parts.append('      <div itemprop="geo" itemscope itemtype="https://schema.org/GeoCoordinates">')
    parts.append(f'        <meta itemprop="latitude" content="{city.lat:.6f}">')
    parts.append(f'        <meta itemprop="longitude" content="{city.lon:.6f}">')
    parts.append("      </div>")

    for section in city.sections:
        if not section.pois:
            continue
        parts.append('      <section class="block">')
        parts.append(f'        <h2 class="block__title">{escape(section.heading.title())}</h2>')
        parts.append('        <div class="grid">')
        for poi in section.pois:
            parts.append('          <article class="card" itemscope itemtype="https://schema.org/TouristAttraction">')
            parts.append(f'            <h3 class="card__title" itemprop="name">{escape(poi.name)}</h3>')
            if poi.address:
                parts.append(f'            <p class="card__meta">{escape(poi.address)}</p>')
            if poi.url:
                parts.append(
                    f'            <p class="card__meta"><a href="{escape(poi.url)}" target="_blank" rel="noreferrer" itemprop="url">Sito</a></p>'
                )
            if poi.description:
                parts.append(f'            <p class="card__desc" itemprop="description">{escape(poi.description)}</p>')
            if poi.lat is not None and poi.lon is not None:
                parts.append('            <div itemprop="geo" itemscope itemtype="https://schema.org/GeoCoordinates">')
                parts.append(f'              <meta itemprop="latitude" content="{poi.lat:.6f}">')
                parts.append(f'              <meta itemprop="longitude" content="{poi.lon:.6f}">')
                parts.append("            </div>")
            parts.append("          </article>")
        parts.append("        </div>")
        parts.append("      </section>")

    parts.append("    </div>")
    parts.append("  </main>")
    parts.append('  <footer class="footer">')
    parts.append("    <p>Progetto TEAM — Text Extraction Analysis and Manipulation</p>")
    parts.append("  </footer>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


def index_page(cities: list[City]) -> str:
    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="it">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>City Guides — Indice</title>")
    parts.append('  <link rel="stylesheet" href="stile.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <header class="topbar">')
    parts.append('    <a class="brand" href="index.html">City Guides</a>')
    parts.append('    <nav class="topnav">')
    parts.append('      <a href="index.html">Indice</a>')
    parts.append('      <a href="report.html">Report</a>')
    parts.append("    </nav>")
    parts.append("  </header>")

    parts.append('  <main class="page">')
    parts.append('    <section class="hero hero--compact">')
    parts.append('      <div class="hero__text">')
    parts.append("        <h1 class=\"title\">Indice città</h1>")
    parts.append("        <p class=\"intro\">Pagine HTML generate da XML validi (DTD) estratti da Wikivoyage.</p>")
    parts.append("      </div>")
    parts.append("    </section>")

    parts.append('    <section class="block">')
    parts.append('      <div class="grid grid--list">')
    for c in sorted(cities, key=lambda x: x.name.lower()):
        parts.append('        <article class="card card--row">')
        parts.append(f'          <h2 class="card__title"><a href="cities/{escape(c.city_id)}.html">{escape(c.name)}</a></h2>')
        parts.append('          <div class="pillRow">')
        parts.append(f'            <span class="pill">Safety: {escape(format_score(c.stats.safety))}</span>')
        parts.append(f'            <span class="pill">Cost: {escape(format_score(c.stats.cost_of_living))}</span>')
        parts.append(f'            <span class="pill">Green: {escape(format_score(c.stats.green_score))}</span>')
        parts.append("          </div>")
        parts.append("        </article>")
    parts.append("      </div>")
    parts.append("    </section>")
    parts.append("  </main>")
    parts.append('  <footer class="footer"><p>Progetto TEAM — dataset: 30 città</p></footer>')
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


def report_page(cities: list[City]) -> str:
    def topn(key, n=5, reverse=True):
        vals = [(c, key(c)) for c in cities if key(c) is not None]
        vals.sort(key=lambda x: x[1], reverse=reverse)
        return vals[:n]

    top_safety = topn(lambda c: c.stats.safety, n=5, reverse=True)
    low_cost = topn(lambda c: c.stats.cost_of_living, n=5, reverse=False)
    top_green = topn(lambda c: c.stats.green_score, n=5, reverse=True)

    def block(title: str, rows: list[tuple[City, float]], fmt=lambda x: f"{x:.1f}"):
        out: list[str] = []
        out.append('    <section class="block">')
        out.append(f'      <h2 class="block__title">{escape(title)}</h2>')
        out.append('      <ol class="rank">')
        for c, v in rows:
            out.append('        <li class="rank__item">')
            out.append(f'          <a class="rank__link" href="cities/{escape(c.city_id)}.html">{escape(c.name)}</a>')
            out.append(f'          <span class="rank__value">{escape(fmt(v))}</span>')
            out.append("        </li>")
        out.append("      </ol>")
        out.append("    </section>")
        return "\n".join(out)

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="it">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>City Guides — Report</title>")
    parts.append('  <link rel="stylesheet" href="stile.css">')
    parts.append("</head>")
    parts.append("<body>")
    parts.append('  <header class="topbar">')
    parts.append('    <a class="brand" href="index.html">City Guides</a>')
    parts.append('    <nav class="topnav">')
    parts.append('      <a href="index.html">Indice</a>')
    parts.append('      <a href="report.html">Report</a>')
    parts.append("    </nav>")
    parts.append("  </header>")

    parts.append('  <main class="page">')
    parts.append('    <section class="hero hero--compact">')
    parts.append('      <div class="hero__text">')
    parts.append('        <h1 class="title">Report</h1>')
    parts.append('        <p class="intro">Classifiche calcolate a partire da <code>city_indices.json</code> e collegate alle pagine città.</p>')
    parts.append("      </div>")
    parts.append("    </section>")

    parts.append(block("Top 5 Safety", top_safety))
    parts.append(block("Top 5 Green score", top_green))
    parts.append(block("Top 5 Low cost of living", low_cost))

    parts.append("  </main>")
    parts.append('  <footer class="footer"><p>Progetto TEAM — report automatico</p></footer>')
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


def main() -> int:
    base = Path(__file__).resolve().parent
    clean_dir = base / "clean_xml"
    site_dir = base / "site"
    cities_dir = site_dir / "cities"
    cities_dir.mkdir(parents=True, exist_ok=True)

    cities: list[City] = []
    for xml_path in sorted(clean_dir.glob("*.xml")):
        rel_from_city = f"../../clean_xml/{xml_path.name}"
        cities.append(parse_city(xml_path, xml_relpath_from_site=rel_from_city))

    # Write pages
    (site_dir / "index.html").write_text(index_page(cities), encoding="utf-8")
    (site_dir / "report.html").write_text(report_page(cities), encoding="utf-8")
    for c in cities:
        (cities_dir / f"{c.city_id}.html").write_text(city_page(c), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

