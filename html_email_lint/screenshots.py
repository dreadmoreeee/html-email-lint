"""Full-page screenshots with Playwright (Chromium), offline by default."""

import os
import re
import struct

WIDTHS = (600, 375)


def _slug(path):
    base = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", base) or "email"


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    return struct.unpack(">II", head[16:24])


def _router(blocked, allow_remote):
    def route(r, *_):
        url = r.request.url
        if allow_remote or url.startswith("data:"):
            r.continue_()
        else:
            if url not in blocked:
                blocked.append(url)
            r.abort()
    return route


def take_screenshots(items, out_dir, allow_remote=False, widths=WIDTHS):
    """Render each item's HTML at each width.

    Returns {item.path: {"files": [...], "blocked": [urls], "overflow": {width: px}}}.
    Every request other than data: URIs is aborted unless allow_remote is True.
    "overflow" is only filled for the narrowest (phone) width.
    """
    from playwright.sync_api import sync_playwright

    os.makedirs(out_dir, exist_ok=True)
    results = {}
    used = set()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for item in items:
                if item.html is None:
                    continue
                slug = _slug(item.path)
                n = 2
                while slug in used:
                    slug = "%s-%d" % (_slug(item.path), n)
                    n += 1
                used.add(slug)
                blocked = []
                files = []
                overflow = {}
                for width in widths:
                    context = browser.new_context(viewport={"width": width, "height": 800},
                                                  java_script_enabled=False)
                    page = context.new_page()
                    page.route("**/*", _router(blocked, allow_remote))
                    page.set_content(item.html, wait_until="load")
                    target = os.path.join(out_dir, "%s-%d.png" % (slug, width))
                    page.screenshot(path=target, full_page=True)
                    files.append(target)
                    shot_width = png_size(target)[0]
                    if width == min(widths) and shot_width > width:
                        overflow[width] = shot_width
                    context.close()
                results[item.path] = {"files": files, "blocked": blocked,
                                     "overflow": overflow}
        finally:
            browser.close()
    return results
