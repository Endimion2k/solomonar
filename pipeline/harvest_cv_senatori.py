"""CV-uri senatori de pe senat.ro — via simulare postback ASP.NET (lnkBiog).

senat.ro e ASP.NET: biografia se încarcă prin __doPostBack('...lnkBiog'). Simulăm: GET FisaSenator
→ __VIEWSTATE/__EVENTVALIDATION → POST cu __EVENTTARGET=lnkBiog → HTML biografie → studii/experiență.
Scriptabil (fără browser), network senat.ro (paralel-safe). Completează parlament-CV (deputați + senatori).
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

import requests
import urllib3

urllib3.disable_warnings()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline.process_cv import _sections  # noqa: E402

V = os.path.join(ROOT, "data/v1")


def _hidden(t, name):
    m = re.search(rf'id="{name}"\s+value="([^"]*)"', t)
    return unescape(m.group(1)) if m else ""


def _fetch_cv(sen):
    purl = sen.get("profile_url")
    if not purl:
        return None
    try:
        s = requests.Session()
        s.headers["User-Agent"] = "Mozilla/5.0"
        t = s.get(purl, timeout=20, verify=False).text
        # target lnkBiog (encoded &#39;)
        m = re.search(r"__doPostBack\(&#39;([^&]*lnkBiog)&#39;", t) or \
            re.search(r"__doPostBack\('([^']*lnkBiog)'", t)
        target = m.group(1) if m else "ctl00$B_Center$Repeater14$ctl00$lnkBiog"
        data = {"__EVENTTARGET": target, "__EVENTARGUMENT": "",
                "__VIEWSTATE": _hidden(t, "__VIEWSTATE"),
                "__EVENTVALIDATION": _hidden(t, "__EVENTVALIDATION"),
                "__VIEWSTATEGENERATOR": _hidden(t, "__VIEWSTATEGENERATOR")}
        t2 = s.post(purl, data=data, timeout=20, verify=False).text
    except Exception:
        return None
    body = unescape(re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", t2)))
    edu, exp = _sections(body)
    if not edu and not exp:
        return None
    return {"nume": sen.get("name", ""), "senat_guid": sen.get("senat_guid"),
            "legislatura": sen.get("legislatura"), "partid": sen.get("party"),
            "judet": sen.get("judet"), "studii": edu, "experienta": exp, "url": purl}


def main() -> dict:
    d = json.load(open(os.path.join(V, "parlament/senatori.json"), encoding="utf-8"))
    sens = d.get("data") or d.get("senatori")
    sens = sens if isinstance(sens, list) else list(sens.values())
    print(f"CV pe {len(sens)} senatori (postback ASP.NET)...", flush=True)
    out, done = [], 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_fetch_cv, sen) for sen in sens]
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                out.append(r)
            if done % 40 == 0:
                print(f"   {done}/{len(sens)}, {len(out)} cu CV", flush=True)
    out.sort(key=lambda x: x["nume"])
    cu = sum(1 for r in out if r.get("studii"))
    json.dump({"total": len(out), "cu_studii": cu, "cv": out},
              open(os.path.join(V, "companii/cv_senatori.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"PUBLICAT cv_senatori.json: {len(out)} senatori cu CV ({cu} cu studii)", flush=True)
    return {"cv": len(out)}


if __name__ == "__main__":
    main()
