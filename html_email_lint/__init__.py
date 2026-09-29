"""Lint HTML emails for real-client compatibility before sending."""

__version__ = "0.1.0"

from .checks import Finding, run_checks  # noqa: E402
from .inputs import EmailInput, load, parse_eml_bytes  # noqa: E402


def lint_html(html, path="<string>"):
    """Lint an HTML string and return a list of Finding."""
    item = EmailInput(path=path, kind="html", html=html,
                      html_bytes=len(html.encode("utf-8")))
    return run_checks(item)


def lint_file(path):
    """Lint one .html/.htm/.eml file and return a list of Finding."""
    return run_checks(load(path))


__all__ = ["Finding", "EmailInput", "lint_html", "lint_file", "load",
           "parse_eml_bytes", "run_checks", "__version__"]
