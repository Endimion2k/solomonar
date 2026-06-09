"""Harvest declarații pe SOE-urile MARI ratate de brand-guess (domenii non-brand cunoscute).

Brand-guess a ratat companiile al căror domeniu ≠ brand (Hidroelectrica→hidro.ro). Aici o listă
curată de SOE-uri majore cu domeniile lor → BFS (refolosește harvest_soe_declaratii.harvest_source)
→ PDF-uri declarații → dedup vs corpus existent → _soe2_pdfs.json. Apoi ROMEGA_SRC=soe2 reprocess.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline.harvest_soe_declaratii import harvest_source  # noqa: E402

V = os.path.join(ROOT, "data/v1/declaratii")

# SOE-uri majore cu capital majoritar de stat (nume → domeniu)
BIG_SOE = {
    "Hidroelectrica": "hidro.ro", "Nuclearelectrica": "nuclearelectrica.ro",
    "Romgaz": "romgaz.ro", "Transgaz": "transgaz.ro", "Transelectrica": "transelectrica.ro",
    "Electrica": "electrica.ro", "Conpet": "conpet.ro",
    "Posta Romana": "posta-romana.ro", "Tarom": "tarom.ro", "Metrorex": "metrorex.ro",
    "CNAIR": "cnair.ro", "Aeroporturi Bucuresti": "bucharestairports.ro",
    "CEC Bank": "cec.ro", "Eximbank": "eximbank.ro", "Loteria Romana": "loteriaromana.ro",
    "Salrom": "salrom.ro", "Romsilva": "rosilva.ro", "Apele Romane": "rowater.ro",
    "Antibiotice Iasi": "antibiotice.ro", "IAR Brasov": "iar.ro", "Romarm": "romarm.ro",
    "Unifarm": "unifarm.ro", "Imprimeria Nationala": "cnin.ro", "Santierul Naval Constanta": "snc.ro",
    "Aeroportul Cluj": "airportcluj.ro", "Aeroportul Timisoara": "aeroporturi-timisoara.ro",
    "Complexul Energetic Oltenia": "ceoltenia.ro", "Nuclearmontaj": "nuclearmontaj.ro",
    "CN Administratia Porturilor Maritime": "constantza-port.ro", "Aeroportul Iasi": "aeroport-iasi.ro",
    "RA-APPS": "raapps.ro", "Romaero": "romaero.com", "Avioane Craiova": "acv.ro",
    "Compania Nationala a Cuprului": "cuprumin.ro", "Minvest": "minvest.ro",
}


def main() -> dict:
    # corpus existent (dedup)
    seen = set()
    for f in glob.glob(os.path.join(V, "avere_*.json")) + glob.glob(os.path.join(V, "interese_*.json")):
        for d in json.load(open(f, encoding="utf-8")).get("declaratii", []):
            if d.get("pdf_url"):
                seen.add(d["pdf_url"])
    print(f"corpus existent: {len(seen)} URL-uri", flush=True)

    items = [{"nume": n, "url": f"https://{d}/"} for n, d in BIG_SOE.items()]
    pdf_to_inst = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(harvest_source, s): s["nume"] for s in items}
        for f in as_completed(futs):
            name = futs[f]
            try:
                _, pdfs = f.result()
            except Exception:
                pdfs = {}
            new = {u: i for u, i in pdfs.items() if u not in seen}
            for u, i in new.items():
                pdf_to_inst[u] = i
            if pdfs:
                print(f"   {name[:32]}: {len(pdfs)} PDF ({len(new)} noi)", flush=True)

    json.dump(pdf_to_inst, open(os.path.join(V, "_soe2_pdfs.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nPUBLICAT _soe2_pdfs.json: {len(pdf_to_inst)} PDF-uri NOI din {len(BIG_SOE)} SOE mari", flush=True)
    print("Pas 2: ROMEGA_SRC=soe2 python -m pipeline.harvest_reprocess text 8", flush=True)
    return {"pdfs": len(pdf_to_inst)}


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    main()
