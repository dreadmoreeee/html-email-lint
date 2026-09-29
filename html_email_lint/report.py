"""Markdown and JSON output."""

import json

from . import __version__
from .support_table import TABLE_DATE


def counts(findings):
    c = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        c[f.severity] += 1
    return c


def to_json(results):
    files = []
    total = {"error": 0, "warning": 0, "info": 0}
    for r in results:
        c = counts(r["findings"])
        for k in total:
            total[k] += c[k]
        files.append({
            "path": r["path"],
            "kind": r["kind"],
            "html_bytes": r["html_bytes"],
            "counts": c,
            "findings": [f.to_dict() for f in r["findings"]],
            "screenshots": r.get("screenshots", []),
        })
    data = {"tool": "html-email-lint", "version": __version__,
            "support_table_date": TABLE_DATE, "summary": total, "files": files}
    return json.dumps(data, indent=2, ensure_ascii=True) + "\n"


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(results):
    lines = ["# html-email-lint report", "",
             "| File | Size | Errors | Warnings | Info |", "|---|---:|---:|---:|---:|"]
    for r in results:
        c = counts(r["findings"])
        lines.append("| %s | %.1f KB | %d | %d | %d |" % (
            _cell(r["path"]), r["html_bytes"] / 1024, c["error"], c["warning"], c["info"]))
    for r in results:
        lines += ["", "## %s" % r["path"], ""]
        if not r["findings"]:
            lines.append("No findings.")
        else:
            lines += ["| Severity | Check | Line | Message |", "|---|---|---:|---|"]
            for f in r["findings"]:
                lines.append("| %s | %s | %s | %s |" % (
                    f.severity, f.id, f.line if f.line else "", _cell(f.message)))
            notes = []
            seen = set()
            for f in r["findings"]:
                if f.id in seen or not (f.clients or f.sources):
                    continue
                seen.add(f.id)
                notes.append("- **%s**: %s%s" % (
                    f.id, "; ".join(f.clients) if f.clients else "",
                    (" (source: %s)" % ", ".join(f.sources)) if f.sources else ""))
            if notes:
                lines += ["", "Client notes:", ""] + notes
        if r.get("screenshots"):
            lines += ["", "Screenshots: " + ", ".join(r["screenshots"])]
    lines += ["", "Support table dated %s (caniemail.com and Microsoft Word rendering "
              "docs); check the linked sources before relying on it." % TABLE_DATE, ""]
    return "\n".join(lines)
