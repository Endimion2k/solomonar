"""Connector generic `institutie` — transformă config/sources.yaml în entități Organization.

Cel mai mare levier al Fazei 5: ministerele, agențiile centrale, camerele parlamentului devin
noduri `Organization` în graf, 100% din config (zero cod per instituție). Plus:
- subordinate_edges: SUBORDINATE_OF (minister → guvern)
- find_declaration_links: detectează linkuri PDF de declarații (pattern comun pe site-urile .gov.ro)

`build_organizations` primește lista APLATIZATĂ (pipeline.config.iter_sources), deci acest
modul NU depinde de pipeline — doar de solomonar_core.

NOTĂ: rezoluția autorității tutelare a SOE (nume → org id slug) e un pas ulterior — momentan
CONTROLS folosește make_id pe NUMELE autorității, distinct de org-ul cu id-slug.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from solomonar_core.models import Edge, EdgeType, Organization, OrgType, Tier, make_id
from solomonar_core.names import name_key
from solomonar_core.parse import selector
from solomonar_core.provenance import SourceRef

CATEGORY_TYPE = {
    "government": OrgType.GOVERNMENT,
    "ministry": OrgType.MINISTRY,
    "agency": OrgType.AGENCY,
    "deconcentrated": OrgType.DECONCENTRATED,
    "local": OrgType.LOCAL_COUNCIL_BODY,
    "parliament": OrgType.PARLIAMENT_CHAMBER,
}
TIER_MAP = {
    "central": Tier.CENTRAL,
    "subordinated": Tier.SUBORDINATED,
    "deconcentrated": Tier.DECONCENTRATED,
    "parliament": Tier.PARLIAMENT,
    "local_autonomy": Tier.LOCAL_AUTONOMY,
}

_RE_DECL = re.compile(r"declarat|avere|interese", re.IGNORECASE)


def org_id(source_id: str) -> str:
    return make_id("o", source_id)


def _is_institution(s: dict, groups: set[str]) -> bool:
    sid = s.get("id")
    if not sid or sid in groups:          # umbrella group cu `items`
        return False
    if s.get("service_types"):            # group templated (deconcentrate/local)
        return False
    return s.get("category") in CATEGORY_TYPE


def build_organizations(
    sources_flat: list[dict], source: SourceRef | None = None
) -> list[Organization]:
    """Construiește Organization din lista aplatizată de surse (iter_sources)."""
    groups = {s["parent_group"] for s in sources_flat if s.get("parent_group")}
    orgs: list[Organization] = []
    seen: set[str] = set()
    for s in sources_flat:
        if not _is_institution(s, groups):
            continue
        sid = s["id"]
        if sid in seen:
            continue
        seen.add(sid)
        domain = s.get("domain") or s.get("base_url")
        orgs.append(
            Organization(
                romega_id=org_id(sid),
                name=s.get("name", sid),
                type=CATEGORY_TYPE[s["category"]],
                tier=TIER_MAP.get(s.get("tier", ""), Tier.CENTRAL),
                domain=domain,
                sources=[source] if source else [],
            )
        )
    return orgs


def resolve_org_by_name(name: str, orgs: list[Organization]) -> str | None:
    """Mapează un nume de instituție (ex. autoritate tutelară SOE) → romega_id de Organization.

    Folosește name_key (invariant la ordine/diacritice). Exact, apoi containment.
    """
    if not name:
        return None
    target = name_key(name)
    if not target:
        return None
    for o in orgs:
        if name_key(o.name) == target:
            return o.romega_id
    for o in orgs:
        ok = name_key(o.name)
        if ok and (target in ok or ok in target):
            return o.romega_id
    return None


def subordinate_edges(sources_flat: list[dict]) -> list[Edge]:
    """SUBORDINATE_OF: fiecare minister → guvern (relația sigură din config)."""
    groups = {s["parent_group"] for s in sources_flat if s.get("parent_group")}
    gov = org_id("gov")
    edges: list[Edge] = []
    for s in sources_flat:
        if _is_institution(s, groups) and s.get("category") == "ministry":
            edges.append(Edge(src=org_id(s["id"]), dst=gov, type=EdgeType.SUBORDINATE_OF))
    return edges


# 41 județe + București (42 unități pentru servicii deconcentrate).
COUNTIES = [
    "Alba", "Arad", "Argeș", "Bacău", "Bihor", "Bistrița-Năsăud", "Botoșani", "Brașov",
    "Brăila", "Buzău", "Caraș-Severin", "Călărași", "Cluj", "Constanța", "Covasna",
    "Dâmbovița", "Dolj", "Galați", "Giurgiu", "Gorj", "Harghita", "Hunedoara", "Ialomița",
    "Iași", "Ilfov", "Maramureș", "Mehedinți", "Mureș", "Neamț", "Olt", "Prahova",
    "Satu Mare", "Sălaj", "Sibiu", "Suceava", "Teleorman", "Timiș", "Tulcea", "Vaslui",
    "Vâlcea", "Vrancea", "București",
]


def generate_deconcentrated(
    service_types: dict[str, list[str]],
    counties: list[str] | None = None,
    source: SourceRef | None = None,
) -> list[Organization]:
    """Generează Organization deconcentrate (Tier 3): fiecare tip de serviciu × județ.

    Ex.: DSP × 42 → 'DSP Alba', ..., 'DSP București'. Config-driven, zero cod per instituție.
    NOTĂ: unele servicii sunt regionale (DGRFP/DRV/DJS) — generarea per-județ le supraestimează.
    """
    counties = counties or COUNTIES
    orgs: list[Organization] = []
    for services in service_types.values():
        for svc in services:
            for county in counties:
                name = f"{svc} {county}"
                orgs.append(
                    Organization(
                        romega_id=make_id("o", name),
                        name=name,
                        short_name=svc,
                        type=OrgType.DECONCENTRATED,
                        tier=Tier.DECONCENTRATED,
                        county=county,
                        placeholder=True,
                        sources=[source] if source else [],
                    )
                )
    return orgs


def build_deconcentrated_from_config(
    sources_flat: list[dict], counties: list[str] | None = None
) -> list[Organization]:
    """Generează toate instituțiile deconcentrate din intrarea `deconcentrate` din sources.yaml."""
    out: list[Organization] = []
    for s in sources_flat:
        if s.get("category") == "deconcentrated" and s.get("service_types"):
            out.extend(generate_deconcentrated(s["service_types"], counties))
    return out


def build_local_from_config(
    sources_flat: list[dict], counties: list[str] | None = None
) -> list[Organization]:
    """Generează instituțiile din subordinea Consiliilor Județene (axă SEPARATĂ de stat central).

    tier=LOCAL_AUTONOMY (NU deconcentrate). Ex.: DGASPC, DJEP × județe.
    """
    counties = counties or COUNTIES
    out: list[Organization] = []
    for s in sources_flat:
        if s.get("category") != "local" or not s.get("service_types"):
            continue
        svcs = s["service_types"]
        services = svcs if isinstance(svcs, list) else [x for v in svcs.values() for x in v]
        for svc in services:
            for county in counties:
                name = f"{svc} {county}"
                out.append(
                    Organization(
                        romega_id=make_id("o", name),
                        name=name,
                        short_name=svc,
                        type=OrgType.LOCAL_COUNCIL_BODY,
                        tier=Tier.LOCAL_AUTONOMY,
                        county=county,
                        placeholder=True,
                    )
                )
    return out


SECTION_KW = {
    "conducere": re.compile(r"conducere|cabinet|ministr|secretar de stat", re.IGNORECASE),
    "declaratii": re.compile(r"declarat\w*\s*(de\s*)?aver|aver\w*.{0,8}interes", re.IGNORECASE),
    "integritate": re.compile(r"integritate", re.IGNORECASE),
    "transparenta": re.compile(r"transparen\w*\s*decizional", re.IGNORECASE),
}


def find_institution_sections(html: bytes | str, base: str = "") -> dict:
    """Detectează secțiunile-cheie ale unui site de instituție (conducere, declarații, integritate)."""
    sel = selector(html)
    found: dict[str, str] = {}
    for a in sel.css("a"):
        href = a.attrib.get("href", "")
        if not href:
            continue
        text = " ".join(t.strip() for t in a.css("::text").getall() if t.strip())
        blob = f"{href} {text}"
        for cat, rx in SECTION_KW.items():
            if cat not in found and rx.search(blob):
                found[cat] = urljoin(base + "/", href)
    return found


def find_declaration_links(html: bytes | str, base: str = "") -> list[str]:
    """Detectează linkuri PDF de declarații de avere/interese (pattern comun .gov.ro)."""
    sel = selector(html)
    out: list[str] = []
    seen: set[str] = set()
    for a in sel.css("a"):
        href = a.attrib.get("href", "")
        if not href or ".pdf" not in href.lower():
            continue
        text = " ".join(a.css("::text").getall())
        if _RE_DECL.search(href) or _RE_DECL.search(text):
            url = urljoin(base, href)
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out


# Excludem ghiduri/formulare/legi (nu sunt declarații completate).
_RE_GUIDE = re.compile(r"ghid|formular|model|instruct|incompat|nomenclat|/lege|cerere|/anexa", re.IGNORECASE)
_RE_SUBPAGE = re.compile(r"declarat|avere|integritate", re.IGNORECASE)


def crawl_declaration_pdfs(
    client, start_url: str, source_id: str, domain: str, max_depth: int = 2, max_pdfs: int = 200
) -> list[str]:
    """Crawl BFS depth-limited pe un site de instituție → toate PDF-urile de declarații.

    Folosește client.fetch_many (PARALEL + cache bronze). Urmărește sub-paginile care conțin
    'declarat/avere/integritate' (până la max_depth), strânge PDF-urile (excluzând ghiduri/formulare).
    """
    pdfs: set[str] = set()
    visited: set[str] = set()
    frontier = [start_url]
    for depth in range(max_depth + 1):
        frontier = [u for u in frontier if u not in visited]
        if not frontier or len(pdfs) >= max_pdfs:
            break
        for u in frontier:
            visited.add(u)
        fetched = client.fetch_many([(u, source_id, ".html") for u in frontier], workers=6)
        next_frontier: set[str] = set()
        for page_url, content in fetched.items():
            if not content:
                continue
            for a in selector(content).css("a"):
                href = a.attrib.get("href", "")
                if not href:
                    continue
                full = urljoin(page_url, href)
                net = urlparse(full).netloc
                if net and domain not in net:
                    continue
                if full.lower().split("?")[0].endswith(".pdf"):
                    if not _RE_GUIDE.search(full):
                        pdfs.add(full)
                elif depth < max_depth and full not in visited:
                    text = " ".join(a.css("::text").getall())
                    if _RE_SUBPAGE.search(href + " " + text):
                        next_frontier.add(full)
        frontier = list(next_frontier)
    return sorted(pdfs)[:max_pdfs]
