#!/usr/bin/env python3
import os, re, sys, time, urllib.request, urllib.error, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SOURCE = os.environ.get("SOURCE_URL", "https://cupertino-tech.webflow.io").rstrip("/")
TARGET = os.environ.get("TARGET_URL", "https://cupertino.tech").rstrip("/")
OUT = os.environ.get("OUT_DIR", "site")
SKIP = re.compile(r"^/(highlight|milestone|session|year)(/|$)")  # helper collections, not real pages

src_host = urlparse(SOURCE).netloc
tgt_host = urlparse(TARGET).netloc

def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cupertino-tech-mirror/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, e.read()
            err = e
        except Exception as e:  # network hiccup: retry
            err = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"Could not fetch {url}: {err}")

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v: self.hrefs.append(v)

def norm(path):
    path = urlparse(path).path or "/"
    return "/" + path.strip("/") if path != "/" else "/"

BADGE_CSS = "<style>.w-webflow-badge{display:none!important}</style>"

def remove_badge(html):
    # Webflow's script adds the "Made in Webflow" badge when <html> carries data-wf-status.
    html = re.sub(r'\sdata-wf-status="[^"]*"', "", html)
    # Backup in case the badge is added another way: hide it with CSS.
    if BADGE_CSS not in html:
        html = html.replace("</head>", BADGE_CSS + "</head>", 1)
    return html

def rewrite(html):
    html = html.replace(SOURCE, TARGET).replace("http://" + src_host, TARGET)
    html = html.replace("//" + src_host, "//" + tgt_host).replace(src_host, tgt_host)
    return remove_badge(html)

def save(path, body):
    rel = "index.html" if path == "/" else path.strip("/") + "/index.html"
    dest = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(rewrite(body))

def main():
    os.makedirs(OUT, exist_ok=True)
    queue, seen, pages = ["/"], set(), []
    status, sm = fetch(SOURCE + "/sitemap.xml")
    if status == 200:
        try:
            for loc in ET.fromstring(sm).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
                queue.append(norm(loc.text.strip()))
        except ET.ParseError:
            pass
    while queue:
        path = queue.pop(0)
        if path in seen or SKIP.match(path):
            continue
        seen.add(path)
        status, body = fetch(SOURCE + path)
        if status != 200:
            print(f"skip {path} ({status})"); continue
        html = body.decode("utf-8", "replace")
        save(path, html); pages.append(path)
        p = Links(); p.feed(html)
        for href in p.hrefs:
            u = urlparse(urljoin(SOURCE + path, href))
            if u.netloc in ("", src_host) and u.scheme in ("http", "https", ""):
                if not re.search(r"\.[a-z0-9]{2,5}$", u.path, re.I):
                    queue.append(norm(u.path))
        print(f"saved {path}")
    # 404 page: Webflow serves its 404 page for any missing path
    status, body = fetch(SOURCE + "/this-page-does-not-exist-404")
    with open(os.path.join(OUT, "404.html"), "w", encoding="utf-8") as f:
        f.write(rewrite(body.decode("utf-8", "replace")))
    with open(os.path.join(OUT, "CNAME"), "w") as f:
        f.write(tgt_host + "\n")
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    with open(os.path.join(OUT, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {TARGET}/sitemap.xml\n")
    with open(os.path.join(OUT, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in sorted(pages):
            f.write(f"  <url><loc>{TARGET}{'' if p == '/' else p}</loc></url>\n")
        f.write("</urlset>\n")
    print(f"Done: {len(pages)} pages")
    if len(pages) < 10:
        sys.exit("Too few pages copied, something is wrong. Not deploying.")

if __name__ == "__main__":
    main()
