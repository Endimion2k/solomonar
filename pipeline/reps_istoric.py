"""Istoricul reprezentanților legali ONRC: cine era înainte, cine e acum.

Dump-ul ONRC are doar starea curentă (fără date de numire sau revocare). Istoricul se construiește
comparând dump-urile succesive: fiecare reprezentant are data dump-ului în care a apărut prima dată,
iar cine dispare trece la `fosti`, cu ultimul dump în care mai apărea și primul în care lipsea.
Schimbarea reală s-a petrecut undeva între aceste două date.

Câmpuri (datele sunt datele dump-urilor ONRC, ISO):
  reprezentanti: [{nume, calitate, vazut_din, aparut_dupa?}]
      aparut_dupa = data dump-ului anterior, doar când firma era deja urmărită și persoana lipsea atunci
  fosti: [{nume, calitate, vazut_din, vazut_pana_la, absent_din}]
"""

from __future__ import annotations

import re
import unicodedata

_DATA = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def data_dump(eticheta: str | None) -> str | None:
    """'ONRC până la 04.11.2026 (set ...)' -> '2026-11-04'."""
    m = _DATA.search(eticheta or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _norm(s: str) -> str:
    """Aceeași persoană, scrisă diferit între dump-uri (CALIN/CĂLIN, ş/ș, cratimă/spațiu) = aceeași cheie."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    s = re.sub(r"[-‐–.,]", " ", s)
    return " ".join(s.split())


def cheie(r: dict) -> tuple[str, str]:
    return _norm(r.get("nume", "")), _norm(r.get("calitate", ""))


def combina(prev: list[dict], prev_data: str | None, curent: dict[int, list[dict]],
            cur_data: str, nume: dict[int, str]) -> list[dict]:
    """Îmbină starea publicată anterior (`prev`, din dump-ul `prev_data`) cu dump-ul curent.

    `curent`: cui -> reprezentanți citiți acum ({nume, calitate}).
    Fără `prev_data` sau cu același dump nu se înregistrează schimbări (rulare repetată).
    Firmele care lipsesc acum din dump rămân în listă cu `reprezentanti` gol și toți la `fosti`.
    """
    schimbare = bool(prev_data) and prev_data != cur_data
    vechi = {int(c["cui"]): c for c in prev if c.get("cui") is not None}
    out = []
    pastrate = set(vechi) if schimbare else {c for c, v in vechi.items() if v.get("fosti")}
    for cui in sorted(set(curent) | pastrate):
        p = vechi.get(cui) or {}
        p_cur = {cheie(r): r for r in p.get("reprezentanti") or []}
        fosti = list(p.get("fosti") or [])
        acum, vazuti = [], set()
        for r in curent.get(cui, []):
            k = cheie(r)
            if k in vazuti:
                continue
            vazuti.add(k)
            v = p_cur.get(k)
            rec = {"nume": r["nume"], "calitate": r.get("calitate", "")}
            if v:
                rec["vazut_din"] = v.get("vazut_din") or prev_data or cur_data
                if v.get("aparut_dupa"):
                    rec["aparut_dupa"] = v["aparut_dupa"]
            else:
                rec["vazut_din"] = cur_data
                if schimbare and cui in vechi:
                    rec["aparut_dupa"] = prev_data
            acum.append(rec)
        if schimbare:
            for k, v in p_cur.items():
                if k not in vazuti:
                    fosti.append({"nume": v["nume"], "calitate": v.get("calitate", ""),
                                  "vazut_din": v.get("vazut_din") or prev_data,
                                  "vazut_pana_la": prev_data, "absent_din": cur_data})
        rec_c = {"cui": cui, "denumire": nume.get(cui) or p.get("denumire", ""), "reprezentanti": acum}
        if fosti:
            rec_c["fosti"] = fosti
        out.append(rec_c)
    return out


def disparute(prev: list[dict], curent: dict[int, list[dict]]) -> int:
    """Câte firme cu reprezentanți publicate anterior nu mai au niciun reprezentant acum."""
    return sum(1 for c in prev if c.get("reprezentanti") and int(c["cui"]) not in curent)
