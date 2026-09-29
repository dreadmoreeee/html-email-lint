from html_email_lint import lint_html
from html_email_lint.checks import GMAIL_CLIP_BYTES, classify_url

BASE = """<!doctype html><html lang="en"><head><title>T</title>
<meta name="color-scheme" content="light dark">%s</head>
<body><div style="display:none;max-height:0;overflow:hidden;">A long enough preview sentence for the inbox list.</div>
<table role="presentation" width="600"><tr><td>%s</td></tr></table>
<a href="https://example.com/unsubscribe">Unsubscribe</a></body></html>"""


def page(body="", head=""):
    return BASE % (head, body)


def ids(findings):
    return [f.id for f in findings]


def by_id(findings, fid):
    return [f for f in findings if f.id == fid]


def test_clean_page_has_only_info():
    f = lint_html(page("<p>Hello</p>"))
    assert all(x.severity == "info" for x in f), [(x.id, x.message) for x in f]


def test_size_near_and_over_gmail_clip():
    filler = "<!--" + "x" * (GMAIL_CLIP_BYTES + 10) + "-->"
    assert "size-gmail-clip" in ids(lint_html(page(filler)))
    near = "<!--" + "x" * (92 * 1024) + "-->"
    f = lint_html(page(near))
    assert "size-near-clip" in ids(f) and "size-gmail-clip" not in ids(f)
    assert by_id(lint_html(page(filler)), "size-gmail-clip")[0].severity == "error"


def test_style_only_rules_and_media_queries():
    head = "<style>.btn{color:red}\n@media (max-width:600px){.x{width:100%}}</style>"
    f = lint_html(page("", head))
    only = by_id(f, "style-only-in-head")
    assert only and only[0].severity == "warning" and ".btn" in only[0].message
    assert by_id(f, "style-media-queries")[0].severity == "info"


def test_client_hack_selectors_are_not_flagged():
    head = "<style>#outlook a{padding:0} .ExternalClass{width:100%} body{margin:0}</style>"
    assert "style-only-in-head" not in ids(lint_html(page("", head)))


def test_style_in_body_and_link_stylesheet():
    f = lint_html(page("<style>.a{color:red}</style>",
                       '<link rel="stylesheet" href="https://example.com/a.css">'))
    assert "style-in-body" in ids(f)
    assert "style-link-stylesheet" in ids(f)


def test_css_support_table_hits():
    body = ('<div style="display:flex;position:absolute;float:left;margin:-4px;'
            'background-image:url(https://example.com/a.png);box-shadow:0 0 1px #000">x</div>'
            '<div style="display:grid;border-radius:4px;margin:0 auto">y</div>')
    f = ids(lint_html(page(body)))
    for fid in ("css-flex", "css-grid", "css-position", "css-float", "css-negative-margin",
                "css-background-image", "css-box-shadow", "css-border-radius",
                "css-margin-auto"):
        assert fid in f, fid


def test_css_findings_carry_sources():
    f = by_id(lint_html(page('<div style="display:flex">x</div>')), "css-flex")[0]
    assert any("caniemail.com" in s for s in f.sources)
    assert any("learn.microsoft.com" in s for s in f.sources)
    assert f.clients


def test_max_width_with_fluid_width_warns_unless_ghost_table():
    body = '<table role="presentation" style="width:100%;max-width:600px"><tr><td>x</td></tr></table>'
    f = by_id(lint_html(page(body)), "css-max-width")[0]
    assert f.severity == "warning"
    ghost = "<!--[if mso]><table width=600><tr><td><![endif]-->" + body
    assert by_id(lint_html(page(ghost)), "css-max-width")[0].severity == "info"
    fixed = '<table role="presentation" style="max-width:600px"><tr><td>x</td></tr></table>'
    assert by_id(lint_html(page(fixed)), "css-max-width")[0].severity == "info"


def test_outlook_only_features_inside_media_query_are_ignored():
    head = "<style>@media (max-width:600px){.a{max-width:100% !important}}</style>"
    assert "css-max-width" not in ids(lint_html(page("", head)))


def test_web_fonts():
    head = ("<style>@font-face{font-family:X;src:url(https://example.com/x.woff2)}</style>"
            '<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">')
    f = by_id(lint_html(page("", head)), "css-web-font")
    assert f and f[0].count == 2


def test_images_alt_and_dimensions():
    body = ('<img src="https://example.com/a.png">'
            '<img src="https://example.com/b.png" alt="" width="10" height="10">')
    f = lint_html(page(body))
    assert len(by_id(f, "img-missing-alt")) == 1
    assert len(by_id(f, "img-missing-dimensions")) == 1


def test_tracking_pixels():
    body = ('<img src="https://t.example.com/o.gif" width="1" height="1" alt="">'
            '<img src="https://t.example.com/p.gif" style="width:0;height:0" alt="">'
            '<img src="https://t.example.com/q.gif" style="display:none" alt="" width="5" height="5">')
    f = lint_html(page(body))
    assert len(by_id(f, "tracking-pixel")) == 3
    assert all(x.severity == "info" for x in by_id(f, "tracking-pixel"))
    assert "img-missing-dimensions" not in ids(f)


def test_url_classification():
    assert classify_url("https://example.com") is None
    assert classify_url("mailto:a@example.com") is None
    assert classify_url("tel:+15065550100") is None
    assert classify_url("{{unsubscribe_url}}") is None
    assert classify_url("*|UNSUB|*") is None
    assert classify_url("/path")[0] == "url-relative"
    assert classify_url("img/a.png", "img")[0] == "url-relative"
    assert classify_url("//cdn.example.com/a.png", "img")[0] == "url-relative"
    assert classify_url("http://example.com")[0] == "url-http"
    assert classify_url("http://127.0.0.1:8000/x")[0] == "url-local-host"
    assert classify_url("https://localhost/x")[0] == "url-local-host"
    assert classify_url("http://192.168.1.10/x")[0] == "url-local-host"
    assert classify_url("#")[0] == "url-empty"
    assert classify_url("")[0] == "url-empty"
    assert classify_url("javascript:void(0)")[0] == "url-javascript"


def test_urls_in_document_are_deduplicated():
    body = '<a href="http://example.com/a">a</a><a href="http://example.com/a">b</a><a href="#">c</a>'
    f = lint_html(page(body))
    http = by_id(f, "url-http")
    assert len(http) == 1 and http[0].count == 2
    assert by_id(f, "url-empty")[0].severity == "warning"


def test_preheader_missing_and_weak():
    html = ('<html lang="en"><head><title>Riverside Pub</title></head><body>'
            '<p>Visible first</p></body></html>')
    f = by_id(lint_html(html), "preheader-missing")
    assert f and "Visible first" in f[0].message
    weak = ('<html lang="en"><head><title>Riverside Pub</title></head><body>'
            '<div style="display:none">Riverside Pub</div><p>x</p></body></html>')
    assert "preheader-weak" in ids(lint_html(weak))


def test_unsubscribe_link_html_is_info():
    f = lint_html(page("<p>x</p>"))
    assert by_id(f, "unsubscribe-link")[0].severity == "info"
    no = lint_html("<html lang='en'><body><p>Receipt</p></body></html>")
    miss = by_id(no, "unsubscribe-link-missing")[0]
    assert miss.severity == "info" and "transactional" in miss.message


def test_dark_mode_hints():
    no = lint_html("<html lang='en'><body><p>x</p></body></html>")
    assert "dark-mode-none" in ids(no)
    q = lint_html("<html lang='en'><head><style>@media (prefers-color-scheme: dark)"
                  "{.a{color:#fff}}</style></head><body><p>x</p></body></html>")
    assert "dark-mode-meta-missing" in ids(q) and "dark-mode-none" not in ids(q)
    assert "dark-mode-none" not in ids(lint_html(page("<p>x</p>")))


def test_lang_and_table_role():
    f = lint_html("<html><body><table><tr><td>x</td></tr></table>"
                  "<table><tr><th>h</th></tr></table></body></html>")
    assert "a11y-lang-missing" in ids(f)
    role = by_id(f, "a11y-table-role")
    assert role and role[0].count == 1  # the table with <th> is a data table


def test_contrast_resolves_ancestors():
    body = ('<table role="presentation" bgcolor="#ffffff"><tr><td style="color:#777777">'
            '<span>Grey text</span></td></tr></table>')
    f = by_id(lint_html(page(body)), "a11y-contrast")
    assert f and "4.48:1" in f[0].message and "#777777 on #ffffff" in f[0].message


def test_contrast_large_text_threshold():
    body = '<p style="color:#949494;font-size:24px">Big</p>'  # ~3.03:1
    assert not by_id(lint_html(page(body)), "a11y-contrast")
    body = '<p style="color:#949494;font-size:16px">Small</p>'
    assert by_id(lint_html(page(body)), "a11y-contrast")
    body = '<p style="color:#949494;font-size:14pt;font-weight:bold">Bold 14pt</p>'
    assert not by_id(lint_html(page(body)), "a11y-contrast")


def test_contrast_uses_background_shorthand_and_skips_hidden():
    body = ('<div style="background:#1f2937 url(x.png) no-repeat"><p style="color:#374151">'
            'dark on dark</p></div><div style="display:none;color:#eee">hidden</div>')
    f = by_id(lint_html(page(body)), "a11y-contrast")
    assert len(f) == 1 and "#374151 on #1f2937" in f[0].message


def test_contrast_skips_text_over_background_image():
    body = '<td style="background-image:url(https://example.com/a.png);color:#eee">x</td>'
    assert not by_id(lint_html(page(body)), "a11y-contrast")


def test_default_link_color_is_used():
    body = '<div style="background:#000000"><a href="https://example.com">link</a></div>'
    f = by_id(lint_html(page(body)), "a11y-contrast")
    assert f and "default link color" in f[0].message
