"""Harvest subvenții de stat per partid politic → ROMEGA.

Sursa: EFOR / banipartide.ro/subventii — un raport public Google Looker Studio
(report id b0177427-ae62-4d70-8c27-0215005733b4). Pagina banipartide.ro doar
înglobează un <iframe> Looker; tabelele HTML de pe pagină sunt layout, nu date.

Cum extragem (investigat live):
  Looker Studio servește datele componentelor prin endpoint-ul intern POST
  `/embed/batchedDataV2`. Corpul cererii e un `datasetSpec` construit client-side
  (datasourceId, queryFields cu sourceFieldName intern). Componenta tabel-pivot
  `cd-h18oxfl6dd` interoghează 3 câmpuri:
    - `_2125_`        -> Anul   (int; e stocat ca an, nu dată reală)
    - `_n1911542674_` -> Partid (string)
    - `_2588566_`     -> Subvenție (sumă, aggregation=6 = SUM)

  Prima cerere a componentei cere `createSnapshot:true` și pică cu
  SNAPSHOT_WITH_NON_REAGGREGATABLE. Re-emisă cu `createSnapshot:false` întoarce
  TOATE rândurile (an × partid), ca array-uri paralele de coloane.

  IMPORTANT — granularitate: câmpul de timp expus de raport (`_2125_`) e ANUL,
  nu luna. Raportul public nu expune granularitate lunară prin nicio componentă
  (datasource-ul are doar An/Partid/Sumă agregat). Deci producem ANUAL per partid;
  `luna` rămâne null. Cifrele coincid cu totalurile EFOR (2025 ≈ 232.046.000 lei).

Reproductibilitate: folosim Playwright (chromium, instalat în venv) ca să avem
sesiunea/cookie-urile corecte, apoi facem fetch în contextul paginii. Fără browser,
cererea e respinsă (lipsesc cookie-uri/anti-CSRF).

Output: data/v1/partide/subventii.json  -> {an, luna, partid, suma_lei}
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPORT_ID = "b0177427-ae62-4d70-8c27-0215005733b4"
PAGE_ID = "p_qm7wece6dd"
DATASOURCE_ID = "4a8a9641-ea4c-4296-91c9-a9c02116bef7"
COMPONENT_ID = "cd-h18oxfl6dd"  # tabelul pivot An/Partid/Subvenție

EMBED_URL = (
    f"https://lookerstudio.google.com/embed/reporting/{REPORT_ID}/page/{PAGE_ID}"
)
BATCH_PATH = "/embed/batchedDataV2?appVersion=20260531_0000"

OUT_DIR = os.path.join(ROOT, "data", "v1", "partide")
OUT_FILE = os.path.join(OUT_DIR, "subventii.json")

# Field name (datasource) pentru: An, Partid, Sumă.
FIELD_AN = "_2125_"
FIELD_PARTID = "_n1911542674_"
FIELD_SUMA = "_2588566_"

# JS care rulează în contextul paginii Looker (cookie-uri corecte) și întoarce
# răspunsul brut batchedDataV2 pentru tabelul pivot, fără snapshot.
FETCH_JS = r"""
async ({batchPath, datasourceId, reportId, pageId, componentId, fAn, fPartid, fSuma}) => {
  const body = {
    dataRequest: [{
      requestContext: {
        reportContext: { reportId, pageId, mode: 1, componentId, displayType: "pivot-table" },
        requestMode: 0
      },
      datasetSpec: {
        dataset: [{ datasourceId, revisionNumber: 0, parameterOverrides: [] }],
        queryFields: [
          { name: "qf_an",     datasetNs: "d0", tableNs: "t0", dataTransformation: { sourceFieldName: fAn } },
          { name: "qf_partid", datasetNs: "d0", tableNs: "t0", dataTransformation: { sourceFieldName: fPartid } },
          { name: "qf_suma",   datasetNs: "d0", tableNs: "t0", dataTransformation: { sourceFieldName: fSuma, aggregation: 6 } }
        ],
        sortData: [],
        includeRowsCount: true,
        relatedDimensionMask: { addDisplay: false, addUniqueId: false, addLatLong: false },
        dsFilterOverrides: [], filters: [], features: [], dateRanges: [],
        contextNsCount: 1, dateRangeDimensions: [], calculatedField: [],
        needGeocoding: false, geoFieldMask: [], multipleGeocodeFields: [],
        cacheOptions: { createSnapshot: false },
        timezone: "Europe/Bucharest"
      }
    }]
  };
  const r = await fetch(batchPath, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include"
  });
  return await r.text();
}
"""


def _strip_xssi(text: str) -> str:
    """Looker prefixează răspunsurile JSON cu )]}' anti-XSSI."""
    text = text.lstrip()
    if text.startswith(")]}'"):
        nl = text.find("\n")
        text = text[nl + 1 :] if nl >= 0 else text[4:]
    return text.strip()


def _parse_pivot(raw: str) -> list[dict]:
    """Parsează coloanele paralele (an / partid / sumă) în înregistrări."""
    data = json.loads(_strip_xssi(raw))
    resp = data["dataResponse"][0]
    if "errorStatus" in resp and "dataSubset" not in resp:
        raise RuntimeError(f"Looker error: {resp['errorStatus']}")
    subset = resp["dataSubset"][0]
    table = subset["dataset"]["tableDataset"]
    cols = table["column"]
    col_info = table["columnInfo"]

    # Mapează numele coloanei -> valorile (string/double).
    by_name: dict[str, list] = {}
    for info, col in zip(col_info, cols):
        if "stringColumn" in col:
            vals = col["stringColumn"]["values"]
        elif "doubleColumn" in col:
            vals = col["doubleColumn"]["values"]
        elif "longColumn" in col:
            vals = col["longColumn"]["values"]
        else:
            vals = []
        by_name[info["name"]] = vals

    ani = by_name.get("qf_an", [])
    partide = by_name.get("qf_partid", [])
    sume = by_name.get("qf_suma", [])
    n = min(len(ani), len(partide), len(sume))
    if not n:
        raise RuntimeError("Pivot gol — nicio înregistrare returnată.")

    out = []
    for i in range(n):
        an = int(round(float(ani[i])))
        partid = str(partide[i]).strip()
        suma = round(float(sume[i]), 2)
        # rotunjește la întreg dacă diferența e neglijabilă (lei)
        if abs(suma - round(suma)) < 0.005:
            suma = int(round(suma))
        out.append({"an": an, "luna": None, "partid": partid, "suma_lei": suma})
    return out


def fetch_records() -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        page = ctx.new_page()
        page.goto(EMBED_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)  # lasă componentele să se inițializeze
        raw = page.evaluate(
            FETCH_JS,
            {
                "batchPath": BATCH_PATH,
                "datasourceId": DATASOURCE_ID,
                "reportId": REPORT_ID,
                "pageId": PAGE_ID,
                "componentId": COMPONENT_ID,
                "fAn": FIELD_AN,
                "fPartid": FIELD_PARTID,
                "fSuma": FIELD_SUMA,
            },
        )
        browser.close()
    return _parse_pivot(raw)


def main() -> int:
    print(f"[1/4] Încarc embed Looker: {EMBED_URL}")
    records = fetch_records()
    records.sort(key=lambda r: (r["an"], r["partid"]))
    print(f"[2/4] Extras {len(records)} înregistrări an×partid.")

    # Verificare: totaluri pe an (pentru sanity check).
    by_year: dict[int, float] = {}
    by_party: dict[str, float] = {}
    for r in records:
        by_year[r["an"]] = by_year.get(r["an"], 0) + r["suma_lei"]
        by_party[r["partid"]] = by_party.get(r["partid"], 0) + r["suma_lei"]

    total_2025 = by_year.get(2025, 0)
    print(f"[3/4] Total 2025 = {total_2025:,.0f} lei (așteptat ≈ 232.046.000)")
    ani = sorted(by_year)
    print(f"      Acoperire ani: {ani[0]}–{ani[-1]} ({len(ani)} ani)")
    print(f"      Partide distincte: {len(by_party)}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sursa": "EFOR / banipartide.ro/subventii (Google Looker Studio)",
        "report_id": REPORT_ID,
        "metoda": "batchedDataV2 (createSnapshot:false) via Playwright",
        "granularitate": "anuala (raportul public nu expune luna; campul 'luna' e null)",
        "total": len(records),
        "totaluri_pe_an": {str(y): round(by_year[y], 2) for y in ani},
        "subventii": records,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[4/4] Scris {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
