#!/usr/bin/env python3
"""Render the hand-built SVGs on the n4p000-q profile README: hero, neofetch, cards, section bars.

.github/workflows/profile.yml runs this daily and publishes the output
directory to the `output` branch, which README.md links to. Stdlib only:
it uses the GraphQL API when GITHUB_TOKEN is set and falls back to the
public REST API otherwise, so local previews work without a token.

    python3 scripts/render.py dist

Set PROFILE_DATA=some.json to cache the fetched data between local runs.
"""

import datetime as dt
import html
import json
import math
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

USER = "n4p000-q"

# Repo -> tags shown on its card, in README order.
FEATURED = {
    "SOC-Alert-Triage-AI-Assistant": ["xgboost", "tensorflow", "shap", "flask", "react"],
    "log-anomaly-detector": ["drain3", "scikit-learn", "real-time"],
    "leswebz_odoo_local_development-business_Implementation": ["odoo", "docker", "python"],
    "borderflow---konsign-sa": ["node.js", "postgresql", "kubernetes"],
}

NEOFETCH = [
    ("OS", "Ubuntu Linux"),
    ("Host", "Maseru, Lesotho"),
    ("Kernel", "developer, security-hardened"),
    ("Uptime", None),  # time on GitHub, filled in at render time
    ("Shell", "zsh"),
    ("Packages", "python · c · c++ · javascript"),
    ("Frameworks", "flask · react · node.js"),
    ("ML", "tensorflow · scikit-learn · xgboost · shap"),
    ("Infra", "docker · kubernetes · postgresql · git"),
    ("Focus", "security · backend · linux · networks"),
]

FORTUNES = [
    ("Talk is cheap. Show me the code.", "Linus Torvalds"),
    ("Security is a process, not a product.", "Bruce Schneier"),
    ("Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"),
    ("Given enough eyeballs, all bugs are shallow.", "Eric S. Raymond"),
    ("Premature optimization is the root of all evil.", "Donald Knuth"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Programs must be written for people to read, and only incidentally for machines to execute.", "Harold Abelson"),
    ("Any fool can write code that a computer can understand. Good programmers write code that humans can understand.", "Martin Fowler"),
    ("Amateurs hack systems, professionals hack people.", "Bruce Schneier"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("There are two ways to write error-free programs; only the third one works.", "Alan Perlis"),
    ("Code never lies, comments sometimes do.", "Ron Jeffries"),
    ("Everyone knows that debugging is twice as hard as writing a program in the first place.", "Brian Kernighan"),
    ("Walking on water and developing software from a specification are easy if both are frozen.", "Edward V. Berard"),
]

BG, BAR, LINE, TILE = "#0A0E13", "#0F151C", "#1E2A36", "#0D131A"
TEXT, MUTED, WHITE = "#C9D1D9", "#6E7C8C", "#E6EDF3"
CYAN, MAGENTA = "#00E5FF", "#FF2E97"
FONT = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono','DejaVu Sans Mono',monospace"
ADVANCE = 0.6  # monospace glyph advance in em; textLength pins every font to it

# Fallback linguist colours for the REST path (GraphQL returns them).
LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Jupyter Notebook": "#DA5B0B", "HTML": "#e34c26", "CSS": "#663399",
    "Shell": "#89e051", "C": "#555555", "C++": "#f34b7d", "Dockerfile": "#384d54",
    "Makefile": "#427819", "PLpgSQL": "#336790",
}

GLYPHS = {
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    " ": ["..", "..", "..", "..", "..", "..", ".."],
}

# Mokorotlo, the Basotho hat: (first column, last column) lit on each row.
MOKOROTLO = [
    [(9, 11)], [(9, 9), (11, 11)], [(9, 11)], [(10, 10)],
    [(9, 11)], [(9, 11)], [(8, 12)], [(8, 12)], [(7, 13)], [(7, 13)],
    [(6, 14)], [(5, 15)], [(4, 16)], [(3, 17)], [(2, 18)], [(0, 20)], [(1, 19)],
]


# ---------------------------------------------------------------- data

def _call(url, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=30) as resp:
        return json.load(resp)


def _graphql(query):
    out = _call("https://api.github.com/graphql", {"query": query, "variables": {"login": USER}})
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]["user"]


def fetch_graphql():
    user = _graphql("""query($login: String!) { user(login: $login) {
      createdAt followers { totalCount }
      all: repositories(ownerAffiliations: OWNER, privacy: PUBLIC, first: 1) { totalCount }
      repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) { nodes {
        name description stargazerCount primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      } }
      contributionsCollection { contributionCalendar { totalContributions } }
    } }""")
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    spans = []
    for year in range(created.year, now.year + 1):
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        spans.append(f'y{year}: contributionsCollection(from: "{start:%Y-%m-%dT%H:%M:%SZ}", '
                     f'to: "{end:%Y-%m-%dT%H:%M:%SZ}") {{ totalCommitContributions }}')
    years = _graphql("query($login: String!) { user(login: $login) { %s } }" % " ".join(spans))

    languages = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            entry = languages.setdefault(edge["node"]["name"], [0, edge["node"]["color"]])
            entry[0] += edge["size"]
    return {
        "created": user["createdAt"],
        "repos": user["all"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in user["repositories"]["nodes"]),
        "followers": user["followers"]["totalCount"],
        "commits": sum(y["totalCommitContributions"] for y in years.values()),
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "languages": languages,
        "projects": {r["name"]: {
            "description": r["description"] or "",
            "stars": r["stargazerCount"],
            "language": (r["primaryLanguage"] or {}).get("name"),
            "color": (r["primaryLanguage"] or {}).get("color"),
        } for r in user["repositories"]["nodes"]},
    }


def fetch_rest():
    api = "https://api.github.com"
    user = _call(f"{api}/users/{USER}")
    repos = _call(f"{api}/users/{USER}/repos?per_page=100&type=owner")
    sources = [r for r in repos if not r["fork"]]
    languages = {}
    for repo in sources:
        for name, size in _call(repo["languages_url"]).items():
            entry = languages.setdefault(name, [0, LANG_COLORS.get(name, MUTED)])
            entry[0] += size
    contributions = None
    try:
        req = urllib.request.Request(f"https://github.com/users/{USER}/contributions",
                                     headers={"User-Agent": USER})
        page = urllib.request.urlopen(req, timeout=30).read().decode()
        match = re.search(r"([\d,]+)\s+contributions?\s+in the last year", page)
        contributions = int(match.group(1).replace(",", "")) if match else None
    except OSError:
        pass
    return {
        "created": user["created_at"],
        "repos": user["public_repos"],
        "stars": sum(r["stargazers_count"] for r in sources),
        "followers": user["followers"],
        "commits": None,  # needs GraphQL
        "contributions": contributions,
        "languages": languages,
        "projects": {r["name"]: {
            "description": r["description"] or "",
            "stars": r["stargazers_count"],
            "language": r["language"],
            "color": LANG_COLORS.get(r["language"], MUTED),
        } for r in sources},
    }


def fetch():
    cache = os.environ.get("PROFILE_DATA")
    if cache and Path(cache).exists():
        return json.loads(Path(cache).read_text())
    data = None
    if os.environ.get("GITHUB_TOKEN"):
        try:
            data = fetch_graphql()
        except Exception as exc:  # keep the profile rendering on API hiccups
            print(f"GraphQL failed, using REST: {exc}", file=sys.stderr)
    data = data or fetch_rest()
    if cache:
        Path(cache).write_text(json.dumps(data, indent=1))
    return data


def github_age(created, today):
    years, months = today.year - created.year, today.month - created.month
    days = today.day - created.day
    if days < 0:
        months -= 1
        days += (today.replace(day=1) - dt.timedelta(days=1)).day
    if months < 0:
        years -= 1
        months += 12
    unit = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    return f"{unit(years, 'year')}, {unit(months, 'month')}, {unit(days, 'day')}"


# ---------------------------------------------------------------- svg kit

def esc(value):
    return html.escape(str(value), quote=True)


def document(width, height, body, css="", defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" fill="none">'
            f'<style>text{{font-family:{FONT};white-space:pre}}'
            f'@keyframes blink{{50%{{opacity:0}}}}.cur{{animation:blink 1s steps(1) infinite}}'
            f'@keyframes in{{from{{opacity:0;transform:translateX(-8px)}}}}'
            f'.in{{animation:in .35s ease-out both}}'
            f'@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}{css}</style>'
            f'<defs>{defs}</defs>{body}</svg>')


def text(x, y, content, size, fill=TEXT, weight=None, anchor=None, extra=""):
    attrs = f' font-weight="{weight}"' if weight else ""
    attrs += f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}"{attrs}{extra}>{content}</text>'


def spans(segments):
    """[(text, colour) or (text, colour, weight)] -> tspans; returns (markup, char count)."""
    out, count = "", 0
    for seg in segments:
        weight = f' font-weight="{seg[2]}"' if len(seg) > 2 else ""
        out += f'<tspan fill="{seg[1]}"{weight}>{esc(seg[0])}</tspan>'
        count += len(seg[0])
    return out, count


def fixed(x, y, segments, size, extra=""):
    """Text pinned to the monospace grid so later columns line up in any font."""
    markup, count = spans(segments)
    width = count * size * ADVANCE
    return text(x, y, markup, size, extra=f' textLength="{width:.1f}" lengthAdjust="spacing"{extra}'), width


def typed(uid, x, y, segments, size, start, step=0.07):
    """Segments revealed one character at a time from `start` (SMIL, so it runs in <img>)."""
    markup, count = spans(segments)
    cw = size * ADVANCE
    end = start + count * step
    times = ";".join(f"{t / end:.4f}" for t in [0] + [start + k * step for k in range(count + 1)])
    widths = ";".join(f"{v:.1f}" for v in [0] + [k * cw for k in range(count + 1)])
    clip = (f'<clipPath id="{uid}"><rect x="{x:.1f}" y="{y - size:.1f}" width="{count * cw:.1f}" '
            f'height="{size * 1.6:.1f}"><animate attributeName="width" dur="{end:.2f}s" values="{widths}" '
            f'keyTimes="{times}" calcMode="discrete" fill="freeze"/></rect></clipPath>')
    body = text(x, y, markup, size, extra=f' textLength="{count * cw:.1f}" lengthAdjust="spacing" '
                                          f'clip-path="url(#{uid})"')
    xs = ";".join(f"{x + v:.1f}" for v in [0] + [k * cw for k in range(count + 1)])
    caret = (f'<animate attributeName="x" dur="{end:.2f}s" values="{xs}" keyTimes="{times}" '
             f'calcMode="discrete" fill="freeze"/>')
    return clip + body, caret, end


def cursor(x, y, size, caret="", show=None, hide=None, fill=CYAN):
    """Blinking block cursor, visible between `show` and `hide` seconds."""
    sets = ""
    if show is not None:
        sets += f'<set attributeName="visibility" to="visible" begin="{show:.2f}s" fill="freeze"/>'
    if hide is not None:
        sets += f'<set attributeName="visibility" to="hidden" begin="{hide:.2f}s" fill="freeze"/>'
    vis = ' visibility="hidden"' if show is not None else ""
    return (f'<g{vis}>{sets}<rect class="cur" x="{x:.1f}" y="{y - size * 0.82:.1f}" '
            f'width="{size * ADVANCE:.1f}" height="{size * 1.05:.1f}" fill="{fill}" opacity=".9">{caret}</rect></g>')


def delay(seconds):
    return f' style="animation-delay:{seconds:.2f}s"'


def window(width, height, title, uid, radius=12, bar=34):
    """Terminal window chrome. Returns (open markup, close markup)."""
    head = (f'<clipPath id="{uid}"><rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="{radius}"/></clipPath>'
            f'<g clip-path="url(#{uid})"><rect width="{width}" height="{height}" fill="{BG}"/>'
            f'<rect width="{width}" height="{bar}" fill="{BAR}"/>'
            f'<line x1="0" y1="{bar}" x2="{width}" y2="{bar}" stroke="{LINE}"/>')
    for i, colour in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        head += f'<circle cx="{20 + i * 18}" cy="{bar / 2}" r="5.5" fill="{colour}" opacity=".85"/>'
    head += text(width / 2, bar / 2 + 4, esc(title), 12, MUTED, anchor="middle")
    tail = (f'</g><rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="{radius}" '
            f'stroke="{LINE}"/>')
    return head, tail


def scanlines(width, height):
    return (f'<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
            f'<rect width="4" height="1" fill="#000" opacity=".22"/></pattern>',
            f'<rect width="{width}" height="{height}" fill="url(#scan)"/>')


# ---------------------------------------------------------------- hero

def render_hero():
    rng = random.Random(USER)
    width, height = 860, 300
    cell, led = 12, 9.5
    cols, rows = 58, 9
    gx, gy = (width - cols * cell) / 2, 66

    lit, col = [], 1
    for ch in "NAPO QHEKU":
        glyph = GLYPHS[ch]
        lit += [(col + c, r + 1) for r, line in enumerate(glyph) for c, bit in enumerate(line) if bit == "#"]
        col += len(glyph[0]) + 1
    pos = lambda c, r: (gx + c * cell + (cell - led) / 2, gy + r * cell + (cell - led) / 2)

    pixels = ""
    for c, r in lit:
        x, y = pos(c, r)
        pixels += (f'<rect class="p" x="{x:.1f}" y="{y:.1f}" width="{led}" height="{led}" rx="2"'
                   f'{delay(0.25 + c * 0.02 + rng.random() * 0.3)}/>')
    twinkles = ""
    for c, r in rng.sample(lit, 14):
        x, y = pos(c, r)
        twinkles += (f'<rect class="tw" x="{x:.1f}" y="{y:.1f}" width="{led}" height="{led}" rx="2" '
                     f'style="animation-delay:{2.5 + rng.random() * 6:.2f}s;'
                     f'animation-duration:{4 + rng.random() * 5:.2f}s"/>')
    ghost = "".join(f"M{pos(c, r)[0]:.1f},{pos(c, r)[1]:.1f}h{led}v{led}h-{led}z" for c, r in lit)

    rain = ""
    for i in range(39):
        chars = [rng.choice("0123456789ABCDEF") for _ in range(16)]
        tspans = "".join(f'<tspan x="{14 + i * 22}" dy="{0 if k == 0 else 15}">{ch}</tspan>'
                         for k, ch in enumerate(chars))
        rain += (f'<text class="rain" y="0" font-size="13" fill="url(#rainfade)" '
                 f'style="animation-duration:{7 + rng.random() * 9:.2f}s;'
                 f'animation-delay:-{rng.random() * 16:.2f}s">{tspans}</text>')

    segments = [("> ", MAGENTA, 700), ("Building. Breaking. Learning.", WHITE)]
    tag_x = (width - sum(len(s[0]) for s in segments) * 18 * ADVANCE) / 2
    tagline, caret, _ = typed("tag", tag_x, 234, segments, 18, start=1.6, step=0.055)

    scan_def, scan = scanlines(width, height)
    css = (f'.p{{fill:{CYAN};animation:boot .5s ease-out both}}'
           f'@keyframes boot{{0%{{opacity:0;fill:#fff}}45%{{opacity:1;fill:#fff}}}}'
           f'.tw{{fill:#fff;opacity:0;animation:tw 6s ease-in-out infinite}}'
           f'@keyframes tw{{0%,88%,100%{{opacity:0}}94%{{opacity:.9}}}}'
           f'.rain{{animation:fall 10s linear infinite}}'
           f'@keyframes fall{{from{{transform:translateY(-250px)}}to{{transform:translateY({height + 20}px)}}}}'
           f'.jit{{animation:jit 5s 2.4s infinite}}'
           f'@keyframes jit{{0%,86%,93%,100%{{transform:none}}87%{{transform:translateX(3px)}}89%{{transform:translateX(-3px)}}91%{{transform:translateX(1px)}}}}'
           f'.ga,.gb,.gc{{opacity:0;mix-blend-mode:screen;animation:ga 5s 2.4s infinite}}'
           f'.gb{{animation-name:gb}}.gc{{animation-name:gc}}'
           f'@keyframes ga{{0%,86%,93%,100%{{opacity:0;transform:none}}87%{{opacity:.9;transform:translateX(-10px)}}89%{{opacity:.9;transform:translateX(6px)}}91%{{opacity:.7;transform:translateX(-4px)}}}}'
           f'@keyframes gb{{0%,86%,93%,100%{{opacity:0;transform:none}}87.5%{{opacity:.85;transform:translateX(9px)}}90%{{opacity:.85;transform:translateX(-5px)}}}}'
           f'@keyframes gc{{0%,88%,92%,100%{{opacity:0;transform:none}}89%{{opacity:.8;transform:translateX(-14px)}}91%{{opacity:.6;transform:translateX(5px)}}}}'
           f'.beam{{animation:beam 7s linear infinite}}'
           f'@keyframes beam{{from{{transform:translateY(-90px)}}to{{transform:translateY({height + 90}px)}}}}'
           f'.pulse{{animation:pulse 2s ease-in-out infinite}}@keyframes pulse{{50%{{opacity:.25}}}}')
    band = lambda uid, r0, r1: (f'<clipPath id="{uid}"><rect x="0" y="{gy + r0 * cell}" width="{width}" '
                                f'height="{(r1 - r0) * cell}"/></clipPath>')
    defs = (f'<clipPath id="panel"><rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="16"/></clipPath>'
            f'<linearGradient id="rainfade" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".85" stop-color="{CYAN}"/>'
            f'<stop offset="1" stop-color="#fff"/></linearGradient>'
            f'<radialGradient id="halo" cx=".5" cy=".42" r=".55"><stop offset="0" stop-color="{CYAN}" stop-opacity=".16"/>'
            f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="vignette" cx=".5" cy=".5" r=".75"><stop offset=".6" stop-color="#000" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>'
            f'<linearGradient id="beamfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="{CYAN}" stop-opacity=".07"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>'
            f'<pattern id="off" x="{gx}" y="{gy}" width="{cell}" height="{cell}" patternUnits="userSpaceOnUse">'
            f'<rect x="{(cell - led) / 2}" y="{(cell - led) / 2}" width="{led}" height="{led}" rx="2" fill="#0E1922"/></pattern>'
            f'<filter id="glow" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="3.2" result="b"/>'
            f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            + band("bandA", 2, 4) + band("bandB", 5, 6) + band("bandC", 7, 8) + scan_def)

    brackets = "".join(f'<path d="{d}" stroke="{CYAN}" stroke-width="2" opacity=".8"/>' for d in (
        "M16 38V16H38", f"M{width - 38} 16H{width - 16}V38",
        f"M16 {height - 38}V{height - 16}H38", f"M{width - 38} {height - 16}H{width - 16}V{height - 38}"))
    hud = (text(44, 36, "SYS://N4P000-Q", 11, CYAN, 700, extra=' letter-spacing="2" opacity=".85"')
           + text(width - 44, 36, "29.31°S 27.48°E · MASERU, LS", 11, MUTED, anchor="end", extra=' letter-spacing="1.5"')
           + text(44, height - 26, "SECURITY / BACKEND / LINUX / NETWORKS", 11, MUTED, extra=' letter-spacing="2"')
           + text(width - 44, height - 26, "ONLINE", 11, CYAN, 700, anchor="end", extra=' letter-spacing="2"')
           + f'<circle class="pulse" cx="{width - 44 - 6 * (11 * ADVANCE + 2) - 10:.1f}" cy="{height - 30}" r="3.5" fill="{CYAN}"/>'
           + text(width - 44 - 6 * (11 * ADVANCE + 2) - 24, height - 26, "EST. 2022 ·", 11, MUTED, anchor="end",
                  extra=' letter-spacing="2"'))

    body = (f'<g clip-path="url(#panel)"><rect width="{width}" height="{height}" fill="{BG}"/>'
            f'<rect width="{width}" height="{height}" fill="url(#halo)"/>'
            f'<g opacity=".16">{rain}</g>'
            f'<rect x="{gx - 14}" y="{gy - 14}" width="{cols * cell + 28}" height="{rows * cell + 28}" rx="10" '
            f'fill="#06090D" stroke="#15202A"/>'
            f'<rect x="{gx}" y="{gy}" width="{cols * cell}" height="{rows * cell}" fill="url(#off)"/>'
            f'<g class="jit"><g filter="url(#glow)">{pixels}</g>{twinkles}</g>'
            f'<g clip-path="url(#bandA)"><path class="ga" d="{ghost}" fill="{MAGENTA}"/></g>'
            f'<g clip-path="url(#bandB)"><path class="gb" d="{ghost}" fill="#7DF9FF"/></g>'
            f'<g clip-path="url(#bandC)"><path class="gc" d="{ghost}" fill="{MAGENTA}"/></g>'
            f'{tagline}{cursor(tag_x, 234, 18, caret)}{hud}{brackets}'
            f'<rect class="beam" y="-90" width="{width}" height="90" fill="url(#beamfill)"/>'
            f'{scan}<rect width="{width}" height="{height}" fill="url(#vignette)"/></g>'
            f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="16" stroke="{LINE}"/>')
    return document(width, height, body, css, defs)


# ---------------------------------------------------------------- neofetch

def scramble(x, y, value, size, start, rng, frames=9, step=0.06, fill=CYAN):
    """A number that 'decrypts': random digits flash before the real value lands."""
    value = "—" if value is None else f"{value:,}"
    out = ""
    for i in range(frames):
        noise = "".join(rng.choice("0123456789ABCDEF") if ch.isalnum() else ch for ch in value)
        out += text(x, y, esc(noise), size, fill, 700,
                    extra=f' class="fr" style="animation-delay:{start + i * step:.2f}s;animation-duration:{step:.2f}s" opacity=".55"')
    return out + text(x, y, esc(value), size, fill, 700, extra=f' class="in"{delay(start + frames * step)}')


def render_neofetch(data, now):
    rng = random.Random(now.date().isoformat())
    width, pad, size, lh = 860, 28, 14, 22
    cw = size * ADVANCE
    body = ""

    # $ neofetch
    prompt = [("napo", CYAN, 700), ("@", MUTED), ("maseru", CYAN, 700), (":", MUTED), ("~", MAGENTA), ("$ ", WHITE)]
    y = 72
    line, prompt_w = fixed(pad, y, prompt, size)
    cmd, caret, typed_end = typed("cmd1", pad + prompt_w, y, [("neofetch", WHITE)], size, start=0.5)
    body += line + cmd + cursor(pad + prompt_w, y, size, caret, hide=typed_end + 0.25)
    t = typed_end + 0.35

    # logo
    top = 104
    cell = 12
    logo_x, logo_y = pad + 12, top + 26
    shades = ("#B8FBFF", CYAN, "#00A9BD", "#006775")
    logo = ""
    for r, runs in enumerate(MOKOROTLO):
        row = ""
        for first, last in runs:
            for c in range(first, last + 1):
                rel = (c - first) / max(1, last - first)
                level = 1 if rel < 0.62 else 2 if rel < 0.88 else 3
                if r == len(MOKOROTLO) - 1 or (r in (7, 8, 11, 12) and (c + r) % 2):
                    level = min(3, level + 1)  # woven bands and brim underside
                if c == first and r > 3 and r not in (7, 8, 11, 12):
                    level = 0  # light catching the left edge
                row += (f'<rect x="{logo_x + c * cell:.1f}" y="{logo_y + r * cell:.1f}" width="{cell - 1.5}" '
                        f'height="{cell - 1.5}" rx="1.5" fill="{shades[level]}"/>')
        logo += f'<g class="in"{delay(t + r * 0.03)}>{row}</g>'
    body += f'<g filter="url(#glow)">{logo}</g>'
    caption_y = logo_y + len(MOKOROTLO) * cell + 30
    body += text(logo_x + 21 * cell / 2, caption_y, "MOKOROTLO.SYS", 10.5, MUTED, anchor="middle",
                 extra=f' letter-spacing="3" class="in"{delay(t + 0.6)}')

    # info column
    ix, kx = 330, 330 + 12 * cw
    rows = [fixed(ix, 0, [("napo", CYAN, 700), ("@", MUTED), ("maseru", CYAN, 700)], 15)[0],
            text(ix, 0, "─" * 28, size, LINE)]
    uptime = github_age(dt.date.fromisoformat(data["created"][:10]), now.date())
    for key, value in NEOFETCH:
        rows.append(text(ix, 0, esc(key), size, CYAN, 700) + text(kx, 0, esc(value or uptime), size, TEXT))
    palette = ("#1E2A36", MAGENTA, "#3DDC97", "#FEBC2E", "#7AA2F7", CYAN, TEXT, WHITE)
    rows.append("")
    rows.append("".join(f'<rect x="{ix + i * 30}" y="-12" width="26" height="15" rx="3" fill="{c}"/>'
                        for i, c in enumerate(palette)))
    for i, row in enumerate(rows):
        if row:
            body += f'<g class="in"{delay(t + 0.05 * i)}><g transform="translate(0 {top + 14 + i * lh})">{row}</g></g>'
    t += 0.05 * len(rows) + 0.2

    # github band
    y = top + 14 + len(rows) * lh + 24
    label = "github.com/" + USER
    body += (f'<g class="in"{delay(t)}>' + text(pad, y, esc(label), 12, CYAN, 700, extra=' letter-spacing="1"')
             + f'<line x1="{pad + len(label) * 12 * ADVANCE + 14:.1f}" y1="{y - 4}" x2="{width - pad}" y2="{y - 4}" stroke="{LINE}"/></g>')
    tiles = [("REPOS", data["repos"]), ("STARS", data["stars"]), ("FOLLOWERS", data["followers"]),
             ("COMMITS", data["commits"]), ("CONTRIBS / YR", data["contributions"])]
    tile_w = (width - 2 * pad - 4 * 12) / 5
    y += 18
    for i, (name, value) in enumerate(tiles):
        x = pad + i * (tile_w + 12)
        body += (f'<g class="in"{delay(t + 0.08 * i)}><rect x="{x:.1f}" y="{y}" width="{tile_w:.1f}" height="66" rx="8" '
                 f'fill="{TILE}" stroke="{LINE}"/>' + text(x + 16, y + 54, name, 10, MUTED, extra=' letter-spacing="2"') + '</g>')
        body += scramble(x + 16, y + 34, value, 24, t + 0.15 + 0.08 * i, rng)
    t += 0.15 + 0.08 * 5 + 0.6
    y += 66 + 30

    # language bar
    langs = sorted(data["languages"].items(), key=lambda kv: -kv[1][0])
    total = sum(v[0] for _, v in langs) or 1
    top_langs = langs[:6]
    bar_w, x = width - 2 * pad, pad
    segments = ""
    for name, (size_bytes, colour) in top_langs:
        w = bar_w * size_bytes / total
        segments += f'<rect x="{x:.1f}" y="{y}" width="{max(w - 2, 1):.1f}" height="8" fill="{colour or MUTED}"/>'
        x += w
    reveal = (f'<clipPath id="langs"><rect x="{pad}" y="{y}" width="{bar_w}" height="8" rx="4">'
              f'<animate attributeName="width" values="0;0;{bar_w}" keyTimes="0;{t / (t + 0.8):.3f};1" '
              f'dur="{t + 0.8:.2f}s" fill="freeze" calcMode="spline" keySplines="0 0 1 1;.2 .7 .3 1"/></rect></clipPath>')
    body += (reveal + f'<rect x="{pad}" y="{y}" width="{bar_w}" height="8" rx="4" fill="{TILE}"/>'
             f'<g clip-path="url(#langs)">{segments}</g>')
    y += 34
    col_w = bar_w / 3
    for i, (name, (size_bytes, colour)) in enumerate(top_langs):
        lx, ly = pad + (i % 3) * col_w, y + (i // 3) * 22
        body += (f'<g class="in"{delay(t + 0.3 + 0.05 * i)}><circle cx="{lx + 5:.1f}" cy="{ly - 4}" r="5" fill="{colour or MUTED}"/>'
                 + fixed(lx + 18, ly, [(name + " ", TEXT), (f"{100 * size_bytes / total:.1f}%", MUTED)], 12.5)[0] + '</g>')
    t += 0.9
    y += 22 * ((len(top_langs) + 2) // 3) + 26

    # $ fortune
    line, _ = fixed(pad, y, prompt, size, extra=f' class="in"{delay(t)}')
    cmd, caret, typed_end = typed("cmd2", pad + prompt_w, y, [("fortune", WHITE)], size, start=t + 0.4)
    body += line + cmd + cursor(pad + prompt_w, y, size, caret, show=t, hide=typed_end + 0.25)
    t = typed_end + 0.4
    quote, author = FORTUNES[now.date().toordinal() % len(FORTUNES)]
    lines = wrap(quote, 84, 3)
    for i, part in enumerate(lines):
        y += lh
        mark = "“" if i == 0 else " "
        tail = "”" if i == len(lines) - 1 else ""
        body += text(pad, y, esc(mark + part + tail), size, TEXT, extra=f' font-style="italic" class="in"{delay(t + 0.05 * i)}')
    y += lh
    body += text(pad, y, esc("  — " + author), size, MAGENTA, extra=f' class="in"{delay(t + 0.1)}')
    t += 0.5

    # idle prompt
    y += lh + 12
    line, _ = fixed(pad, y, prompt, size, extra=f' class="in"{delay(t)}')
    body += line + cursor(pad + prompt_w, y, size, show=t)

    height = y + 40
    body += text(width - pad, height - 16, f"synced {now:%Y-%m-%d %H:%M} UTC · github actions", 10.5, "#3A4654", anchor="end")
    head, tail = window(width, height, "napo@maseru: ~ — zsh — 120×40", "win")
    scan_def, scan = scanlines(width, height)
    css = (f'.fr{{opacity:0;animation-name:flash;animation-timing-function:linear}}'
           f'@keyframes flash{{from,to{{opacity:.55}}}}')
    defs = (scan_def + '<filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.5" result="b"/>'
            '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    return document(width, height, head + body + f'<g opacity=".5">{scan}</g>' + tail, css, defs)


# ---------------------------------------------------------------- cards

def clip_text(value, limit):
    return value if len(value) <= limit else value[:limit - 1] + "…"


def wrap(value, limit, max_lines):
    lines, current = [], ""
    for word in value.split():
        if current and len(current) + len(word) + 1 > limit:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:limit - 2].rstrip() + " …"
    return lines


def star(cx, cy, r):
    points = []
    for i in range(10):
        radius, angle = (r if i % 2 == 0 else r * 0.45), math.radians(-90 + i * 36)
        points.append(f"{cx + radius * math.cos(angle):.1f},{cy + radius * math.sin(angle):.1f}")
    return f'<polygon points="{" ".join(points)}" fill="{MUTED}"/>'


def render_card(name, tags, repo):
    width, height, pad = 420, 178, 20  # drawn 10px shorter than the canvas to gap the rows
    head, tail = window(width, height, "~/" + clip_text(name, 34), "win", bar=30)
    body = text(pad, 64, esc(clip_text(name, 36)), 16, CYAN, 700)
    for i, line in enumerate(wrap(repo["description"] or "No description yet.", 50, 2)):
        body += text(pad, 90 + i * 18, esc(line), 12.5, TEXT)
    x = pad
    for tag in tags:
        w = len(tag) * 11 * ADVANCE + 16
        if x + w > width - pad:
            break
        body += (f'<rect x="{x:.1f}" y="124" width="{w:.1f}" height="20" rx="10" fill="{MAGENTA}" fill-opacity=".1" '
                 f'stroke="{MAGENTA}" stroke-opacity=".45"/>' + text(x + 8, 138, esc(tag), 11, MAGENTA))
        x += w + 6
    x = pad
    if repo.get("language"):
        label, label_w = fixed(x + 16, 166, [(repo["language"], TEXT)], 12)
        body += f'<circle cx="{x + 5}" cy="162" r="5" fill="{repo.get("color") or MUTED}"/>' + label
        x += 16 + label_w + 18
    body += star(x + 6, 161.5, 6.5) + text(x + 17, 166, str(repo["stars"]), 12, TEXT)
    body += text(width - pad, 166, "open ↗", 12, CYAN, anchor="end")
    return document(width, height + 10, head + body + tail)


# ---------------------------------------------------------------- headers / footer

SECTIONS = ["stack", "featured", "activity"]


def status_bar(width, height, badge, badge_fill, left, right):
    """tmux-style status bar: a powerline badge, `left` segments after it, `right` flush right."""
    mid = height / 2
    badge_w = len(badge) * 13 * ADVANCE + 28
    right_w = len(right) * 11.5 * ADVANCE
    sep = width - 20 - right_w - 14
    return (f'<clipPath id="bar"><rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="8"/></clipPath>'
            f'<g clip-path="url(#bar)"><rect width="{width}" height="{height}" fill="{BAR}"/>'
            f'<path d="M0 0H{badge_w:.1f}L{badge_w + 12:.1f} {mid}L{badge_w:.1f} {height}H0Z" fill="{badge_fill}"/>'
            + fixed(14, mid + 4.5, [(badge, "#06090D", 700)], 13)[0]
            + fixed(badge_w + 30, mid + 4.5, left, 13)[0]
            + f'<path d="M{sep:.1f} 9L{sep - 7:.1f} {mid}L{sep:.1f} {height - 9}" stroke="{LINE}" stroke-width="1.5"/>'
            + fixed(width - 20 - right_w, mid + 4, [(right, MUTED)], 11.5)[0]
            + f'</g><rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="8" stroke="{LINE}"/>')


def render_section(index, hint):
    """Section header drawn as a tmux status line with this section's window active."""
    windows = []
    for i, name in enumerate(SECTIONS, 1):
        active = i == index
        windows.append((f"{i}:{name}{'*' if active else ' '}", WHITE if active else MUTED, 700 if active else 400))
        windows.append(("   ", MUTED))
    badge = f"{index:02d} {SECTIONS[index - 1].upper()}"
    return document(860, 40, status_bar(860, 40, badge, CYAN, windows[:-1], hint))


def render_footer(now):
    width = 860
    prompt = [("napo", CYAN, 700), ("@", MUTED), ("maseru", CYAN, 700), (":", MUTED), ("~", MAGENTA), ("$ ", WHITE), ("exit", WHITE)]
    body = (status_bar(width, 40, "EOF", MAGENTA, prompt, "[process completed]")
            + text(width / 2, 64, f"drawn by scripts/render.py · snake by Platane/snk · rebuilt daily by GitHub Actions · {now:%Y-%m-%d}",
                   11, MUTED, anchor="middle"))
    return document(width, 74, body)


# ---------------------------------------------------------------- main

def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    data = fetch()
    files = {
        "hero.svg": render_hero(),
        "neofetch.svg": render_neofetch(data, now),
        "section-stack.svg": render_section(1, "ls ~/stack"),
        "section-projects.svg": render_section(2, "ls ~/projects --featured"),
        "section-activity.svg": render_section(3, "git log --graph"),
        "footer.svg": render_footer(now),
    }
    for name, tags in FEATURED.items():
        if name in data["projects"]:
            files[f"card-{name}.svg"] = render_card(name, tags, data["projects"][name])
    for name, svg in files.items():
        (out / name).write_text(svg, encoding="utf-8")
    print(f"rendered {len(files)} files into {out}/")


if __name__ == "__main__":
    main()
