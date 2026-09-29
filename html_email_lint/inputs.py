"""Read .html/.htm/.eml files (or folders of them)."""

import email
import email.policy
import os
from dataclasses import dataclass, field

HTML_EXT = (".html", ".htm")
EML_EXT = (".eml",)


@dataclass
class EmailInput:
    path: str
    kind: str                     # "html" or "eml"
    html: str | None = None
    html_bytes: int = 0
    text: str | None = None       # plain-text part (eml only)
    headers: dict = field(default_factory=dict)   # eml only, lower-case keys
    subject: str | None = None


def decode_html_bytes(raw):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_html(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return EmailInput(path=path, kind="html", html=decode_html_bytes(raw),
                      html_bytes=len(raw))


def load_eml(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return parse_eml_bytes(raw, path)


def parse_eml_bytes(raw, path="<eml>"):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    html = text = None
    for part in msg.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype == "text/html" and html is None:
            html = _content(part)
        elif ctype == "text/plain" and text is None:
            text = _content(part)
    headers = {}
    for k, v in msg.items():
        headers.setdefault(k.lower(), str(v))
    item = EmailInput(path=path, kind="eml", html=html, text=text,
                      headers=headers, subject=headers.get("subject"))
    if html is not None:
        item.html_bytes = len(html.encode("utf-8"))
    return item


def _content(part):
    try:
        return part.get_content()
    except (LookupError, UnicodeDecodeError):
        payload = part.get_payload(decode=True) or b""
        return payload.decode("utf-8", errors="replace")


def expand_paths(paths):
    """Files in the order given; folders are walked (sorted) for html/htm/eml."""
    files, missing = [], []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames.sort()
                for name in sorted(filenames):
                    if name.lower().endswith(HTML_EXT + EML_EXT):
                        files.append(os.path.join(dirpath, name))
        elif os.path.isfile(p):
            files.append(p)
        else:
            missing.append(p)
    return files, missing


def load(path):
    if path.lower().endswith(EML_EXT):
        return load_eml(path)
    return load_html(path)
