"""Modele Pydantic canonice SOLOMONAR.

Unifică zeci de surse eterogene în entități comune. Vezi docs/02-DATA-MODEL.md.
Toate entitățile poartă `sources: list[SourceRef]` (provenance).
"""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from solomonar_core.provenance import SourceRef


def make_id(prefix: str, *parts: object) -> str:
    """ID determinist: prefix + sha256(parts)[:16]. Stabil cât timp `parts` e stabil.

    Folosit pentru entități cu cheie naturală (ex. Company după CUI). Pentru Person,
    ID-ul vine din PersonRegistry (resolve), nu de aici.
    """
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


# --------------------------------------------------------------------------- #
# Enums                                                                        #
# --------------------------------------------------------------------------- #
class OrgType(StrEnum):
    PARLIAMENT_CHAMBER = "parliament_chamber"
    GOVERNMENT = "government"
    MINISTRY = "ministry"
    AGENCY = "agency"
    AUTHORITY = "authority"
    DECONCENTRATED = "deconcentrated"
    LOCAL_COUNCIL_BODY = "local_council_body"
    COURT = "court"
    OTHER = "other"


class Tier(StrEnum):
    PARLIAMENT = "parliament"
    CENTRAL = "central"
    SUBORDINATED = "subordinated"
    DECONCENTRATED = "deconcentrated"
    LOCAL_AUTONOMY = "local_autonomy"


class RoleType(StrEnum):
    ELECTED = "elected"
    APPOINTED = "appointed"
    BOARD = "board"          # CA / consiliu de supraveghere
    MANAGEMENT = "management"  # directorat / director general
    CIVIL_SERVANT = "civil_servant"


class DeclType(StrEnum):
    AVERE = "avere"
    INTERESE = "interese"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    RADIATA = "radiata"
    INSOLVENTA = "insolventa"
    UNKNOWN = "unknown"


class EdgeType(StrEnum):
    HOLDS_POSITION = "HOLDS_POSITION"
    MEMBER_OF_BOARD = "MEMBER_OF_BOARD"
    OWNS_SHARE = "OWNS_SHARE"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    CONTROLS = "CONTROLS"
    AWARDED_CONTRACT = "AWARDED_CONTRACT"
    DECLARED = "DECLARED"
    SUBORDINATE_OF = "SUBORDINATE_OF"
    LEGAL_REP = "LEGAL_REP"  # reprezentant legal (Person → Company), din ONRC


# --------------------------------------------------------------------------- #
# Entități core                                                                #
# --------------------------------------------------------------------------- #
class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)
    sources: list[SourceRef] = Field(default_factory=list)


class Person(_Base):
    romega_id: str = Field(..., description="'p:...' atribuit de PersonRegistry")
    full_name: str
    aliases: list[str] = Field(default_factory=list)
    birth_date: date | None = None
    county: str | None = None
    # crosswalk către ID-uri externe (sistem -> listă de ID-uri)
    external_ids: dict[str, list[str]] = Field(default_factory=dict)
    # NU stocăm: CNP, adresă completă, semnătură (redactate legal — vezi docs/04)


class Organization(_Base):
    romega_id: str
    name: str
    short_name: str | None = None
    type: OrgType = OrgType.OTHER
    tier: Tier = Tier.CENTRAL
    parent: str | None = None
    tutelary_authority: str | None = None
    domain: str | None = None
    county: str | None = None  # pentru deconcentrate / local
    cif: str | None = None
    valid_from: date | None = None  # instituțiile se versionează în timp
    valid_to: date | None = None
    placeholder: bool = False  # True = nod generat din config/șablon (NU scrapuit individual)


class FinancialYear(BaseModel):
    year: int
    turnover_ron: float | None = None
    profit_ron: float | None = None
    employees: int | None = None


class OwnershipStake(BaseModel):
    holder_id: str  # romega_id Person sau Company
    company_id: str
    percent: float | None = None
    role: str | None = None  # asociat | actionar


class Company(_Base):
    romega_id: str  # 'c:...'
    cui: int
    name: str
    reg_com: str | None = None
    caen: str | None = None
    status: CompanyStatus = CompanyStatus.UNKNOWN
    vat_payer: bool | None = None
    is_soe: bool = False
    tutelary_authority: str | None = None  # pentru SOE
    county: str | None = None             # județ (din companiidestat)
    sector: str | None = None             # sector economic (din companiidestat)
    bvb_listed: bool | None = None        # listată la BVB
    financial_status: str | None = None   # PROFIT/PIERDERE/... (companiidestat)
    legal_reps: list[str] = Field(default_factory=list)  # romega_id Person
    shareholders: list[OwnershipStake] = Field(default_factory=list)
    financials: list[FinancialYear] = Field(default_factory=list)

    @classmethod
    def id_for_cui(cls, cui: int) -> str:
        return make_id("c", cui)


class Position(BaseModel):
    person_id: str
    org_id: str | None = None
    company_id: str | None = None
    role: str
    role_type: RoleType
    start_date: date | None = None
    end_date: date | None = None
    remuneration_ron: float | None = None
    source_legislature: str | None = None


class Declaration(_Base):
    romega_id: str
    person_id: str
    org_id: str | None = None
    type: DeclType
    year: int
    filed_at: date | None = None
    pdf_url: str
    is_native_pdf: bool = True  # 2022+ text vs pre-2022 scanat (OCR)


class Contract(_Base):
    romega_id: str
    contracting_authority_id: str  # Organization
    supplier_id: str  # Company
    amount: float
    currency: str = "RON"
    award_date: date | None = None
    cpv: str | None = None
    procedure_type: str | None = None
    title: str | None = None


class Edge(BaseModel):
    """O muchie în graf (forma persistată în DuckDB)."""

    src: str
    dst: str
    type: EdgeType
    props: dict = Field(default_factory=dict)
    sources: list[SourceRef] = Field(default_factory=list)
