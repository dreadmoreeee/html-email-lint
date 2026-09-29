import json
import os
from email.message import EmailMessage

import pytest

from html_email_lint.cli import main
from html_email_lint.inputs import parse_eml_bytes
from html_email_lint.checks import run_checks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
GOOD_HTML = open(os.path.join(EXAMPLES, "good.html"), encoding="utf-8").read()


def make_eml(text=True, unsub=True, post=True, html=GOOD_HTML):
    msg = EmailMessage()
    msg["From"] = "a@example.com"
    msg["To"] = "b@example.com"
    msg["Subject"] = "Hello"
    if unsub:
        msg["List-Unsubscribe"] = "<https://example.com/u?x=1>, <mailto:u@example.com>"
    if post:
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    if text:
        msg.set_content("Plain version")
        if html:
            msg.add_alternative(html, subtype="html")
    elif html:
        msg.set_content(html, subtype="html")
    else:
        msg.set_content("only text")
    return bytes(msg)


def ids(item):
    return [f.id for f in run_checks(item)]


def test_eml_with_everything():
    item = parse_eml_bytes(make_eml())
    assert item.html and item.text.strip() == "Plain version"
    assert item.headers["list-unsubscribe-post"] == "List-Unsubscribe=One-Click"
    f = ids(item)
    for bad in ("text-part-missing", "unsubscribe-header-missing", "unsubscribe-post-missing"):
        assert bad not in f


def test_eml_without_text_part():
    assert "text-part-missing" in ids(parse_eml_bytes(make_eml(text=False)))


def test_eml_without_list_unsubscribe():
    f = ids(parse_eml_bytes(make_eml(unsub=False, post=False)))
    assert "unsubscribe-header-missing" in f


def test_eml_without_one_click_post():
    f = ids(parse_eml_bytes(make_eml(post=False)))
    assert "unsubscribe-post-missing" in f


def test_eml_without_html_part():
    f = run_checks(parse_eml_bytes(make_eml(html=None, text=False)))
    assert f[0].id == "html-part-missing" and f[0].severity == "error"


def test_folder_input_and_json(tmp_path, capsys):
    sub = tmp_path / "nested"
    sub.mkdir()
    (tmp_path / "a.html").write_text(GOOD_HTML, encoding="utf-8")
    (sub / "b.eml").write_bytes(make_eml())
    (sub / "c.htm").write_text(GOOD_HTML, encoding="utf-8")
    (sub / "notes.txt").write_text("ignored", encoding="utf-8")
    code = main([str(tmp_path), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert sorted(os.path.basename(f["path"]) for f in data["files"]) == ["a.html", "b.eml", "c.htm"]
    kinds = {os.path.basename(f["path"]): f["kind"] for f in data["files"]}
    assert kinds["b.eml"] == "eml"
    assert data["support_table_date"]
    assert set(data["summary"]) == {"error", "warning", "info"}


def test_markdown_output_file(tmp_path):
    out = tmp_path / "r" / "report.md"
    code = main([os.path.join(EXAMPLES, "bad.html"), "--output", str(out)])
    text = out.read_text(encoding="utf-8")
    assert code == 1
    assert text.startswith("# html-email-lint report")
    assert "| Severity | Check | Line | Message |" in text
    assert "url-relative" in text and "caniemail.com" in text


def test_exit_codes(tmp_path, capsys):
    good = os.path.join(EXAMPLES, "good.html")
    bad = os.path.join(EXAMPLES, "bad.html")
    assert main([good]) == 0
    assert main([bad]) == 1
    warn_only = tmp_path / "w.html"
    warn_only.write_text(GOOD_HTML.replace('<html lang="en">', "<html>"), encoding="utf-8")
    assert main([str(warn_only)]) == 0
    assert main([str(warn_only), "--fail-on", "warning"]) == 1
    assert main([str(tmp_path / "missing.html")]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty)]) == 2
    assert main([]) == 2
    assert main([good, "--format", "xml"]) == 2
    capsys.readouterr()


def test_examples_sample_eml_is_clean():
    assert main([os.path.join(EXAMPLES, "sample.eml"), "--fail-on", "warning"]) == 0


def _chromium_available():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_available(), reason="Playwright Chromium not installed")
def test_screenshots_offline(tmp_path, capsys):
    from html_email_lint.screenshots import png_size
    page = tmp_path / "mail.html"
    page.write_text(
        '<html lang="en"><body style="margin:0">'
        '<table role="presentation" width="700"><tr><td>'
        '<img src="https://example.invalid/remote.png" width="10" height="10" alt="x">'
        '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="10" height="10" alt="y">'
        '</td></tr></table></body></html>', encoding="utf-8")
    shots = tmp_path / "shots"
    code = main([str(page), "--screenshots", str(shots), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    files = sorted(os.listdir(shots))
    assert files == ["mail-375.png", "mail-600.png"]
    assert png_size(str(shots / "mail-600.png"))[0] >= 600
    found = {f["id"]: f for f in data["files"][0]["findings"]}
    blocked = found["screenshot-blocked-requests"]
    assert "example.invalid" in blocked["message"]
    assert "data:" not in blocked["message"]
    assert "screenshot-overflow" in found
