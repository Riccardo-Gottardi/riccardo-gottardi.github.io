"""The text of a post as it should be read aloud, for the audio version (src/audio.py).

Works on the post's rendered HTML, so it sees exactly what the page shows:

    headings, paragraphs, lists, quotes   read, one paragraph each (a pause between them)
    links, inline code, emphasis          read as plain text
    tables                                one sentence per row: "Header: cell, header: cell."
    images                                their alt text, if any
    code blocks                           "A code example is shown on the page."
    Mermaid diagrams                      their accDescr (accessible description), else a pointer to the page
    math                                  a pointer to the page (KaTeX only renders in the browser)
    citations [Hof25], footnote marks     skipped
    footnotes, everything from the        skipped, with one closing sentence that they are on the page
    References heading on

Standard library only: imported by build.py (Python 3.14) and never by audio.py, which runs
on an older Python because of the TTS model and gets this text from `build.py --speech`.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser

# Bump when the rules above change in a way that changes the spoken text of existing posts,
# so every post gets a fresh recording. (Changes to the text itself are picked up anyway.)
RULES_VERSION = 1

BLOCKS = {"p", "li", "h2", "h3", "h4", "h5", "h6", "blockquote", "tr", "figcaption", "dt", "dd", "div"}
HEADINGS = {"h2", "h3", "h4", "h5", "h6"}
REFERENCE_IDS = {"references", "bibliography"}
ACC_DESCR = re.compile(r"^\s*accDescr\s*(?::\s*(.+?)\s*$|\{(.*?)\})", re.M | re.S)

CODE = "A code example is shown on the page."
DIAGRAM = "A diagram is shown on the page."
EQUATION = "An equation is shown on the page."
INLINE_MATH = "a formula shown on the page"
REFERENCES = "The references are listed on the page."


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.buf: list[str] = []
        self.skip = 0  # depth inside a subtree that is not read
        self.skip_tag: list[str] = []
        self.done = False  # reached the References heading
        self.pre_mermaid: list[str] | None = None
        self.row: list[str] | None = None  # cells of the current table row
        self.header: list[str] = []  # header cells of the current table
        self.cell: list[str] | None = None
        self.cell_is_th = False

    # ---- helpers ----
    def flush(self) -> None:
        text = " ".join("".join(self.buf).split())
        self.buf = []
        if not text:
            return
        if text[-1] not in ".!?:;…":
            text += "."  # headings, labels, unpunctuated lines: end on a falling tone and a pause
        self.paragraphs.append(text)

    def say(self, sentence: str) -> None:
        self.flush()
        self.paragraphs.append(sentence)

    def start_skip(self, tag: str) -> None:
        self.skip += 1
        self.skip_tag.append(tag)

    # ---- parser callbacks ----
    def handle_starttag(self, tag: str, attrs) -> None:
        if self.done:
            return
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if self.skip:
            if tag == self.skip_tag[-1]:
                self.start_skip(tag)  # nested element of the same kind: track the depth
            return
        if tag in HEADINGS and a.get("id") in REFERENCE_IDS:
            self.say(REFERENCES)
            self.done = True
            return
        if tag == "pre":
            if "mermaid" in classes:
                self.pre_mermaid = []
            else:
                self.say(CODE)
            self.start_skip(tag)
        elif tag == "section" and "footnotes" in classes:
            self.start_skip(tag)
        elif tag == "sup" and "footnote-ref" in classes:
            self.start_skip(tag)
        elif tag == "a" and classes & {"cite", "cite-back", "footnote"}:
            self.start_skip(tag)
        elif tag in {"span", "div"} and "math" in classes:
            if tag == "div":
                self.say(EQUATION)
            else:
                self.buf.append(INLINE_MATH)
            self.start_skip(tag)
        elif tag in {"script", "style", "svg", "button", "nav"}:
            self.start_skip(tag)
        elif tag == "img":
            alt = (a.get("alt") or "").strip()
            if alt:
                self.say(f"Image: {alt.rstrip('.')}.")
        elif tag == "br":
            self.buf.append(" ")
        elif tag == "table":
            self.flush()
            self.header = []
        elif tag == "tr":
            self.flush()
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell, self.cell_is_th = [], tag == "th"
        elif tag in BLOCKS:
            self.flush()

    def handle_endtag(self, tag: str) -> None:
        if self.done:
            return
        if self.skip:
            if tag == self.skip_tag[-1]:
                self.skip -= 1
                self.skip_tag.pop()
                if tag == "pre" and self.pre_mermaid is not None:
                    m = ACC_DESCR.search("".join(self.pre_mermaid))
                    desc = " ".join((m[1] or m[2]).split()) if m else ""
                    self.say(f"Diagram: {desc.rstrip('.')}." if desc else DIAGRAM)
                    self.pre_mermaid = None
            return
        if tag in {"th", "td"} and self.cell is not None and self.row is not None:
            self.row.append((" ".join("".join(self.cell).split()), self.cell_is_th))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            cells, self.row = self.row, None
            if cells and all(is_th for _, is_th in cells):
                self.header = [c for c, _ in cells]
            elif cells:
                parts = [
                    f"{self.header[i]}: {c}" if i < len(self.header) and self.header[i] else c
                    for i, (c, _) in enumerate(cells)
                    if c
                ]
                if parts:
                    self.paragraphs.append(", ".join(parts).rstrip(".") + ".")
        elif tag in BLOCKS:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self.done:
            return
        if self.skip:
            if self.pre_mermaid is not None:
                self.pre_mermaid.append(data)
            return
        if self.cell is not None:
            self.cell.append(data)
        else:
            self.buf.append(data)


def spoken_text(title: str, html: str) -> str:
    """The post as plain text, one paragraph per line, starting with its title."""
    r = _Reader()
    r.feed(html)
    r.close()
    r.flush()
    return "\n".join([title.rstrip(".") + ".", *r.paragraphs])


def audio_key(text: str, voice: str, speed: float) -> str:
    """Name of the cached recording: changes whenever the text, the voice or the rules change."""
    h = hashlib.sha256(f"{RULES_VERSION}|{voice}|{speed}|{text}".encode())
    return h.hexdigest()[:16]
