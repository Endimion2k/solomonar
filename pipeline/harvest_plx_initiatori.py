"""Harvest INIȚIATORII proiectelor legislative (PLx) — leagă legislația de persoane în graf.

Pagina proiectului cdep (`/ords/pls/proiecte/upl_pck2015.proiect?cam={cam}&idp={idp}`) listează
inițiatorii: 'Initiator: N deputati+senatori' + link-uri structura.mp?idm=N (= membrii inițiatori)
+ flag Guvern. Idm-urile se leagă la deputați via cdep_idm. Resume-safe (JSONL).
Output data/v1/comisii/plx_initiatori.json + index idm→[plx].
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packages", "solomonar_core"))
from solomonar_core.http import Client  # noqa: E402

V = os.path.join(ROOT, "data/v1")
JL = os.path.join(ROOT, "pipeline", "_plx_init.jsonl")
URL = "https://www.cdep.ro/ords/pls/proiecte/upl_pck2015.proiect?cam={cam}&idp={idp}"


def _parse(txt):
    t = html.unescape(txt.decode("utf-8", "replace") if isinstance(txt, bytes) else txt)
    idm = sorted(set(re.findall(r"structura\w*\.mp\?[^\"']*idm=(\d+)", t)))
    m = re.search(r"Initiator:\s*([^<\n]{0,120})", t)
    linie = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    n = re.search(r"(\d+)\s+deputati", linie)
    guvern = bool(re.search(r"[Gg]uvernul", t[:t.find('Initiator')+400] if 'Initiator' in t else t[:3000]))
    return {"initiatori_idm": idm, "n_initiatori": int(n.group(1)) if n else len(idm),
            "guvern": guvern, "linie": linie[:120]}


def main() -> dict:
    c = Client(throttle_seconds=0.1, timeout=30)
    plx = json.load(open(os.path.join(V, "comisii/plx.json"), encoding="utf-8"))
    rows = plx.get("data") or plx.get("plx") or []
    rows = rows if isinstance(rows, list) else list(rows.values())
    targets = [(r.get("idp"), r.get("camera", "2"), r.get("titlu", "")) for r in rows if r.get("idp")]

    done = {}
    if os.path.exists(JL):
        for line in open(JL, encoding="utf-8"):
            try:
                x = json.loads(line); done[str(x["idp"])] = x
            except Exception:
                pass
    print(f"PLx: {len(targets)} | deja={len(done)}", flush=True)

    fh = open(JL, "a", encoding="utf-8")
    n = 0
    for idp, cam, titlu in targets:
        if str(idp) in done:
            continue
        try:
            raw, _ = c.fetch(URL.format(cam=cam, idp=idp), "cdep", ext=".html")
            rec = _parse(raw)
        except Exception:
            rec = {"initiatori_idm": [], "n_initiatori": 0, "guvern": None, "linie": ""}
        rec.update({"idp": idp, "camera": cam, "titlu": titlu})
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
        done[str(idp)] = rec
        n += 1
        if n % 100 == 0:
            print(f"   {n} | idp={idp} init={rec['n_initiatori']}", flush=True)
        time.sleep(0.05)
    fh.close()

    data = list(done.values())
    # index idm → proiectele inițiate
    idm_plx = {}
    for r in data:
        for idm in r.get("initiatori_idm", []):
            idm_plx.setdefault(idm, []).append({"titlu": r.get("titlu"), "idp": r.get("idp")})
    json.dump({"sursa": "cdep proiect (inițiatori)", "total_plx": len(data),
               "cu_initiatori_parlamentari": sum(1 for r in data if r.get("initiatori_idm")),
               "guvern_initiator": sum(1 for r in data if r.get("guvern")), "plx": data},
              open(os.path.join(V, "comisii/plx_initiatori.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump({"nota": "idm membru cdep → proiectele PLx pe care le-a inițiat", "total_membri": len(idm_plx),
               "index": {k: v[:50] for k, v in idm_plx.items()}},
              open(os.path.join(V, "comisii/plx_initiator_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT plx_initiatori.json: {len(data)} PLx, "
          f"{sum(1 for r in data if r.get('guvern'))} guvern, {len(idm_plx)} membri inițiatori", flush=True)
    return {"plx": len(data), "membri": len(idm_plx)}


if __name__ == "__main__":
    main()
