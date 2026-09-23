#!/usr/bin/env python3
"""Validate the published site before deploy: metadata, local assets, sitemap, robots.

Standard library only, so CI needs no dependencies.
Exits non-zero with a readable list of problems.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
problems = []
notes = []


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def need(cond, message):
    if not cond:
        problems.append(message)


# ---------------------------------------------------------------- index.html
try:
    html = read("index.html")
except FileNotFoundError:
    print("FATAL: index.html is missing")
    sys.exit(1)

required_patterns = {
    "<title>": r"<title>[^<]{10,}</title>",
    "meta description": r'<meta name="description" content="[^"]{40,}"',
    "canonical URL": r'<link rel="canonical" href="https://[^"]+"',
    "robots meta": r'<meta name="robots" content="[^"]*index[^"]*"',
    "og:type": r'<meta property="og:type" content="website"',
    "og:title": r'<meta property="og:title" content="[^"]{10,}"',
    "og:description": r'<meta property="og:description" content="[^"]{40,}"',
    "og:url": r'<meta property="og:url" content="https://[^"]+"',
    "og:image": r'<meta property="og:image" content="https://[^"]+"',
    "og:image:width": r'<meta property="og:image:width" content="1200"',
    "og:image:height": r'<meta property="og:image:height" content="630"',
    "twitter:card": r'<meta name="twitter:card" content="summary_large_image"',
    "twitter:image": r'<meta name="twitter:image" content="https://[^"]+"',
}
for label, pattern in required_patterns.items():
    need(re.search(pattern, html) is not None, "index.html is missing required head tag: %s" % label)

need('name="robots" content="index' in html and "noindex" not in html,
     "index.html must be indexable (no 'noindex')")

# ------------------------------------------------- structured data (JSON-LD)
blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
need(len(blocks) >= 1, "no JSON-LD structured data found")
types = []
for block in blocks:
    try:
        data = json.loads(block)
    except json.JSONDecodeError as exc:
        problems.append("JSON-LD does not parse: %s" % exc)
        continue
    for node in data.get("@graph", [data]):
        if "@type" in node:
            types.append(node["@type"])
need("Person" in types, "JSON-LD should describe a Person (found: %s)" % (types or "nothing"))
need("Organization" in types, "JSON-LD should describe an Organization (found: %s)" % (types or "nothing"))
notes.append("JSON-LD types: %s" % ", ".join(types) if types else "JSON-LD types: none")

# ------------------------------------------------------------ local assets
local_refs = set()
for attr in ("href", "src"):
    for value in re.findall(r'%s="([^"]+)"' % attr, html):
        if value.startswith(("http://", "https://", "#", "mailto:", "data:")):
            continue
        local_refs.add(value.split("#")[0].split("?")[0])
for ref in sorted(local_refs):
    need(ref and os.path.exists(os.path.join(ROOT, ref)), "referenced local file does not exist: %s" % ref)
notes.append("local references checked: %d" % len(local_refs))

# ------------------------------------------------------------- og:image size
og_image = re.search(r'<meta property="og:image" content="https://[^/]+/([^"]+)"', html)
if og_image:
    image_path = os.path.join(ROOT, og_image.group(1))
    if os.path.exists(image_path):
        with open(image_path, "rb") as fh:
            head = fh.read(33)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(head[16:20], "big")
            height = int.from_bytes(head[20:24], "big")
            need((width, height) == (1200, 630),
                 "og:image should be 1200x630 for social previews, found %dx%d" % (width, height))
            notes.append("og:image dimensions: %dx%d" % (width, height))
        else:
            notes.append("og:image is not a PNG; size not verified")
    else:
        problems.append("og:image file is missing: %s" % og_image.group(1))

# ---------------------------------------------------------------- sitemap
try:
    sitemap = read("sitemap.xml")
    root = ET.fromstring(sitemap)
    locs = [e.text or "" for e in root.iter() if e.tag.endswith("loc")]
    need(len(locs) >= 1, "sitemap.xml contains no <loc> entries")
    for loc in locs:
        need(loc.startswith("https://"), "sitemap entry is not an absolute https URL: %s" % loc)
    notes.append("sitemap entries: %d" % len(locs))
except FileNotFoundError:
    problems.append("sitemap.xml is missing")
except ET.ParseError as exc:
    problems.append("sitemap.xml is not valid XML: %s" % exc)

# ----------------------------------------------------------------- robots
try:
    robots = read("robots.txt")
    need(re.search(r"(?im)^\s*allow:\s*/\s*$", robots) is not None,
         "robots.txt should contain an 'Allow: /' rule")
    need(re.search(r"(?im)^\s*sitemap:\s*https://", robots) is not None,
         "robots.txt should point to the sitemap")
    need(re.search(r"(?im)^\s*disallow:\s*/\s*$", robots) is None,
         "robots.txt must not disallow the whole site")
except FileNotFoundError:
    problems.append("robots.txt is missing")

# ------------------------------------------------------------------ report
for line in notes:
    print("note: %s" % line)
if problems:
    print("\nFAILED with %d problem(s):" % len(problems))
    for problem in problems:
        print("  - %s" % problem)
    sys.exit(1)
print("\nSite validation passed.")
