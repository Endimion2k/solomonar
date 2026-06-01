"""Rezolvă reprezentanții legali (nume din dump-ul ONRC) → noduri Person + muchii LEGAL_REP.

Conectează cele două jumătăți ale grafului: companii ↔ persoane. Aceeași persoană care apare
ca reprezentant la mai multe firme se rezolvă la un singur romega_id (prin PersonRegistry) —
deci poți vedea „toate firmele legate de o persoană".
"""

from __future__ import annotations

from romega_core.models import Company, Edge, EdgeType, Person
from romega_core.provenance import SourceRef
from romega_core.resolve import PersonRegistry


def resolve_legal_reps(
    companies: list[Company], registry: PersonRegistry, source: SourceRef | None = None
) -> tuple[list[Person], list[Edge]]:
    """Întoarce (persoane unice, muchii LEGAL_REP person→company)."""
    persons: dict[str, Person] = {}
    edges: list[Edge] = []
    for c in companies:
        for name in c.legal_reps:
            if not name or not name.strip():
                continue
            try:
                match = registry.resolve(name)
            except ValueError:
                continue
            persons.setdefault(
                match.romega_id,
                Person(
                    romega_id=match.romega_id,
                    full_name=name,
                    aliases=[name],
                    sources=[source] if source else [],
                ),
            )
            edges.append(
                Edge(src=match.romega_id, dst=c.romega_id, type=EdgeType.LEGAL_REP, props={"name": name})
            )
    return list(persons.values()), edges
