"""Nivelul de încredere al legăturilor persoană → firmă (fără rețea)."""

import pytest

pytest.importorskip("solomonar_core")
from pipeline.build_gold import nivel_incredere  # noqa: E402


def test_parlamentar_fara_firme_e_high():
    assert nivel_incredere(True, 0, False) == "high"


def test_parlamentar_cu_firme_doar_pe_nume_e_candidat():
    # omonimul de la o companie mare nu devine „confirmat” doar pentru că parlamentarul are dată de naștere
    assert nivel_incredere(True, 3, False) == "candidat"


def test_parlamentar_cu_context_e_high():
    assert nivel_incredere(True, 2, True) == "high"


def test_neparlamentar():
    assert nivel_incredere(False, 2, True) == "context"
    assert nivel_incredere(False, 2, False) == "candidat"
    assert nivel_incredere(False, 0, False) == "candidat"
