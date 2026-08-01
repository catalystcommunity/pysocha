"""Turn rendered markdown into plain text for indexing.

Pysocha indexes the rendered body of a document, not the finished page, so page
chrome such as navigation and footers never reaches the index. That removes the
need for any indexing markup in templates.
"""

import re
from html.parser import HTMLParser
from typing import List, Tuple


#: Elements whose text is never content.
_SKIP_ELEMENTS = frozenset({"script", "style", "template", "noscript"})

#: Elements that hold code, collected apart from the prose.
_CODE_ELEMENTS = frozenset({"pre", "code"})

#: Elements that end a run of text, so words do not run together.
_BLOCK_ELEMENTS = frozenset({
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
})

_WHITESPACE = re.compile(r"\s+")


def _clean(chunks: List[str]) -> str:
    return _WHITESPACE.sub(" ", "".join(chunks)).strip()


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._code_depth = 0
        self._prose: List[str] = []
        self._code: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_ELEMENTS:
            self._skip_depth += 1
        elif tag in _CODE_ELEMENTS:
            self._code_depth += 1
        if tag in _BLOCK_ELEMENTS:
            self._prose.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_ELEMENTS:
            self._prose.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_ELEMENTS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _CODE_ELEMENTS:
            self._code_depth = max(0, self._code_depth - 1)
        if tag in _BLOCK_ELEMENTS:
            self._prose.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._code_depth > 0:
            self._code.append(data)
        else:
            self._prose.append(data)

    def result(self) -> Tuple[str, str]:
        return _clean(self._prose), _clean(self._code)


def split_text_and_code(html: str) -> Tuple[str, str]:
    """Split rendered markdown into prose text and code text.

    The two are kept apart so that each configured search can decide whether to
    index code. Syntax highlighting wraps code in many small elements, so this
    also stops highlight markup from reaching the index.
    """
    if not html:
        return "", ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.result()


def html_to_text(html: str, include_code: bool = False) -> str:
    """Extract indexable plain text from rendered markdown."""
    prose, code = split_text_and_code(html)
    if include_code and code:
        return prose + "\n" + code
    return prose
