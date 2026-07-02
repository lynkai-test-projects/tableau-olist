"""Export the live "Olist Marketplace Overview" dashboard from Tableau Cloud to a
static site folder (PNG + PDF + index.html) for GitHub Pages.

Pure stdlib (urllib) — no pip install. Runs on GitHub's runners (clean internet,
default TLS) and locally (set TABLEAU_CA_BUNDLE to the corporate CA bundle if your
network MITM-intercepts TLS).

Env:
  TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET   (required — a Tableau Personal Access Token)
  TABLEAU_SERVER   (default https://prod-uk-a.online.tableau.com)
  TABLEAU_SITE     (default laila-5f52a99af6)
  TABLEAU_API_VER  (default 3.19)
  DASHBOARD_VIEW   (default "Olist Marketplace Overview")
  TABLEAU_CA_BUNDLE (optional path to a CA bundle for local proxied networks)

Usage:  python publish/export_dashboard.py [output_dir]   (default: site)
"""
from __future__ import annotations

import os
import ssl
import sys
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib import request, error

NS = {"t": "http://tableau.com/api"}
SERVER = os.environ.get("TABLEAU_SERVER", "https://prod-uk-a.online.tableau.com")
SITE = os.environ.get("TABLEAU_SITE", "laila-5f52a99af6")
VER = os.environ.get("TABLEAU_API_VER", "3.19")
VIEW_NAME = os.environ.get("DASHBOARD_VIEW", "Olist Marketplace Overview")
_CA = os.environ.get("TABLEAU_CA_BUNDLE")
CTX = ssl.create_default_context(cafile=_CA if _CA and os.path.exists(_CA) else None)


def api(path: str) -> str:
    return f"{SERVER}/api/{VER}/{path}"


def call(url, data=None, method="GET", headers=None, ctype=None) -> bytes:
    h = dict(headers or {})
    if ctype:
        h["Content-Type"] = ctype
    req = request.Request(url, data=data, method=method, headers=h)
    with request.urlopen(req, timeout=120, context=CTX) as resp:
        return resp.read()


def main() -> None:
    name = os.environ.get("TABLEAU_PAT_NAME")
    secret = os.environ.get("TABLEAU_PAT_SECRET")
    if not name or not secret:
        sys.exit("Set TABLEAU_PAT_NAME and TABLEAU_PAT_SECRET (repo secrets).")

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    out.mkdir(parents=True, exist_ok=True)

    body = (f'<tsRequest><credentials personalAccessTokenName="{name}" '
            f'personalAccessTokenSecret="{secret}"><site contentUrl="{SITE}" />'
            f'</credentials></tsRequest>').encode()
    cred = ET.fromstring(call(api("auth/signin"), body, "POST", ctype="application/xml")).find("t:credentials", NS)
    token = cred.get("token")
    site_id = cred.find("t:site", NS).get("id")
    auth = {"X-Tableau-Auth": token}

    views = ET.fromstring(call(api(f"sites/{site_id}/views?pageSize=1000"), headers=auth))
    view_id = next((v.get("id") for v in views.iter("{http://tableau.com/api}view")
                    if v.get("name") == VIEW_NAME), None)
    if not view_id:
        sys.exit(f"View {VIEW_NAME!r} not found on site {SITE}.")

    png = call(api(f"sites/{site_id}/views/{view_id}/image?resolution=high&maxAge=1"), headers=auth)
    (out / "olist_overview.png").write_bytes(png)

    # The PDF is only a "Download" convenience link. Some servers reject the PDF
    # endpoint for large dashboards (HTTP 400) — never let that fail the deploy.
    pdf_link = ""
    try:
        pdf = call(api(f"sites/{site_id}/views/{view_id}/pdf?maxAge=1"), headers=auth)
        (out / "olist_overview.pdf").write_bytes(pdf)
        pdf_link = '<div class="bar"><a class="btn" href="olist_overview.pdf">Download PDF</a></div>'
        print(f"PDF exported ({len(pdf):,} B)")
    except Exception as e:
        print(f"WARN: PDF export skipped ({e}); deploying PNG only.")

    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (out / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist Marketplace Overview</title>
<style>
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; color:#171717; background:#f7f7f8; }}
  header {{ background:#6749F4; color:#fff; padding:18px 24px; }}
  header h1 {{ margin:0; font-size:20px; }}
  header p {{ margin:4px 0 0; opacity:.85; font-size:13px; }}
  main {{ max-width:1000px; margin:24px auto; padding:0 16px; }}
  img {{ width:100%; height:auto; border:1px solid #e5e5e5; border-radius:8px; background:#fff; }}
  .bar {{ margin:12px 0; font-size:14px; }}
  a.btn {{ display:inline-block; background:#6749F4; color:#fff; text-decoration:none; padding:8px 14px; border-radius:6px; }}
  footer {{ color:#78737d; font-size:12px; text-align:center; margin:24px; }}
</style></head>
<body>
  <header><h1>Olist Marketplace Overview</h1><p>Executive dashboard · built on the dbt marts (OLIST.DBT_DEMO)</p></header>
  <main>
    {pdf_link}
    <img src="olist_overview.png" alt="Olist Marketplace Overview dashboard">
    <footer>Snapshot of the live Tableau dashboard · last updated {updated} · auto-published from the tableau-olist repo</footer>
  </main>
</body></html>
""", encoding="utf-8")

    print(f"Wrote {out}/index.html + olist_overview.png ({len(png):,} B)")


if __name__ == "__main__":
    main()
