"""A forgiving element tree built on the standard library html.parser."""

from html.parser import HTMLParser

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
# start tag -> tags it implicitly closes when still open in the current scope
IMPLIED_END = {
    "p": {"p"},
    "li": {"li"},
    "tr": {"tr", "td", "th"},
    "td": {"td", "th"},
    "th": {"td", "th"},
    "tbody": {"tbody", "thead", "tr", "td", "th"},
    "thead": {"tbody", "thead", "tr", "td", "th"},
    "option": {"option"},
}
SCOPE_STOP = {"table", "html", "body", "ul", "ol", "select"}
BLOCK_CLOSES_P = {"div", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
                  "blockquote", "hr", "pre", "section"}


class Text:
    __slots__ = ("data", "line", "parent")

    def __init__(self, data, line, parent):
        self.data = data
        self.line = line
        self.parent = parent


class Element:
    def __init__(self, tag, attrs, line, parent):
        self.tag = tag
        self.attrs = {}
        for k, v in attrs:
            if k not in self.attrs:
                self.attrs[k] = v if v is not None else ""
        self.line = line
        self.parent = parent
        self.children = []

    def get(self, name, default=None):
        return self.attrs.get(name, default)

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Element):
                yield from c.iter()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def text(self):
        out = []
        for c in self.children:
            out.append(c.data if isinstance(c, Text) else c.text())
        return "".join(out)

    def __repr__(self):
        return "<%s line %s>" % (self.tag, self.line)


class Document:
    def __init__(self):
        self.root = Element("#document", [], 1, None)
        self.comments = []  # (text, line)
        self.styles = []    # (css text, line, element)

    def iter(self):
        return self.root.iter()

    def find_all(self, tag):
        return [e for e in self.iter() if e.tag == tag]

    def find(self, tag):
        for e in self.iter():
            if e.tag == tag:
                return e
        return None


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.doc = Document()
        self.stack = [self.doc.root]
        self._style = None

    @property
    def cur(self):
        return self.stack[-1]

    def _close_implied(self, tag):
        closes = set(IMPLIED_END.get(tag, ()))
        if tag in BLOCK_CLOSES_P:
            closes.add("p")
        if not closes:
            return
        cut = None
        for i in range(len(self.stack) - 1, 0, -1):
            t = self.stack[i].tag
            if t in closes:
                cut = i  # keep going: close the outermost match in scope
            elif t in SCOPE_STOP:
                break
        if cut is not None:
            del self.stack[cut:]

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        self._close_implied(tag)
        el = Element(tag, attrs, line, self.cur)
        self.cur.children.append(el)
        if tag not in VOID:
            self.stack.append(el)
        if tag == "style":
            self._style = (el, line, [])

    def handle_startendtag(self, tag, attrs):
        line = self.getpos()[0]
        self._close_implied(tag)
        el = Element(tag, attrs, line, self.cur)
        self.cur.children.append(el)

    def handle_endtag(self, tag):
        if tag == "style" and self._style is not None:
            el, line, parts = self._style
            self.doc.styles.append(("".join(parts), line, el))
            self._style = None
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self._style is not None:
            self._style[2].append(data)
        self.cur.children.append(Text(data, self.getpos()[0], self.cur))

    def handle_comment(self, data):
        self.doc.comments.append((data, self.getpos()[0]))


def parse(html):
    b = _Builder()
    b.feed(html)
    b.close()
    if b._style is not None:
        el, line, parts = b._style
        b.doc.styles.append(("".join(parts), line, el))
    return b.doc
