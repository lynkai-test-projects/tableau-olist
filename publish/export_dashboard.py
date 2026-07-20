"""Export the live "Olist Marketplace Analytics" dashboards from Tableau Cloud to a static
site folder (one PNG per dashboard + a gallery index.html) for GitHub Pages.

Pure stdlib (urllib) — no pip install. Runs on GitHub's runners (clean internet, default TLS)
and locally (set TABLEAU_CA_BUNDLE to the corporate CA bundle if your network MITM-intercepts TLS).

Env:
  TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET   (required — a Tableau Personal Access Token)
  TABLEAU_SERVER    (default https://prod-uk-a.online.tableau.com)
  TABLEAU_SITE      (default laila-5f52a99af6)
  TABLEAU_API_VER   (default 3.19)
  DASHBOARD_VIEWS   (default the 4 dashboard names, comma-separated)
  TABLEAU_CA_BUNDLE (optional path to a CA bundle for local proxied networks)

Usage:  python publish/export_dashboard.py [output_dir]   (default: site)
"""
from __future__ import annotations

import os
import re
import ssl
import sys
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib import request

NS = {"t": "http://tableau.com/api"}
SERVER = os.environ.get("TABLEAU_SERVER", "https://10ax.online.tableau.com")
SITE = os.environ.get("TABLEAU_SITE", "nba-lynk")
VER = os.environ.get("TABLEAU_API_VER", "3.19")
DEFAULT_VIEWS = "Executive Overview,Growth & Funnel,Delivery Operations,Seller & Customer 360"
VIEWS = [v.strip() for v in os.environ.get("DASHBOARD_VIEWS", DEFAULT_VIEWS).split(",") if v.strip()]
_CA = os.environ.get("TABLEAU_CA_BUNDLE")
CTX = ssl.create_default_context(cafile=_CA if _CA and os.path.exists(_CA) else None)


def api(path: str) -> str:
    return f"{SERVER}/api/{VER}/{path}"


def call(url, data=None, method="GET", headers=None, ctype=None) -> bytes:
    h = dict(headers or {})
    if ctype:
        h["Content-Type"] = ctype
    req = request.Request(url, data=data, method=method, headers=h)
    with request.urlopen(req, timeout=180, context=CTX) as resp:
        return resp.read()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


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

    views_xml = ET.fromstring(call(api(f"sites/{site_id}/views?pageSize=1000"), headers=auth))
    by_name = {v.get("name"): v.get("id") for v in views_xml.iter("{http://tableau.com/api}view")}

    exported = []  # (display_name, png_filename)
    for vname in VIEWS:
        vid = by_name.get(vname)
        if not vid:
            print(f"WARN: view {vname!r} not found on site {SITE}; skipping.")
            continue
        png = call(api(f"sites/{site_id}/views/{vid}/image?resolution=high&maxAge=1"), headers=auth)
        fname = f"olist_{slug(vname)}.png"
        (out / fname).write_bytes(png)
        exported.append((vname, fname))
        print(f"  {vname:<26} -> {fname} ({len(png):,} B)")

    if not exported:
        sys.exit("No dashboards exported — check DASHBOARD_VIEWS / that the workbook is published.")

    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cards = "\n".join(
        f'''    <section class="card" id="{slug(n)}">
      <h2>{n}</h2>
      <img src="{f}" alt="{n} dashboard" loading="lazy">
    </section>''' for n, f in exported
    )
    (out / "index.html").write_text(f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist Marketplace Analytics</title>
<style>
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; color:#171717; background:#f7f7f8; }}
  header {{ background:#6749F4; color:#fff; padding:20px 24px; }}
  header h1 {{ margin:0; font-size:22px; }}
  header p {{ margin:6px 0 0; opacity:.9; font-size:13px; }}
  main {{ max-width:1080px; margin:24px auto; padding:0 16px; }}
  nav {{ margin:0 0 20px; font-size:14px; }}
  nav a {{ color:#6749F4; text-decoration:none; margin-right:14px; }}
  .card {{ margin:0 0 32px; }}
  .card h2 {{ font-size:16px; margin:0 0 8px; }}
  img {{ width:100%; height:auto; border:1px solid #e5e5e5; border-radius:8px; background:#fff; }}
  footer {{ color:#78737d; font-size:12px; text-align:center; margin:24px; }}
</style></head>
<body>
  <header>
    <h1>Olist Marketplace Analytics</h1>
    <p>Executive · Growth · Operations · Seller &amp; Customer 360 — built on the dbt marts (OLIST.DBT_DEMO), metrics governed by the Lynk semantic layer.</p>
  </header>
  <main>
    <nav>{" ".join(f'<a href="#{slug(n)}">{n}</a>' for n, _ in exported)}</nav>
{cards}
    <footer>Snapshot of the live Tableau dashboards · last updated {updated} · auto-published from the tableau-olist repo</footer>
  </main>
</body></html>
""", encoding="utf-8")

    print(f"Wrote {out}/index.html with {len(exported)} dashboard(s).")


if __name__ == "__main__":
    main()
