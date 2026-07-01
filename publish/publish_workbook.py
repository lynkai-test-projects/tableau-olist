"""Publish the Olist workbook (.twbx) to Tableau Cloud via the REST API, then
export the dashboard to PNG + PDF for a login-free preview.

Uses raw REST (urllib) + PAT auth, so no tableauserverclient dependency. The
corporate proxy MITM-intercepts TLS, so we build an SSL context off the same
combined CA bundle the Snowflake tooling uses.

Env (never commit):  TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET
Run:                  python publish/publish_workbook.py
"""
from __future__ import annotations

import os
import ssl
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib import request, error

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

NS = {"t": "http://tableau.com/api"}
CA = os.environ.get("TABLEAU_CA_BUNDLE", "C:/Users/USUARIO/snowflake-mcp/win_ca_bundle.pem")
CTX = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)


def cfg() -> dict:
    p = Path(__file__).with_name("config.toml")
    with p.open("rb") as fh:
        return tomllib.load(fh)


def api(server: str, ver: str, path: str) -> str:
    return f"{server}/api/{ver}/{path}"


def req(url: str, data=None, method="GET", headers=None, ctype=None) -> bytes:
    h = dict(headers or {})
    if ctype:
        h["Content-Type"] = ctype
    r = request.Request(url, data=data, method=method, headers=h)
    try:
        with request.urlopen(r, timeout=180, context=CTX) as resp:
            return resp.read()
    except error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code} on {method} {url}\n{body[:1000]}")


def signin(c: dict):
    body = (
        f"<tsRequest><credentials personalAccessTokenName=\"{os.environ['TABLEAU_PAT_NAME']}\" "
        f"personalAccessTokenSecret=\"{os.environ['TABLEAU_PAT_SECRET']}\">"
        f"<site contentUrl=\"{c['site_content_url']}\" /></credentials></tsRequest>"
    ).encode()
    out = req(api(c["server_url"], c["api_version"], "auth/signin"), data=body,
              method="POST", ctype="application/xml")
    root = ET.fromstring(out)
    cred = root.find("t:credentials", NS)
    token = cred.get("token")
    site_id = cred.find("t:site", NS).get("id")
    return token, site_id


def find_project(c, token, site_id) -> str:
    out = req(api(c["server_url"], c["api_version"], f"sites/{site_id}/projects?pageSize=1000"),
              headers={"X-Tableau-Auth": token})
    for p in ET.fromstring(out).iter("{http://tableau.com/api}project"):
        if p.get("name") == c["project_name"]:
            return p.get("id")
    sys.exit(f"Project {c['project_name']!r} not found")


def publish(c, token, site_id, project_id):
    wb = (Path(__file__).parent / c["workbook_file"]).resolve()
    payload = (
        f"<tsRequest><workbook name=\"{c['workbook_name']}\">"
        f"<project id=\"{project_id}\" /></workbook></tsRequest>"
    )
    boundary = f"boundary-{uuid.uuid4().hex}"
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: name=\"request_payload\"\r\n"
                 f"Content-Type: text/xml\r\n\r\n{payload}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: name=\"tableau_workbook\"; filename=\"{wb.name}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
        + wb.read_bytes() + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    url = api(c["server_url"], c["api_version"],
              f"sites/{site_id}/workbooks?overwrite=true")
    out = req(url, data=body, method="POST",
              headers={"X-Tableau-Auth": token},
              ctype=f"multipart/mixed; boundary={boundary}")
    root = ET.fromstring(out)
    w = root.find("t:workbook", NS)
    views = [(v.get("id"), v.get("name")) for v in w.iter("{http://tableau.com/api}view")]
    return w.get("id"), w.get("webpageUrl"), views


def export_png(c, token, site_id, view_id, out_path: Path):
    url = api(c["server_url"], c["api_version"],
              f"sites/{site_id}/views/{view_id}/image?resolution=high")
    data = req(url, headers={"X-Tableau-Auth": token})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    print(f"Wrote {out_path} ({len(data)} bytes)")


def main() -> None:
    c = cfg()
    if not os.environ.get("TABLEAU_PAT_NAME") or not os.environ.get("TABLEAU_PAT_SECRET"):
        sys.exit("Set TABLEAU_PAT_NAME and TABLEAU_PAT_SECRET in the environment.")
    token, site_id = signin(c)
    print(f"Signed in. site_id={site_id}")
    project_id = find_project(c, token, site_id)
    print(f"project '{c['project_name']}' id={project_id}")
    wb_id, url, views = publish(c, token, site_id, project_id)
    print(f"Published '{c['workbook_name']}' id={wb_id}\n  {url}")
    print("Views:")
    for vid, vname in views:
        print(f"  {vname}: {vid}")
    # export the dashboard view (name matches the dashboard)
    dash = next((v for v in views if v[1] and "Overview" in v[1]), views[0] if views else None)
    if dash:
        export_png(c, token, site_id, dash[0], Path(__file__).parent.parent / "build" / "olist_overview.png")


if __name__ == "__main__":
    main()
