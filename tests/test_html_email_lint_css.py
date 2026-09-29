import pytest

from html_email_lint.css import (TRANSPARENT, color_in_background, contrast_ratio,
                                 parse_color, parse_declarations, parse_stylesheet,
                                 relative_luminance)
from html_email_lint.dom import parse


def test_wcag_contrast_examples():
    assert contrast_ratio((0x77, 0x77, 0x77), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast_ratio((255, 255, 255), (255, 255, 255)) == pytest.approx(1.0)
    # order does not matter
    assert contrast_ratio((255, 255, 255), (0x77, 0x77, 0x77)) == \
        contrast_ratio((0x77, 0x77, 0x77), (255, 255, 255))


def test_relative_luminance():
    assert relative_luminance((255, 255, 255)) == pytest.approx(1.0)
    assert relative_luminance((0, 0, 0)) == 0.0
    assert relative_luminance((255, 0, 0)) == pytest.approx(0.2126)


def test_parse_color_forms():
    assert parse_color("#fff") == (255, 255, 255)
    assert parse_color("#1F6F5C") == (0x1f, 0x6f, 0x5c)
    assert parse_color("rgb(10, 20, 30)") == (10, 20, 30)
    assert parse_color("rgba(10,20,30,1)") == (10, 20, 30)
    assert parse_color("rgba(10,20,30,0)") == TRANSPARENT
    assert parse_color("rgba(10,20,30,.5)") is None
    assert parse_color("White") == (255, 255, 255)
    assert parse_color("transparent") == TRANSPARENT
    assert parse_color("ffffff") == (255, 255, 255)
    assert parse_color("inherit") is None


def test_background_shorthand_color():
    assert color_in_background("#eef1fe") == (0xee, 0xf1, 0xfe)
    assert color_in_background("url(a.png) no-repeat #000") == (0, 0, 0)
    assert color_in_background("url(#abc.png)") is None


def test_parse_declarations():
    d = parse_declarations("color:#fff; background:url(a;b.png) ; width:100% !important")
    assert d == [("color", "#fff", False), ("background", "url(a;b.png)", False),
                 ("width", "100%", True)]


def test_parse_stylesheet_contexts_and_lines():
    css = "\n.a{color:red}\n/* c */\n@media (max-width:600px){\n .b{width:100%}\n}\n@import url(x.css);\n@font-face{font-family:X}"
    rules, at_rules = parse_stylesheet(css, first_line=10)
    a = next(r for r in rules if r.selector == ".a")
    b = next(r for r in rules if r.selector == ".b")
    assert a.line == 11 and a.context == ()
    assert b.line == 14 and b.context[0].startswith("@media")
    names = [n for n, _, _ in at_rules]
    assert names == ["media", "import", "font-face"]


def test_dom_implied_end_tags_and_lines():
    doc = parse("<table>\n<tr><td>a<td>b\n<tr><td>c</table><p>x<p>y")
    tds = doc.find_all("td")
    assert [t.text() for t in tds] == ["a", "b\n", "c"]
    assert all(t.parent.tag == "tr" for t in tds)
    assert tds[2].line == 3
    ps = doc.find_all("p")
    assert [p.parent.tag for p in ps] == ["#document", "#document"]
