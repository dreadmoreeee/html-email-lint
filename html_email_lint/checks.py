"""All lint checks. Each returns a list of Finding."""

import ipaddress
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urlsplit

from . import css as cssmod
from . import support_table as st
from .dom import Element, Text, parse

SEVERITIES = ("error", "warning", "info")

GMAIL_CLIP_BYTES = 102 * 1024
NEAR_CLIP_BYTES = 90 * 1024


@dataclass
class Finding:
    id: str
    severity: str
    message: str
    line: int | None = None
    clients: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    count: int = 1

    def to_dict(self):
        return asdict(self)


class Context:
    """Parsed document plus cached per-element style data."""

    def __init__(self, item):
        self.item = item
        self.doc = parse(item.html or "")
        self._styles = {}
        self.sheets = []  # (rules, at_rules, style element)
        for text, line, el in self.doc.styles:
            rules, at_rules = cssmod.parse_stylesheet(text, line)
            self.sheets.append((rules, at_rules, el))
        self.has_mso_conditional = any(
            re.search(r"\[if\s[^\]]*mso", c, re.I) for c, _ in self.doc.comments)

    def style(self, el):
        key = id(el)
        if key not in self._styles:
            self._styles[key] = cssmod.style_map(el.get("style", ""))
        return self._styles[key]

    @property
    def body(self):
        return self.doc.find("body") or self.doc.root

    def title(self):
        t = self.doc.find("title")
        return t.text().strip() if t is not None else ""


# ------------------------------------------------------------------ helpers

NON_RENDERED = {"head", "style", "script", "title", "template", "noscript"}


def _zero(value):
    return bool(re.fullmatch(r"\s*0(\.0+)?\s*(px|pt|em|rem|%)?\s*", value or ""))


def hidden_by_self(ctx, el):
    s = ctx.style(el)
    if s.get("display", "").lower().startswith("none"):
        return True
    if s.get("visibility", "").lower() == "hidden":
        return True
    if s.get("mso-hide", "").lower() == "all":
        return True
    if _zero(s.get("opacity")):
        return True
    if _zero(s.get("font-size")) and "font-size" in s:
        return True
    if "max-height" in s and _zero(s["max-height"]) and \
            s.get("overflow", "").lower() == "hidden":
        return True
    if "hidden" in el.attrs:
        return True
    return False


def is_hidden(ctx, el):
    node = el
    while node is not None and node.tag != "#document":
        if node.tag in NON_RENDERED or hidden_by_self(ctx, node):
            return True
        node = node.parent
    return False


def _visible_text(data):
    return data.replace("\xa0", " ").replace("\u200c", "").replace("\u200b", "").strip()


def _text_nodes(el):
    for c in el.children:
        if isinstance(c, Text):
            yield c
        else:
            yield from _text_nodes(c)


def _snippet(text, n=40):
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 3] + "..."


def _first_line(hits):
    lines = [h for h in hits if h]
    return min(lines) if lines else None


# ------------------------------------------------------------------ size

def check_size(ctx):
    n = ctx.item.html_bytes
    clients = ["Gmail: messages whose HTML is larger than about 102 KB are clipped "
               "behind a 'View entire message' link (tracking pixels and footer "
               "links past the cut are lost)"]
    if n > GMAIL_CLIP_BYTES:
        return [Finding("size-gmail-clip", "error",
                        "HTML is %.1f KB, above Gmail's ~102 KB clipping limit" % (n / 1024),
                        clients=clients)]
    if n >= NEAR_CLIP_BYTES:
        return [Finding("size-near-clip", "warning",
                        "HTML is %.1f KB, close to Gmail's ~102 KB clipping limit" % (n / 1024),
                        clients=clients)]
    return []


# ------------------------------------------------------------------ <style> and CSS

HACK_SELECTOR = re.compile(
    r"ExternalClass|ReadMsgBody|x-apple-data-detectors|#outlook|u\s*\+|"
    r"#MessageViewBody|data-ogs[cb]|yshortcuts|^\s*:root|^\s*\*\s*$|"
    r"^\s*(html|body|table|td|img|a|p)(\s*,\s*(html|body|table|td|img|a|p))*\s*$",
    re.I)


def check_style_blocks(ctx):
    out = []
    for rules, at_rules, el in ctx.sheets:
        in_head = any(a.tag == "head" for a in el.ancestors())
        if not in_head:
            out.append(Finding(
                "style-in-body", "warning",
                "<style> block outside <head>; Gmail only keeps <style> in <head>",
                line=el.line, clients=st.STYLE_ELEMENT["clients"][:1],
                sources=st.STYLE_ELEMENT["sources"]))
    base = [r for rules, _, _ in ctx.sheets for r in rules
            if not r.context and r.selector]
    important = [r for r in base if not HACK_SELECTOR.search(r.selector)]
    if important:
        sels = ", ".join(sorted({r.selector for r in important})[:4])
        out.append(Finding(
            "style-only-in-head", "warning",
            "%d CSS rule(s) exist only in <style> (e.g. %s); they are lost where <style> "
            "is stripped. Inline the styles the layout depends on" % (len(important), sels),
            line=_first_line(r.line for r in important), count=len(important),
            clients=st.STYLE_ELEMENT["clients"], sources=st.STYLE_ELEMENT["sources"]))
    media = [r for rules, _, _ in ctx.sheets for r in rules
             if any(c.lower().startswith("@media") for c in r.context)]
    if media:
        out.append(Finding(
            "style-media-queries", "info",
            "%d rule(s) inside @media queries: progressive enhancement only, make sure "
            "the inline styles give a usable layout without them" % len(media),
            line=_first_line(r.line for r in media), count=len(media),
            clients=st.STYLE_ELEMENT["clients"][1:], sources=st.STYLE_ELEMENT["sources"]))
    for rules, at_rules, el in ctx.sheets:
        for name, prelude, line in at_rules:
            if name == "import":
                out.append(Finding(
                    "style-import", "warning",
                    "@import in <style> (%s): external CSS is not loaded by most clients"
                    % _snippet(prelude, 60), line=line,
                    clients=st.LINK_STYLESHEET["clients"],
                    sources=st.LINK_STYLESHEET["sources"]))
    for link in ctx.doc.find_all("link"):
        rel = link.get("rel", "").lower()
        if "stylesheet" in rel:
            out.append(Finding(
                "style-link-stylesheet", "warning",
                "<link rel=stylesheet href=%s>: external stylesheets are not loaded by "
                "most clients; inline the CSS" % _snippet(link.get("href", ""), 60),
                line=link.line, clients=st.LINK_STYLESHEET["clients"],
                sources=st.LINK_STYLESHEET["sources"]))
    return out


FONT_URL = re.compile(r"fonts\.googleapis|fonts\.gstatic|typekit|use\.fontawesome|"
                      r"fonts\.bunny|\.woff2?\b|\.ttf\b|\.otf\b", re.I)
OUTLOOK_ONLY = {"css-float", "css-background-image", "css-max-width",
                "css-border-radius", "css-box-shadow", "css-margin-auto"}


def _declaration_sites(ctx):
    """Yield (prop, value, line, element or None, in_media)."""
    for el in ctx.doc.iter():
        if "style" in el.attrs:
            for prop, value, _ in cssmod.parse_declarations(el.get("style")):
                yield prop, value, el.line, el, False
    for rules, _, _ in ctx.sheets:
        for r in rules:
            in_media = any(c.lower().startswith("@media") for c in r.context)
            for prop, value, _ in r.declarations:
                yield prop, value, r.line, None, in_media


def check_css_support(ctx):
    decl_features = [(f, re.compile(f["property"], re.I), re.compile(f["value"], re.I))
                     for f in st.FEATURES if f["kind"] == "decl"]
    hits = {}
    for prop, value, line, el, in_media in _declaration_sites(ctx):
        for f, prop_re, value_re in decl_features:
            if f["id"] in OUTLOOK_ONLY and in_media:
                continue  # Outlook for Windows ignores @media anyway
            if prop_re.search(prop) and value_re.search(value):
                hits.setdefault(f["id"], []).append((line, el, "%s:%s" % (prop, value)))
    out = []
    for f, _, _ in decl_features:
        h = hits.get(f["id"])
        if not h:
            continue
        severity = f["severity"]
        extra = ""
        if f["id"] == "css-max-width":
            fluid = [x for x in h if x[1] is not None and
                     "%" in ctx.style(x[1]).get("width", "")]
            if fluid and not ctx.has_mso_conditional:
                severity = "warning"
                extra = ("; %d element(s) combine it with a percentage width and there is "
                         "no MSO conditional table to cap the width" % len(fluid))
        examples = ", ".join(sorted({x[2] for x in h})[:3])
        out.append(Finding(
            f["id"], severity,
            "%s used %d time(s) (%s)%s" % (f["title"], len(h), examples, extra),
            line=_first_line(x[0] for x in h), count=len(h),
            clients=f["clients"], sources=f["sources"]))
    # web fonts
    font_feature = next(f for f in st.FEATURES if f["id"] == "css-web-font")
    font_lines = []
    for rules, at_rules, _ in ctx.sheets:
        for name, prelude, line in at_rules:
            if name == "font-face" or (name == "import" and FONT_URL.search(prelude)):
                font_lines.append(line)
    for link in ctx.doc.find_all("link"):
        if FONT_URL.search(link.get("href", "")):
            font_lines.append(link.line)
    if font_lines:
        out.append(Finding(
            "css-web-font", font_feature["severity"],
            "Web font loaded %d time(s); make sure font-family lists safe fallbacks"
            % len(font_lines),
            line=min(font_lines), count=len(font_lines),
            clients=font_feature["clients"], sources=font_feature["sources"]))
    return out


# ------------------------------------------------------------------ images

def _px(value):
    if value is None:
        return None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(px)?\s*", str(value))
    return float(m.group(1)) if m else None


def is_tracking_pixel(ctx, img):
    s = ctx.style(img)
    w = _px(img.get("width"))
    h = _px(img.get("height"))
    if w is None:
        w = _px(s.get("width"))
    if h is None:
        h = _px(s.get("height"))
    if w is not None and h is not None and w <= 1 and h <= 1:
        return True
    return hidden_by_self(ctx, img)


def check_images(ctx):
    out = []
    no_alt, no_dim = [], []
    for img in ctx.doc.find_all("img"):
        if is_tracking_pixel(ctx, img):
            out.append(Finding(
                "tracking-pixel", "info",
                "Probable tracking pixel (1x1, 0x0 or hidden image): %s"
                % _snippet(img.get("src", ""), 70), line=img.line,
                clients=["Apple Mail Privacy Protection preloads images, so opens "
                         "are inflated; many clients block remote images by default"]))
            continue
        if "alt" not in img.attrs:
            no_alt.append(img)
        if "width" not in img.attrs or "height" not in img.attrs:
            no_dim.append(img)
    for img in no_alt:
        out.append(Finding(
            "img-missing-alt", "warning",
            "<img src=%s> has no alt attribute (use alt=\"\" for decorative images)"
            % _snippet(img.get("src", ""), 60), line=img.line,
            clients=["Images are blocked by default in several clients (e.g. Outlook for "
                     "Windows); the alt text is what readers and screen readers get"]))
    for img in no_dim:
        missing = [a for a in ("width", "height") if a not in img.attrs]
        out.append(Finding(
            "img-missing-dimensions", "warning",
            "<img src=%s> is missing the %s attribute(s)"
            % (_snippet(img.get("src", ""), 60), "/".join(missing)), line=img.line,
            clients=["Outlook for Windows (Word engine) uses the width attribute, not CSS, "
                     "and can render images at their native size without it",
                     "Without dimensions the layout jumps when blocked images load"],
            sources=[st.WORD_DOCS]))
    return out


# ------------------------------------------------------------------ URLs

TEMPLATE = re.compile(r"\{\{|\{%|\*\||%%|\[\[|\$\{|<%|\{\$")
OK_SCHEMES = {"mailto", "tel", "sms", "cid", "data", "https"}
URL_ATTRS = {"a": ("href",), "area": ("href",), "img": ("src",), "link": ("href",),
             "source": ("src", "srcset"), "table": ("background",),
             "td": ("background",), "body": ("background",), "v:fill": ("src",),
             "v:image": ("src",)}
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)


def _is_local_host(host):
    if not host:
        return False
    host = host.strip("[]").lower()
    if host in ("localhost",) or host.endswith((".localhost", ".local", ".test",
                                                ".internal", ".lan")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_unspecified or ip.is_link_local


def classify_url(url, tag="a"):
    """Return (finding_id, severity, reason) or None when the URL is fine."""
    u = (url or "").strip()
    if tag in ("a", "area") and u in ("", "#"):
        return ("url-empty", "warning", "empty or '#' link")
    if not u or TEMPLATE.search(u):
        return None
    if u.startswith("#"):
        return None
    if u.startswith("//"):
        return ("url-relative", "error",
                "protocol-relative URL; there is no page protocol in an email")
    parts = urlsplit(u)
    scheme = parts.scheme.lower()
    if not scheme:
        return ("url-relative", "error", "relative URL; email needs absolute URLs")
    if scheme == "javascript":
        return ("url-javascript", "error", "javascript: URL is removed by every client")
    if scheme in ("http", "https") and _is_local_host(parts.hostname):
        return ("url-local-host", "error",
                "points to a local/private host (%s); recipients cannot reach it"
                % parts.hostname)
    if scheme == "http":
        return ("url-http", "warning", "plain http:// link; use https://")
    if scheme in OK_SCHEMES:
        return None
    if scheme == "file":
        return ("url-relative", "error", "file: URL only exists on the author's machine")
    return None


def _urls(ctx):
    for el in ctx.doc.iter():
        for attr in URL_ATTRS.get(el.tag, ()):
            if attr in el.attrs:
                val = el.get(attr)
                if attr == "srcset":
                    for cand in val.split(","):
                        cand = cand.strip().split(" ")[0]
                        if cand:
                            yield cand, el.tag, el.line
                else:
                    yield val, el.tag, el.line
        for m in CSS_URL.finditer(el.get("style", "") or ""):
            yield m.group(1), "css", el.line
    for rules, _, _ in ctx.sheets:
        for r in rules:
            for _, value, _ in r.declarations:
                for m in CSS_URL.finditer(value):
                    yield m.group(1), "css", r.line


def check_urls(ctx):
    seen = {}
    for url, tag, line in _urls(ctx):
        res = classify_url(url, tag)
        if not res:
            continue
        fid, sev, reason = res
        key = (fid, url)
        if key in seen:
            seen[key].count += 1
            continue
        seen[key] = Finding(fid, sev, "%s: <%s> %r" % (reason, tag, url), line=line)
    out = list(seen.values())
    for f in out:
        if f.count > 1:
            f.message += " (%d times)" % f.count
    return out


# ------------------------------------------------------------------ preheader

def check_preheader(ctx):
    body = ctx.body
    texts = [t for t in _text_nodes(body) if _visible_text(t.data)
             and not any(a.tag in ("style", "script", "title", "head")
                         for a in _chain(t.parent))]
    title = ctx.title()
    for t in texts[:5]:
        if is_hidden(ctx, t.parent):
            holder = t.parent
            # the hidden container's whole text is the preheader
            node = holder
            while node.parent is not None and node.parent is not body and \
                    hidden_by_self(ctx, node.parent):
                node = node.parent
            pre = " ".join(_visible_text(node.text()).split())
            if len(pre) < 30 or (title and pre.lower() == title.lower()):
                why = "repeats the <title>" if title and pre.lower() == title.lower() \
                    else "is short"
                return [Finding(
                    "preheader-weak", "info",
                    "Preheader %r %s; the inbox preview shows it next to the subject, "
                    "so a sentence that adds information works better" % (pre, why),
                    line=node.line)]
            return []
    first = _snippet(_visible_text(texts[0].data)) if texts else ""
    return [Finding(
        "preheader-missing", "warning",
        "No hidden preheader near the start of <body>; inbox previews will show the "
        "first visible text%s" % (" (%r)" % first if first else ""),
        line=body.line if body.tag == "body" else None)]


def _chain(el):
    node = el
    while node is not None:
        yield node
        node = node.parent


# ------------------------------------------------------------------ eml parts and headers

def check_eml_parts(ctx):
    item = ctx.item
    if item.kind != "eml":
        return []
    out = []
    if item.text is None or not item.text.strip():
        out.append(Finding(
            "text-part-missing", "warning",
            "No text/plain part: add a multipart/alternative plain-text version",
            clients=["Plain-text readers and some spam filters score HTML-only mail "
                     "lower"]))
    return out


UNSUB_WORDS = re.compile(
    r"unsubscribe|opt[\s-]?out|email preferences|manage preferences|"
    r"darse de baja|cancelar (la )?suscripci|d\u00e9sabonner|desabonner|"
    r"se d\u00e9sinscrire|abmelden", re.I)


def _unsub_links(ctx):
    found = []
    for a in ctx.doc.find_all("a"):
        if UNSUB_WORDS.search(a.text()) or UNSUB_WORDS.search(a.get("href", "")):
            found.append(a)
    return found


def check_unsubscribe(ctx):
    item = ctx.item
    links = _unsub_links(ctx)
    if item.kind == "eml":
        out = []
        lu = item.headers.get("list-unsubscribe")
        lup = item.headers.get("list-unsubscribe-post")
        clients = ["Gmail and Yahoo require one-click unsubscribe (RFC 8058) for bulk "
                   "marketing senders since February 2024"]
        if not lu:
            out.append(Finding(
                "unsubscribe-header-missing", "warning",
                "No List-Unsubscribe header. Required for marketing/bulk mail; "
                "transactional mail (receipts, bookings) may legitimately omit it",
                clients=clients, sources=st.UNSUBSCRIBE_SOURCES))
        else:
            if "https://" not in lu.lower():
                out.append(Finding(
                    "unsubscribe-header-no-https", "warning",
                    "List-Unsubscribe has no https:// URI; one-click unsubscribe "
                    "needs one (mailto: alone is not enough)",
                    clients=clients, sources=st.UNSUBSCRIBE_SOURCES))
            if not lup or "list-unsubscribe=one-click" not in lup.lower().replace(" ", ""):
                out.append(Finding(
                    "unsubscribe-post-missing", "warning",
                    "List-Unsubscribe present but no 'List-Unsubscribe-Post: "
                    "List-Unsubscribe=One-Click' header (RFC 8058)",
                    clients=clients, sources=st.UNSUBSCRIBE_SOURCES))
        if not links and not lu:
            out.append(Finding(
                "unsubscribe-link-missing", "info",
                "No unsubscribe link in the HTML (fine for transactional mail)"))
        return out
    if links:
        return [Finding(
            "unsubscribe-link", "info",
            "Unsubscribe link found; the List-Unsubscribe headers can only be checked "
            "on a .eml file", line=links[0].line)]
    return [Finding(
        "unsubscribe-link-missing", "info",
        "No unsubscribe link found. Marketing mail needs one; transactional mail "
        "(receipts, booking confirmations) may legitimately lack it")]


# ------------------------------------------------------------------ dark mode

def check_dark_mode(ctx):
    metas = {}
    for m in ctx.doc.find_all("meta"):
        name = m.get("name", "").lower()
        if name in ("color-scheme", "supported-color-schemes"):
            metas[name] = m.get("content", "")
    query = any("prefers-color-scheme" in c.lower()
                for rules, _, _ in ctx.sheets for r in rules for c in r.context)
    query = query or any("prefers-color-scheme" in p.lower()
                         for _, at_rules, _ in ctx.sheets for _, p, _ in at_rules)
    if not metas and not query:
        return [Finding(
            "dark-mode-none", "info",
            "No <meta name=\"color-scheme\">, <meta name=\"supported-color-schemes\"> "
            "or prefers-color-scheme styles; clients that force dark mode will "
            "recolor the design on their own",
            clients=st.DARK_MODE["clients"], sources=st.DARK_MODE["sources"])]
    out = []
    if query and "color-scheme" not in metas:
        out.append(Finding(
            "dark-mode-meta-missing", "info",
            "prefers-color-scheme styles without <meta name=\"color-scheme\" "
            "content=\"light dark\">; Apple Mail needs the meta tag to apply them",
            clients=st.DARK_MODE["clients"], sources=st.DARK_MODE["sources"]))
    return out


# ------------------------------------------------------------------ accessibility

def check_lang(ctx):
    html = ctx.doc.find("html")
    if html is None or not html.get("lang", "").strip():
        return [Finding(
            "a11y-lang-missing", "warning",
            "<html> has no lang attribute; screen readers may use the wrong voice",
            line=html.line if html is not None else None)]
    return []


def check_tables(ctx):
    bad = []
    for t in ctx.doc.find_all("table"):
        role = t.get("role", "").lower()
        if role in ("presentation", "none"):
            continue
        if any(e.tag in ("th", "caption") for e in t.iter() if e is not t):
            continue  # looks like a data table
        bad.append(t)
    if not bad:
        return []
    return [Finding(
        "a11y-table-role", "warning",
        "%d layout table(s) without role=\"presentation\"; screen readers announce "
        "rows and columns" % len(bad),
        line=bad[0].line, count=len(bad))]


HEADING_EM = {"h1": 2.0, "h2": 1.5, "h3": 1.17, "h4": 1.0, "h5": 0.83, "h6": 0.67,
              "small": 0.83}
BOLD_TAGS = {"b", "strong", "th", "h1", "h2", "h3", "h4", "h5", "h6"}
LINK_DEFAULT = (0, 0, 238)


def _font_px(ctx, el, memo):
    key = id(el)
    if key in memo:
        return memo[key]
    parent = el.parent if el.parent is not None and el.parent.tag != "#document" else None
    base = _font_px(ctx, parent, memo) if parent is not None else 16.0
    fs = ctx.style(el).get("font-size", "").strip().lower()
    size = base
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(px|pt|em|rem|%)?", fs)
    if m:
        n, unit = float(m.group(1)), m.group(2) or "px"
        size = {"px": n, "pt": n * 4 / 3, "em": n * base, "rem": n * 16.0,
                "%": n * base / 100}[unit]
    elif el.tag in HEADING_EM:
        size = base * HEADING_EM[el.tag]
    memo[key] = size
    return size


def _is_bold(ctx, el):
    for node in _chain(el):
        if node.tag == "#document":
            break
        fw = ctx.style(node).get("font-weight", "").strip().lower()
        if fw:
            if fw in ("bold", "bolder"):
                return True
            if fw.isdigit():
                return int(fw) >= 700
            return False
        if node.tag in BOLD_TAGS:
            return True
    return False


def _fg(ctx, el):
    for node in _chain(el):
        if node.tag == "#document":
            break
        c = cssmod.parse_color(ctx.style(node).get("color"))
        if c is None and node.tag == "font":
            c = cssmod.parse_color(node.get("color"))
        if c is not None and c != cssmod.TRANSPARENT:
            return c, False
        if node.tag == "a" and "href" in node.attrs:
            return LINK_DEFAULT, True
    return (0, 0, 0), False


def _bg(ctx, el):
    for node in _chain(el):
        if node.tag == "#document":
            break
        s = ctx.style(node)
        c = None
        if "background-color" in s:
            c = cssmod.parse_color(s["background-color"])
        if c is None and "background" in s:
            c = cssmod.color_in_background(s["background"])
            if c is None and "url(" in s["background"].lower():
                return None  # text over an image: cannot judge
        if c is None and "background-image" in s and "url(" in s["background-image"]:
            return None
        if c is None and "bgcolor" in node.attrs:
            c = cssmod.parse_color(node.get("bgcolor"))
        if c is not None and c != cssmod.TRANSPARENT:
            return c
    return (255, 255, 255)


def check_contrast(ctx):
    memo, pairs = {}, {}
    for t in _text_nodes(ctx.doc.root):
        text = _visible_text(t.data)
        if not text or t.parent is None or is_hidden(ctx, t.parent):
            continue
        el = t.parent
        fg, default_link = _fg(ctx, el)
        bg = _bg(ctx, el)
        if bg is None:
            continue
        size = _font_px(ctx, el, memo)
        bold = _is_bold(ctx, el)
        large = size >= 24 or (bold and size >= 18.66)
        need = 3.0 if large else 4.5
        ratio = cssmod.contrast_ratio(fg, bg)
        if ratio + 1e-9 >= need:
            continue
        key = (fg, bg, large)
        entry = pairs.setdefault(key, {"ratio": ratio, "line": t.line, "count": 0,
                                       "sample": text, "need": need,
                                       "link": default_link})
        entry["count"] += 1
    out = []
    for (fg, bg, large), e in sorted(pairs.items(), key=lambda kv: kv[1]["ratio"]):
        out.append(Finding(
            "a11y-contrast", "warning",
            "Text %s on %s has contrast %.2f:1, below %.1f:1 for %s text%s; "
            "%d text run(s), e.g. %r" % (
                cssmod.to_hex(fg), cssmod.to_hex(bg), e["ratio"], e["need"],
                "large" if large else "normal",
                " (default link color, no inline color set)" if e["link"] else "",
                e["count"], _snippet(e["sample"])),
            line=e["line"], count=e["count"], sources=st.CONTRAST_SOURCES))
    return out


ALL_CHECKS = [
    check_size, check_style_blocks, check_css_support, check_images, check_urls,
    check_preheader, check_eml_parts, check_unsubscribe, check_dark_mode,
    check_lang, check_tables, check_contrast,
]


def run_checks(item):
    if item.html is None:
        findings = [Finding("html-part-missing", "error",
                            "No text/html part found in the message")]
        findings += check_eml_parts(_Stub(item))
        return findings
    ctx = Context(item)
    findings = []
    for check in ALL_CHECKS:
        findings.extend(check(ctx))
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (order[f.severity], f.line or 0, f.id))
    return findings


class _Stub:
    def __init__(self, item):
        self.item = item
