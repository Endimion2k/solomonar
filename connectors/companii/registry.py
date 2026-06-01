"""CompanyRegistry — fuzionează datele de companie din surse multiple, după CUI.

Spre deosebire de persoane (rezoluție fuzzy), companiile au cheie naturală sigură: CUI. Deci
fuziunea e un simplu upsert pe CUI, completând câmpurile lipsă din fiecare sursă (AMEPIP →
is_soe + autoritate; ANAF → status/CAEN/TVA; ONRC → reg_com + reprezentanți).
"""

from __future__ import annotations

from romega_core.models import Company, Edge, EdgeType, make_id

STATE_ORG_ID = "o:stat-roman"


class CompanyRegistry:
    def __init__(self) -> None:
        self._by_cui: dict[int, Company] = {}

    def upsert(self, c: Company) -> Company:
        existing = self._by_cui.get(c.cui)
        if existing is None:
            self._by_cui[c.cui] = c.model_copy(deep=True)
            return self._by_cui[c.cui]
        m = existing
        for field in ("name", "reg_com", "caen", "tutelary_authority"):
            if not getattr(m, field) and getattr(c, field):
                setattr(m, field, getattr(c, field))
        if m.vat_payer is None and c.vat_payer is not None:
            m.vat_payer = c.vat_payer
        if c.is_soe:
            m.is_soe = True
        if c.status and c.status != "unknown":
            m.status = c.status
        if c.financials:
            m.financials = m.financials + c.financials
        if c.legal_reps:
            m.legal_reps = sorted(set(m.legal_reps) | set(c.legal_reps))
        if c.sources:
            m.sources = m.sources + c.sources
        return m

    def all(self) -> list[Company]:
        return list(self._by_cui.values())

    def __len__(self) -> int:
        return len(self._by_cui)


def control_edges(companies: list[Company], state_org_id: str = STATE_ORG_ID) -> list[Edge]:
    """Muchii CONTROLS de la autoritatea tutelară (sau stat) către fiecare SOE."""
    edges: list[Edge] = []
    for c in companies:
        if not c.is_soe:
            continue
        src = make_id("o", c.tutelary_authority) if c.tutelary_authority else state_org_id
        edges.append(
            Edge(src=src, dst=c.romega_id, type=EdgeType.CONTROLS, props={"apt": c.tutelary_authority})
        )
    return edges
