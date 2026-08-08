#!/usr/bin/env python3
"""
Regenerate the guides list in index.html from repositories in the organisation
that are tagged with the topic `mixomics-guide` AND have GitHub Pages enabled.

Only the region between GUIDES:START and GUIDES:END is rewritten; the rest of
the page is hand-authored and left alone.

Run locally:  GH_TOKEN=$(gh auth token) python3 scripts/build-index.py
"""
import base64
import datetime
import html
import json
import os
import re
import sys
import urllib.request

ORG   = os.environ.get("ORG", "mixOmics-org")
TOPIC = os.environ.get("TOPIC", "mixomics-guide")

# A second topic sets the card's accent colour and label. Absent one, the card
# renders untyped in neutral grey rather than guessing.
TYPES = {
    "guide-vignette":  "Vignette",
    "guide-tutorial":  "Tutorial",
    "guide-reference": "Reference",
}
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
PAGE  = "index.html"


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mixomics-guides-indexer",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def guides():
    out, page = [], 1
    while True:
        batch = api(f"/orgs/{ORG}/repos?per_page=100&page={page}&type=public")
        if not batch:
            break
        for repo in batch:
            if repo.get("archived") or repo.get("fork"):
                continue
            # `topics` is normally inlined in the repos response. If it is ever
            # absent, fall back to the dedicated endpoint rather than silently
            # filtering everything out.
            topics = repo.get("topics")
            if topics is None:
                topics = api(f"/repos/{ORG}/{repo['name']}/topics").get("names", [])
            if TOPIC not in topics:
                continue
            if not repo.get("has_pages"):
                print(f"  skip {repo['name']}: topic present but Pages not enabled",
                      file=sys.stderr)
                continue
            kind = next((TYPES[t] for t in topics if t in TYPES), None)
            out.append({
                "name": repo["name"],
                # `homepage` lets a repo override the displayed title;
                # otherwise fall back to the repo name.
                "title": (repo.get("homepage") or "").strip() or repo["name"],
                "note": (repo.get("description") or "").strip(),
                "kind": kind,
                "pushed": repo.get("pushed_at", ""),
            })
        page += 1
    # most recently updated first, so new work surfaces without manual ordering
    return sorted(out, key=lambda g: g["pushed"], reverse=True)


def render(items):
    if not items:
        return ('      <ul class="guides">\n'
                '        <li class="guides__item"><p class="guide__note">'
                'No guides published yet.</p></li>\n'
                '      </ul>\n')
    rows = ['      <ul class="guides">']
    for g in items:
        mod = f' guide--{g["kind"].lower()}' if g["kind"] else ""
        label = (f'\n            <span class="guide__type">{html.escape(g["kind"])}</span>'
                 if g["kind"] else "")
        note = (f'\n            <span class="guide__note">{html.escape(g["note"])}</span>'
                if g["note"] else "")
        rows.append(
            f'        <li class="guides__item">\n'
            f'          <a class="guide{mod}" href="/{g["name"]}/">'
            f'{label}\n'
            f'            <span class="guide__title">{html.escape(g["title"])}</span>'
            f'{note}\n'
            f'          </a>\n'
            f'        </li>'
        )
    rows.append('      </ul>')
    return "\n".join(rows) + "\n"


def stamp_assets(page, day):
    """Append ?v=YYYYMMDD to local CSS/JS refs.

    GitHub Pages sends Cache-Control: max-age=600 with ETags, so a stale
    stylesheet self-corrects within ten minutes. This closes that window,
    which matters when a deploy changes layout rather than just content.
    """
    page = re.sub(r'(href="style\.css)(\?v=\d+)?"', rf'\1?v={day}"', page)
    page = re.sub(r'(src="script\.js)(\?v=\d+)?"',  rf'\1?v={day}"', page)
    return page


def write_sitemap(items):
    today = datetime.date.today().isoformat()
    urls = ['  <url>\n'
            '    <loc>https://guides.mixomics.org/</loc>\n'
            f'    <lastmod>{today}</lastmod>\n'
            '    <changefreq>monthly</changefreq>\n'
            '    <priority>1.0</priority>\n'
            '  </url>']
    for g in items:
        urls.append('  <url>\n'
                    f'    <loc>https://guides.mixomics.org/{g["name"]}/</loc>\n'
                    f'    <lastmod>{g["pushed"][:10] or today}</lastmod>\n'
                    '    <changefreq>monthly</changefreq>\n'
                    '    <priority>0.8</priority>\n'
                    '  </url>')
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!-- Generated by .github/workflows/build-index.yml. Do not edit. -->\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + '\n</urlset>\n')
    open("sitemap.xml", "w", encoding="utf-8").write(body)
    print(f"sitemap.xml: {len(urls)} url(s)", file=sys.stderr)


def load_site():
    """Site-specific settings only. Licence and authorship are NOT stored
    here — they are read from the package repository at build time."""
    with open("site.json", encoding="utf-8") as fh:
        return json.load(fh)


def fetch_text(repo, path):
    """Fetch a file's contents from a repository, or None."""
    try:
        blob = api(f"/repos/{repo}/contents/{path}")
        return base64.b64decode(blob["content"]).decode("utf-8")
    except Exception as exc:                       # noqa: BLE001
        print(f"  could not read {repo}/{path}: {exc}", file=sys.stderr)
        return None


# DESCRIPTION License field -> SPDX. R uses its own vocabulary, so a map is
# unavoidable; unknown values pass through unchanged rather than guessing.
SPDX = {
    "GPL (>= 2)":  "GPL-2.0-or-later",
    "GPL (>= 3)":  "GPL-3.0-or-later",
    "GPL-2":       "GPL-2.0-only",
    "GPL-3":       "GPL-3.0-only",
    "AGPL-3":      "AGPL-3.0-only",
    "AGPL (>= 3)": "AGPL-3.0-or-later",
    "MIT + file LICENSE": "MIT",
    "Artistic-2.0": "Artistic-2.0",
}


def read_package_licence(cfg):
    """Read the licence from the package's DESCRIPTION — the file Bioconductor
    and CRAN treat as authoritative. The site then cannot disagree with the
    package, and a relicence needs no change here at all.

    Falls back to site.json only if the fetch fails, so a network blip does not
    silently publish the wrong licence."""
    repo = cfg["source"]["package_repo"]
    text = fetch_text(repo, "DESCRIPTION")
    if not text:
        print("  falling back to site.json licence", file=sys.stderr)
        return cfg["fallback"]["licence"]

    label = None
    for line in text.splitlines():
        if line.startswith("License:"):
            label = line.split(":", 1)[1].strip()
            break
    if not label:
        print("  no License: field in DESCRIPTION; using fallback", file=sys.stderr)
        return cfg["fallback"]["licence"]

    lic = {
        "label": label,
        "spdx": SPDX.get(label, label),
        "url": f"https://github.com/{repo}/blob/master/LICENSE",
    }
    print(f"  licence from {repo}/DESCRIPTION: {label} ({lic['spdx']})", file=sys.stderr)
    return lic


def read_package_people(cfg):
    """Read contributors from the package's CITATION.cff — the file that already
    governs how the work is cited, so credit here cannot drift from credit in
    the literature.

    CITATION.cff has no role vocabulary, so roles come from site.json where
    they are set, keyed by name."""
    repo = cfg["source"]["package_repo"]
    text = fetch_text(repo, "CITATION.cff")
    roles = {r["name"]: r for r in cfg.get("roles", [])}

    people = []
    if text:
        try:
            import yaml
            doc = yaml.safe_load(text) or {}
            for a in doc.get("authors", []):
                given = (a.get("given-names") or "").strip()
                family = (a.get("family-names") or "").strip()
                name = (a.get("name") or f"{given} {family}").strip()
                if not name:
                    continue
                extra = roles.get(name, {})
                people.append({
                    "name": name,
                    "role": extra.get("role", "Contributor"),
                    "since": extra.get("since"),
                    "until": extra.get("until"),
                    "orcid": (a.get("orcid") or "").replace("https://orcid.org/", "") or extra.get("orcid"),
                    "current": extra.get("current", True),
                })
            print(f"  {len(people)} author(s) from {repo}/CITATION.cff", file=sys.stderr)
        except ImportError:
            print("  pyyaml not installed; using fallback people", file=sys.stderr)
        except Exception as exc:                   # noqa: BLE001
            print(f"  could not parse CITATION.cff: {exc}", file=sys.stderr)

    # anyone named in site.json roles but absent from CITATION.cff — people who
    # maintain the site or infrastructure without authoring the package
    named = {p["name"] for p in people}
    for r in cfg.get("roles", []):
        if r["name"] not in named and r.get("include_if_absent", False):
            people.append({**r, "current": r.get("current", True)})

    return people or cfg["fallback"]["people"]


def write_humans(cfg):
    """Regenerate humans.txt. Never hand-edit it; edit site.json."""
    lic = cfg["licence"]
    current  = [p for p in cfg["people"] if p.get("current", True)]
    emeritus = [p for p in cfg["people"] if not p.get("current", True)]

    out = ["/* TEAM */"]
    for p in current:
        out.append(f'  {p["role"]}: {p["name"]}')
        if p.get("orcid"):
            out.append(f'  ORCID: {p["orcid"]}')
        if p.get("since"):
            out.append(f'  Since: {p["since"]}')
        out.append("")
    if emeritus:
        out.append("/* PREVIOUSLY */")
        for p in emeritus:
            yrs = f' ({p["since"]}–{p.get("until","")})' if p.get("since") else ""
            out.append(f'  {p["role"]}: {p["name"]}{yrs}')
        out.append("")
    out += [
        "/* SITE */",
        f'  Site: {cfg["site"]["url"]}',
        "  Standards: HTML5, CSS (container queries, custom properties), ES2020",
        "  Components: Montserrat (SIL OFL 1.1), self-hosted",
        "  Software: GitHub Pages",
        f'  Site content: {lic["site_content"]["label"]}',
        f'  mixOmics package: {lic["package"]["label"]}',
        "",
        "/* THANKS */",
    ]
    for line in cfg["acknowledgement"].split(". "):
        line = line.strip().rstrip(".")
        if line:
            out.append(f"  {line}.")
    out.append("")
    out.append("/* GENERATED — edit site.json, not this file. */")
    open("humans.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"humans.txt: {len(current)} current, {len(emeritus)} emeritus", file=sys.stderr)


def sync_licence(page, cfg):
    """Propagate the package licence label and URL into the colophon and the
    JSON-LD, so a relicence is a one-line change in site.json."""
    lic = cfg["licence"]["package"]
    page = re.sub(
        r'(<a class="site-footer__link" href=")[^"]*("[^>]*>)[^<]*(</a>,\s*\n\s*and developed since)',
        rf'\1{lic["url"]}\2{lic["label"]}\3', page)
    page = re.sub(r'("license":\s*")[^"]*(")', rf'\1{lic["url"]}\2', page)
    return page


def main():
    cfg = load_site()
    print("Reading licence and authorship from the package repository:", file=sys.stderr)
    cfg["licence"] = {
        "package": read_package_licence(cfg),
        "site_content": cfg["fallback"]["licence_site_content"],
    }
    cfg["people"] = read_package_people(cfg)
    cfg["acknowledgement"] = cfg["fallback"]["acknowledgement"]

    items = guides()
    print(f"found {len(items)} guide(s): {', '.join(g['name'] for g in items) or '—'}",
          file=sys.stderr)

    page = open(PAGE, encoding="utf-8").read()
    pattern = re.compile(
        r"(<!-- GUIDES:START.*?-->\n)(.*?)(      <!-- GUIDES:END -->)", re.S)
    if not pattern.search(page):
        sys.exit("ERROR: GUIDES:START / GUIDES:END markers not found in index.html")

    updated = pattern.sub(lambda m: m.group(1) + render(items) + m.group(3), page)

    updated = sync_licence(updated, cfg)
    updated = stamp_assets(updated, datetime.date.today().strftime("%Y%m%d"))
    write_sitemap(items)
    write_humans(cfg)

    if updated == page:
        print("no change to index.html", file=sys.stderr)
        return
    open(PAGE, "w", encoding="utf-8").write(updated)
    print("index.html updated", file=sys.stderr)


if __name__ == "__main__":
    main()
