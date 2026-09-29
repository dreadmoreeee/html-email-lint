"""Small, hand-written email client support table.

Each entry says which clients drop or mangle a CSS feature, and where that
claim comes from. Support changes over time: follow the source links before
relying on an entry. Only features with well documented, long-standing
problems are listed; absence from this table does not mean "safe".
"""

TABLE_DATE = "2026-09-29"

WORD_DOCS = (
    "https://learn.microsoft.com/en-us/previous-versions/office/developer/"
    "office-2007/aa338201(v=office.12)"
)


def caniemail(feature):
    return "https://www.caniemail.com/features/%s/" % feature


# kind:
#   "decl"    - matched against CSS declarations (property regex + value regex)
#   "at-rule" - matched against @-rules in <style> blocks
FEATURES = [
    {
        "id": "css-flex",
        "title": "display:flex",
        "kind": "decl",
        "property": r"^display$",
        "value": r"\b(inline-)?flex\b",
        "severity": "warning",
        "clients": [
            "Outlook for Windows (Word engine): not supported, children stack as plain blocks",
            "Support in other clients is mixed; check the source page",
        ],
        "sources": [caniemail("css-display-flex"), WORD_DOCS],
    },
    {
        "id": "css-grid",
        "title": "display:grid",
        "kind": "decl",
        "property": r"^display$",
        "value": r"\b(inline-)?grid\b",
        "severity": "warning",
        "clients": [
            "Outlook for Windows (Word engine): not supported",
            "Gmail: not supported",
        ],
        "sources": [caniemail("css-display-grid"), WORD_DOCS],
    },
    {
        "id": "css-position",
        "title": "position",
        "kind": "decl",
        "property": r"^position$",
        "value": r"\b(absolute|relative|fixed|sticky)\b",
        "severity": "warning",
        "clients": [
            "Gmail: position is stripped",
            "Outlook for Windows (Word engine): not supported",
        ],
        "sources": [caniemail("css-position"), WORD_DOCS],
    },
    {
        "id": "css-float",
        "title": "float",
        "kind": "decl",
        "property": r"^float$",
        "value": r"\b(left|right)\b",
        "severity": "warning",
        "clients": [
            "Outlook for Windows (Word engine): unreliable, mostly ignored outside images",
        ],
        "sources": [caniemail("css-float"), WORD_DOCS],
    },
    {
        "id": "css-background-image",
        "title": "background-image",
        "kind": "decl",
        "property": r"^background(-image)?$",
        "value": r"url\s*\(",
        "severity": "warning",
        "clients": [
            "Outlook for Windows (Word engine): CSS background images are not shown; "
            "use a solid bgcolor fallback (or VML)",
        ],
        "sources": [caniemail("css-background-image"), WORD_DOCS],
    },
    {
        "id": "css-negative-margin",
        "title": "negative margin",
        "kind": "decl",
        "property": r"^margin(-(top|right|bottom|left))?$",
        "value": r"(^|\s)-\d",
        "severity": "warning",
        "clients": [
            "Outlook.com: negative margin values are removed",
            "Outlook for Windows (Word engine): negative margins not supported",
        ],
        "sources": [caniemail("css-margin"), WORD_DOCS],
    },
    {
        "id": "css-margin-auto",
        "title": "margin:auto centering",
        "kind": "decl",
        "property": r"^margin(-(left|right))?$",
        "value": r"\bauto\b",
        "severity": "info",
        "clients": [
            "Outlook for Windows (Word engine): auto margins do not center block elements; "
            "use align=\"center\" on the table or cell",
        ],
        "sources": [caniemail("css-margin"), WORD_DOCS],
    },
    {
        "id": "css-max-width",
        "title": "max-width",
        "kind": "decl",
        "property": r"^max-width$",
        "value": r".",
        "severity": "info",
        "clients": [
            "Outlook for Windows (Word engine): max-width is ignored; with a fluid width "
            "the element can stretch to the full window unless a fixed width attribute "
            "or an MSO conditional (ghost) table caps it",
        ],
        "sources": [caniemail("css-max-width"), WORD_DOCS],
    },
    {
        "id": "css-border-radius",
        "title": "border-radius",
        "kind": "decl",
        "property": r"^border(-(top|bottom)-(left|right))?-radius$",
        "value": r".",
        "severity": "info",
        "clients": [
            "Outlook for Windows (Word engine): not supported, corners render square "
            "(harmless if the design tolerates it)",
        ],
        "sources": [caniemail("css-border-radius"), WORD_DOCS],
    },
    {
        "id": "css-box-shadow",
        "title": "box-shadow",
        "kind": "decl",
        "property": r"^box-shadow$",
        "value": r".",
        "severity": "info",
        "clients": [
            "Outlook for Windows (Word engine): not supported",
        ],
        "sources": [caniemail("css-box-shadow"), WORD_DOCS],
    },
    {
        "id": "css-web-font",
        "title": "web fonts (@font-face / font stylesheet)",
        "kind": "at-rule",
        "at_rule": "font-face",
        "severity": "info",
        "clients": [
            "Only Apple Mail, iOS Mail, Outlook for Mac, Samsung Email and Thunderbird "
            "load web fonts",
            "Gmail, Outlook.com, Yahoo and Outlook for Windows use the fallback stack; "
            "Outlook for Windows may fall back to Times New Roman",
        ],
        "sources": [caniemail("css-at-font-face"), WORD_DOCS],
    },
]

STYLE_ELEMENT = {
    "clients": [
        "Gmail: <style> supported in <head> only; a block containing CSS Gmail cannot "
        "parse is dropped whole",
        "Gmail apps with non-Google (IMAP/POP) accounts: <style> is stripped",
        "Outlook for Windows (Word engine): reads <style> but ignores @media queries",
    ],
    "sources": [caniemail("html-style"), caniemail("css-at-media"), WORD_DOCS],
}

LINK_STYLESHEET = {
    "clients": [
        "Gmail, Outlook.com, Yahoo and Outlook for Windows do not load external "
        "stylesheets; only a few clients (Apple Mail, iOS Mail) do",
    ],
    "sources": [caniemail("css-at-import")],
}

DARK_MODE = {
    "clients": [
        "Apple Mail, iOS Mail and Outlook for Mac honor prefers-color-scheme "
        "and the color-scheme meta tags",
        "Gmail does not support prefers-color-scheme; Gmail apps and Outlook apps may "
        "invert colors on their own",
    ],
    "sources": [caniemail("css-at-media-prefers-color-scheme")],
}

CONTRAST_SOURCES = [
    "https://www.w3.org/TR/WCAG21/#contrast-minimum",
    "https://www.w3.org/TR/WCAG21/#dfn-relative-luminance",
]

UNSUBSCRIBE_SOURCES = [
    "https://www.rfc-editor.org/rfc/rfc8058",
    "https://support.google.com/a/answer/81126",
]
