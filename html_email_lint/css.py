"""Tiny CSS helpers: declarations, <style> rules, colors and WCAG contrast."""

import re

_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def parse_declarations(text):
    """'a:b; c:d' -> [(prop, value, important)] with lower-case property names."""
    out = []
    if not text:
        return out
    text = _COMMENT.sub("", text)
    for part in _split_outside_parens(text, ";"):
        if ":" not in part:
            continue
        prop, value = part.split(":", 1)
        prop = prop.strip().lower()
        value = value.strip()
        important = False
        m = re.search(r"!\s*important\s*$", value, re.I)
        if m:
            important = True
            value = value[:m.start()].strip()
        if prop:
            out.append((prop, value, important))
    return out


def style_map(text):
    """Last declaration wins, like the cascade inside a single style attribute."""
    return {p: v for p, v, _ in parse_declarations(text)}


def _split_outside_parens(text, sep):
    parts, depth, cur, quote = [], 0, [], None
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


class Rule:
    """One rule from a <style> block."""

    def __init__(self, selector, declarations, line, context):
        self.selector = selector      # "" for at-rules without selector
        self.declarations = declarations
        self.line = line
        self.context = context        # tuple of enclosing at-rule preludes

    def __repr__(self):
        return "Rule(%r, ctx=%r, line=%d)" % (self.selector, self.context, self.line)


def parse_stylesheet(text, first_line=1):
    """Return (rules, at_rules). at_rules: [(name, prelude, line)]."""
    text = _blank_comments(text)
    rules, at_rules = [], []
    _parse_block(text, 0, len(text), first_line, text, (), rules, at_rules)
    return rules, at_rules


def _blank_comments(text):
    # keep newlines so line numbers survive
    return _COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _line_at(full, pos, first_line):
    return first_line + full.count("\n", 0, pos)


def _parse_block(text, start, end, first_line, full, context, rules, at_rules):
    i = start
    while i < end:
        while i < end and text[i] in " \t\r\n;":
            i += 1
        if i >= end:
            break
        j = i
        while j < end and text[j] not in "{;}":
            j += 1
        prelude = text[i:j].strip()
        line = _line_at(full, i, first_line)
        if j >= end or text[j] in ";}":
            if prelude.startswith("@"):
                name = prelude[1:].split(None, 1)[0].lower() if len(prelude) > 1 else ""
                at_rules.append((name, prelude, line))
            i = j + 1
            continue
        # text[j] == "{": find the matching brace
        depth, k = 1, j + 1
        while k < end and depth:
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
            k += 1
        body_end = k - 1 if depth == 0 else end
        if prelude.startswith("@"):
            name = prelude[1:].split(None, 1)[0].lower() if len(prelude) > 1 else ""
            at_rules.append((name, prelude, line))
            if name in ("media", "supports", "document", "layer", "container"):
                _parse_block(text, j + 1, body_end, first_line, full,
                             context + (prelude,), rules, at_rules)
            else:
                rules.append(Rule("", parse_declarations(text[j + 1:body_end]),
                                  line, context + (prelude,)))
        else:
            rules.append(Rule(prelude, parse_declarations(text[j + 1:body_end]),
                              line, context))
        i = k
    return rules


# ---------------------------------------------------------------- colors

NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "silver": (192, 192, 192),
    "maroon": (128, 0, 0), "purple": (128, 0, 128), "fuchsia": (255, 0, 255),
    "lime": (0, 255, 0), "olive": (128, 128, 0), "navy": (0, 0, 128),
    "teal": (0, 128, 128), "aqua": (0, 255, 255), "orange": (255, 165, 0),
    "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105),
    "whitesmoke": (245, 245, 245), "gainsboro": (220, 220, 220),
}
TRANSPARENT = "transparent"

_HEX = re.compile(r"#([0-9a-fA-F]{3,8})\b")
_RGB = re.compile(r"rgba?\(\s*([^)]*)\)", re.I)


def parse_color(value):
    """Parse one CSS color. Returns (r, g, b), TRANSPARENT or None if unknown."""
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v == "transparent":
        return TRANSPARENT
    if v in NAMED:
        return NAMED[v]
    m = _HEX.fullmatch(v) if v.startswith("#") else None
    if m:
        return _hex(m.group(1))
    m = _RGB.fullmatch(v)
    if m:
        return _rgb(m.group(1))
    if re.fullmatch(r"[0-9a-f]{6}", v):  # bgcolor="ffffff" is common and accepted
        return _hex(v)
    return None


def _hex(h):
    if len(h) in (3, 4):
        if len(h) == 4 and h[3] != "f":
            return TRANSPARENT if h[3] == "0" else None
        return tuple(int(c * 2, 16) for c in h[:3])
    if len(h) in (6, 8):
        if len(h) == 8 and h[6:].lower() != "ff":
            return TRANSPARENT if h[6:] == "00" else None
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return None


def _rgb(args):
    parts = [p for p in re.split(r"[\s,/]+", args.strip()) if p]
    if len(parts) < 3:
        return None
    try:
        rgb = []
        for p in parts[:3]:
            if p.endswith("%"):
                rgb.append(round(float(p[:-1]) * 2.55))
            else:
                rgb.append(round(float(p)))
        if len(parts) > 3:
            a = parts[3]
            alpha = float(a[:-1]) / 100 if a.endswith("%") else float(a)
            if alpha == 0:
                return TRANSPARENT
            if alpha < 1:
                return None  # blending unknown: skip rather than guess
    except ValueError:
        return None
    return tuple(max(0, min(255, c)) for c in rgb)


def color_in_background(value):
    """First color token in a 'background' shorthand."""
    if not value:
        return None
    v = re.sub(r"url\([^)]*\)", " ", value, flags=re.I)
    m = _HEX.search(v)
    if m:
        return _hex(m.group(1))
    m = _RGB.search(v)
    if m:
        return _rgb(m.group(1))
    for tok in re.split(r"\s+", v.strip().lower()):
        if tok == "transparent":
            return TRANSPARENT
        if tok in NAMED:
            return NAMED[tok]
    return None


def to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def relative_luminance(rgb):
    """WCAG 2.x relative luminance of an sRGB color."""
    def chan(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    a, b = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)
