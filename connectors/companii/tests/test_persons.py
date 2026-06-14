"""Test rezoluție reprezentanți legali → Person + muchii LEGAL_REP (glue companii↔persoane)."""

from __future__ import annotations

from connectors.companii.persons import resolve_legal_reps
from solomonar_core.models import Company, EdgeType
from solomonar_core.resolve import PersonRegistry


def test_resolve_legal_reps_links_and_dedup():
    c1 = Company(romega_id="c:1", cui=1, name="A SRL", legal_reps=["Popescu Ion"])
    c2 = Company(romega_id="c:2", cui=2, name="B SRL", legal_reps=["POPESCU Ion", "Maria Ionescu"])
    reg = PersonRegistry()

    persons, edges = resolve_legal_reps([c1, c2], reg)

    # „Popescu Ion" = aceeași persoană la ambele firme → 2 persoane unice (+ Maria)
    assert len(persons) == 2
    assert all(e.type == EdgeType.LEGAL_REP for e in edges)
    assert len(edges) == 3  # Popescu→c1, Popescu→c2, Maria→c2

    ion = next(p for p in persons if "opescu" in p.full_name.lower())
    ion_edges = [e for e in edges if e.src == ion.romega_id]
    assert {e.dst for e in ion_edges} == {"c:1", "c:2"}  # aceeași persoană, două firme
