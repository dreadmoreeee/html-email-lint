"""Command line interface."""

import argparse
import os
import sys

from . import __version__
from .checks import Finding, run_checks
from .inputs import expand_paths, load
from .report import to_json, to_markdown

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2


def build_parser():
    p = argparse.ArgumentParser(
        prog="html-email-lint",
        description="Lint HTML emails (.html, .htm, .eml or folders) for real-client "
                    "compatibility.")
    p.add_argument("paths", nargs="+", metavar="PATH")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--output", "-o", metavar="FILE", help="write the report to FILE")
    p.add_argument("--fail-on", choices=("error", "warning"), default="error",
                   help="exit 1 when a finding of this severity or worse exists "
                        "(default: error)")
    p.add_argument("--screenshots", metavar="DIR",
                   help="save 600px and 375px full-page PNG screenshots to DIR")
    p.add_argument("--allow-remote", action="store_true",
                   help="let screenshots load remote images/CSS (blocked by default)")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return p


def lint_paths(paths):
    files, missing = expand_paths(paths)
    results = []
    for path in files:
        item = load(path)
        shown = path.replace(os.sep, "/") if os.sep != "/" else path
        results.append({"path": shown, "kind": item.kind, "html_bytes": item.html_bytes,
                        "findings": run_checks(item), "item": item})
    return results, missing


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code not in (0, None) else EXIT_OK
    results, missing = lint_paths(args.paths)
    if missing:
        for m in missing:
            print("html-email-lint: no such file or folder: %s" % m, file=sys.stderr)
        return EXIT_USAGE
    if not results:
        print("html-email-lint: no .html, .htm or .eml files found", file=sys.stderr)
        return EXIT_USAGE

    if args.screenshots:
        try:
            from .screenshots import take_screenshots
            shots = take_screenshots([r["item"] for r in results], args.screenshots,
                                     allow_remote=args.allow_remote)
        except Exception as e:  # playwright missing or browser not installed
            print("html-email-lint: screenshots failed: %s" % e, file=sys.stderr)
            return EXIT_USAGE
        for r in results:
            s = shots.get(r["item"].path)
            if not s:
                continue
            r["screenshots"] = [f.replace(os.sep, "/") for f in s["files"]]
            for width, actual in sorted(s["overflow"].items()):
                r["findings"].append(Finding(
                    "screenshot-overflow", "warning",
                    "Rendered content is %dpx wide in a %dpx viewport: readers on "
                    "narrow screens get horizontal scrolling or a zoomed-out email"
                    % (actual, width)))
            if s["blocked"]:
                r["findings"].append(Finding(
                    "screenshot-blocked-requests", "info",
                    "%d remote request(s) blocked while taking screenshots (e.g. %s); "
                    "use --allow-remote to load them" % (len(s["blocked"]), s["blocked"][0]),
                    count=len(s["blocked"])))

    text = to_json(results) if args.format == "json" else to_markdown(results)
    if args.output:
        folder = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(folder, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)

    failing = {"error": {"error"}, "warning": {"error", "warning"}}[args.fail_on]
    if any(f.severity in failing for r in results for f in r["findings"]):
        return EXIT_FINDINGS
    return EXIT_OK
