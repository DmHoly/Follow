import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Nesting(HTMLParser):
    """Checks that every element closes, in the right order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open_tags: list[tuple[str, tuple[int, int]]] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in _VOID_ELEMENTS:
            self.open_tags.append((tag, self.getpos()))

    def handle_startendtag(self, tag: str, attrs) -> None:  # <br/>, <meta ... />
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_ELEMENTS:
            return
        if not self.open_tags:
            self.problems.append(f"</{tag}> at line {self.getpos()[0]} closes nothing")
            return
        open_tag, position = self.open_tags.pop()
        if open_tag != tag:
            self.problems.append(
                f"</{tag}> at line {self.getpos()[0]} closes <{open_tag}> opened at line {position[0]}"
            )


def assert_well_formed_html(html: str) -> None:
    """Fail unless every element in ``html`` is closed, in order.

    Counting ``"<div"`` against ``"</div>"`` - what these tests used to do - says nothing about
    nesting or ordering: ``<div><p></div></p>`` passes it, and so does a page whose escaping is
    broken. Parsing the document catches the mismatches a counter cannot see.

    Inline ``<script>`` bodies are dropped first: Plotly's payload contains ``</div>`` inside
    JavaScript string literals, which is valid there but not markup.
    """
    stripped = re.sub(r"<script\b.*?</script\s*>", "", html, flags=re.S | re.I)
    parser = _Nesting()
    parser.feed(stripped)
    parser.close()

    problems = list(parser.problems)
    if parser.open_tags:
        unclosed = ", ".join(f"<{tag}> (line {position[0]})" for tag, position in parser.open_tags[:5])
        problems.append(f"never closed: {unclosed}")
    assert not problems, "malformed HTML:\n  - " + "\n  - ".join(problems)
