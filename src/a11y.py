"""Accessibility checker for the built site.

    uv run src/a11y.py                    check docs/ (the production build)
    uv run src/a11y.py --out .preview     check the local preview (drafts included)
    uv run src/a11y.py --strict           exit with status 1 if anything is found (for a pipeline)

It reads the generated HTML and CSS, so templates and content are both covered, and
prints one `warning:` per problem with the WCAG criterion it breaks and a `fix:` hint.
Problems in a post's text point to its Markdown source and line; problems in the page
templates are reported once, with the pages they appear on.

These are **static** checks: they don't run a browser, so they cannot see reflow,
overlap with Wider spacing on, or colours that only appear after CSS is applied.
Those stay manual (see CLAUDE.md, "Checks before committing").

To add a check: write a function that yields `Finding`s and add it to PAGE_CHECKS
(per page) or SITE_CHECKS (once per run). Rule ids are short and stable, so a future
publication pipeline can filter or ignore them.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- findings

@dataclass
class Finding:
    rule: str  # stable id, e.g. "mermaid-desc"
    message: str  # what is wrong, with the WCAG criterion
    fix: str  # how to fix it
    in_content: bool = False  # inside the post/page text (.prose) rather than the template
    needle: str | tuple[str, ...] = ""  # text to look for in the Markdown source (first that matches gives the line)
    file: str = ""  # set when the problem is in a file other than the page (CSS)
    line: int | None = None
    pages: list[str] = field(default_factory=list)  # URLs it was found on


# --------------------------------------------------------------------------- a tiny DOM

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Node | None = None
    children: list[Node | str] = field(default_factory=list)

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    def classes(self) -> set[str]:
        return set((self.get("class") or "").split())

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk()

    def find_all(self, tag: str) -> list[Node]:
        return [n for n in self.walk() if n.tag == tag]

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent

    def hidden(self) -> bool:
        """Hidden from assistive technology (aria-hidden or the hidden attribute)."""
        return any(n.get("aria-hidden") == "true" or "hidden" in n.attrs for n in [self, *self.ancestors()])

    def in_prose(self) -> bool:
        return any("prose" in n.classes() or "lead" in n.classes() for n in [self, *self.ancestors()])


class TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {}, 1)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v if v is not None else "" for k, v in attrs}, self.getpos()[0], self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        # close up to the matching open tag; ignore stray end tags
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html: str) -> Node:
    b = TreeBuilder()
    b.feed(html)
    b.close()
    return b.root


def squash(text: str) -> str:
    return " ".join(text.split())


def accessible_name(node: Node, doc: Node) -> str:
    """A simplified version of the accessible-name computation (enough for this site)."""
    if node.get("aria-hidden") == "true":
        return ""
    if node.get("aria-labelledby"):
        ids = node.get("aria-labelledby").split()
        return squash(" ".join(accessible_name(n, doc) for n in doc.walk() if n.get("id") in ids))
    if node.get("aria-label", "").strip():
        return squash(node.get("aria-label"))
    if node.tag == "img":
        return squash(node.get("alt") or "")
    parts = []
    for c in node.children:
        if isinstance(c, str):
            parts.append(c)
        elif c.tag not in ("script", "style"):
            parts.append(accessible_name(c, doc))
    name = squash(" ".join(parts))
    return name or squash(node.get("title") or "")


def focusable(n: Node) -> bool:
    if n.tag == "a" and "href" in n.attrs:
        return True
    if n.tag in ("button", "input", "select", "textarea") and "disabled" not in n.attrs:
        return True
    t = n.get("tabindex")
    return t is not None and t.lstrip("-").isdigit() and int(t) >= 0


# --------------------------------------------------------------------------- page checks

def check_document(doc: Node):
    html = next((n for n in doc.walk() if n.tag == "html"), None)
    if html is None or not (html.get("lang") or "").strip():
        yield Finding("lang", "the page has no language (<html lang>), so screen readers may use the wrong voice (WCAG 3.1.1)",
                      "set lang on <html> in templates/base.html")
    title = next(iter(doc.find_all("title")), None)
    if title is None or not squash(title.text()):
        yield Finding("title", "the page has no <title> (WCAG 2.4.2)", "fill the title block of the template")
    for meta in doc.find_all("meta"):
        if meta.get("name") == "viewport":
            content = (meta.get("content") or "").replace(" ", "").lower()
            scale = re.search(r"maximum-scale=([\d.]+)", content)
            if "user-scalable=no" in content or "user-scalable=0" in content or (scale and float(scale[1]) < 2):
                yield Finding("zoom", "the viewport meta tag blocks pinch zoom (WCAG 1.4.4)",
                              "remove user-scalable=no and maximum-scale from the viewport meta tag")
    mains = doc.find_all("main")
    if len(mains) != 1:
        yield Finding("main", f"the page has {len(mains)} <main> landmarks, it needs exactly one (WCAG 1.3.1)",
                      "wrap the page content in a single <main>")


def check_skip_link(doc: Node):
    body = next((n for n in doc.walk() if n.tag == "body"), doc)
    first = next((n for n in body.walk() if focusable(n) and not n.hidden()), None)
    ids = {n.get("id") for n in doc.walk() if n.get("id")}
    href = first.get("href", "") if first is not None and first.tag == "a" else ""
    if not (href.startswith("#") and href[1:] in ids):
        yield Finding("skip-link", "no \"Skip to content\" link: keyboard users tab through the sidebar on every page "
                      "before reaching the content (WCAG 2.4.1, best practice)",
                      "add <a class=\"skip-link\" href=\"#content\">Skip to content</a> as the first element of <body>, "
                      "and id=\"content\" on <main>")


def check_headings(doc: Node):
    heads = [n for n in doc.walk() if re.fullmatch(r"h[1-6]", n.tag) and not n.hidden()]
    h1 = [h for h in heads if h.tag == "h1"]
    if len(h1) != 1:
        yield Finding("h1", f"the page has {len(h1)} <h1> headings, it needs exactly one (WCAG 1.3.1)",
                      "keep the page title as the only h1; Markdown '#' headings become h2")
    prev = 0
    for h in heads:
        level, text = int(h.tag[1]), squash(h.text())
        if not text:
            yield Finding("heading-empty", f"an empty <{h.tag}> (WCAG 2.4.6)", "give the heading text or remove it",
                          in_content=h.in_prose())
        if prev and level > prev + 1:
            # the page title is the h1, so Markdown "#" is h2: Markdown level = HTML level - 1
            yield Finding("heading-skip", f"heading \"{text}\" jumps from h{prev} to h{level}, skipping a level (WCAG 1.3.1)",
                          f"write it as {'#' * prev} {text} (one level below the previous heading; '#' is the top level "
                          "in a post)" if h.in_prose() else "use the next heading level",
                          in_content=h.in_prose(), needle=f"{'#' * (level - 1)} {text}")
        prev = level


def check_ids(doc: Node):
    seen: dict[str, int] = defaultdict(int)
    for n in doc.walk():
        if n.get("id"):
            seen[n.get("id")] += 1
    for i, count in seen.items():
        if count > 1:
            yield Finding("id-duplicate", f"id=\"{i}\" is used {count} times; links and labels pointing to it break (WCAG 4.1.1)",
                          "make the ids unique (for headings: give them different text)", needle=i)
    for a in doc.find_all("a"):
        href = a.get("href") or ""
        if href.startswith("#") and len(href) > 1 and href[1:] not in seen:
            close = difflib.get_close_matches(href[1:], list(seen), n=1)
            yield Finding("anchor", f"link to \"{href}\" points to nothing on the page (WCAG 2.4.4)",
                          f"did you mean #{close[0]}?" if close else
                          "heading ids are the heading text in lowercase, words joined by '-'",
                          in_content=a.in_prose(), needle=href)


GENERIC_LINK_TEXT = {"here", "click here", "this", "link", "this link", "more", "read more", "click", "go", "page"}


def check_links_and_buttons(doc: Node):
    for n in doc.walk():
        if n.hidden():
            if focusable(n):
                yield Finding("hidden-focusable", f"a focusable <{n.tag}> is inside aria-hidden content: keyboard users reach it "
                              "but screen readers can't announce it (WCAG 4.1.2)",
                              "remove aria-hidden, or take the element out of the tab order", in_content=n.in_prose())
            continue
        if n.tag == "a" and "href" in n.attrs and not any(x.tag == "svg" for x in n.ancestors()):  # see check_svgs
            name = accessible_name(n, doc)
            href = n.get("href")
            if not name:
                yield Finding("link-name", f"a link to \"{href}\" has no text, so screen readers only read the URL (WCAG 2.4.4)",
                              "give the link text, or alt text to its image, or an aria-label", in_content=n.in_prose(),
                              needle=href)
            elif name.lower().strip(".!:→ ") in GENERIC_LINK_TEXT:
                yield Finding("link-text", f"link text \"{name}\" doesn't say where it goes (WCAG 2.4.4)",
                              "use the destination as link text, e.g. [the Mermaid docs](…) instead of [here](…)",
                              in_content=n.in_prose(), needle=f"[{name}]")
        elif n.tag == "button" and not accessible_name(n, doc):
            yield Finding("button-name", "a <button> has no text or label (WCAG 4.1.2)", "add visible text to the button")
        t = n.get("tabindex")
        if t and t.isdigit() and int(t) > 0:
            yield Finding("tabindex", f"tabindex=\"{t}\" changes the keyboard order (WCAG 2.4.3)", "use tabindex=\"0\" or none")


IMAGE_NAME = re.compile(r"^(img|image|picture|photo|screenshot|figure|graph|diagram|logo)?[\s_-]*\d*$|\.(png|jpe?g|gif|svg|webp|avif)$", re.I)


def check_images(doc: Node):
    for img in doc.find_all("img"):
        if img.hidden():
            continue
        src = img.get("src") or ""
        alt = img.get("alt")
        short = src.rsplit("/", 1)[-1].split("?")[0]
        if alt is None:
            yield Finding("img-alt", f"image \"{short}\" has no alt attribute, so screen readers read the file name (WCAG 1.1.1)",
                          "write ![what the image shows](file) in Markdown", in_content=img.in_prose(),
                          needle=(f'src="{src}"', short))
        elif not alt.strip() and img.in_prose():
            # Markdown's ![](file) produces alt="", which marks the image as decorative: usually by mistake
            yield Finding("img-alt", f"image \"{short}\" has empty alt text, so screen readers skip it (WCAG 1.1.1)",
                          "write ![what the image shows](file); leave it empty only if the image is pure decoration",
                          in_content=True, needle=(f"![]({src}", short))
        elif alt.strip() and IMAGE_NAME.search(alt.strip()):
            yield Finding("img-alt", f"image \"{short}\" has alt text \"{alt}\", which doesn't describe it (WCAG 1.1.1)",
                          "describe what the image shows, or the point it makes", in_content=img.in_prose(),
                          needle=(f"![{alt}]", f'alt="{alt}"', short))


ACC_TITLE = re.compile(r"^\s*accTitle\s*:\s*\S", re.M)
ACC_DESCR = re.compile(r"^\s*accDescr\s*(:\s*\S|\{)", re.M)


def check_mermaid(doc: Node):
    blocks = [n for n in doc.find_all("pre") if "mermaid" in n.classes()]
    for i, pre in enumerate(blocks):
        src = pre.text()
        kind = squash(src).split(" ", 1)[0] if src.strip() else "diagram"
        needle = f"```mermaid#{i}"  # the i-th mermaid fence of the source
        missing = [k for k, rx in (("accTitle", ACC_TITLE), ("accDescr", ACC_DESCR)) if not rx.search(src)]
        if missing:
            yield Finding("mermaid-alt", f"Mermaid {kind} has no {' and no '.join(missing)}: it is drawn as an SVG, so screen "
                          "readers get no name or description for it (WCAG 1.1.1)",
                          "add `accTitle: <short name>` and `accDescr: <what the diagram shows, in a sentence or two>` "
                          "right after the diagram type (a long description can use `accDescr { … }`)",
                          in_content=True, needle=needle)


def check_svgs(doc: Node):
    for svg in doc.find_all("svg"):
        if svg.hidden() or any(a.tag == "svg" for a in svg.ancestors()):
            continue
        named = svg.get("aria-label", "").strip() or svg.get("aria-labelledby") or any(
            c.tag == "title" for c in svg.children if isinstance(c, Node))
        if not named and svg.get("role") not in ("presentation", "none"):
            yield Finding("svg-name", "an inline SVG has no name and isn't hidden (WCAG 1.1.1)",
                          "add role=\"img\" and aria-label (or a <title> as first child), "
                          "or aria-hidden=\"true\" if it is decoration", in_content=svg.in_prose(), needle="<svg")
        for a in svg.find_all("a"):
            if not any(c.tag == "title" for c in a.children if isinstance(c, Node)) and not a.get("aria-label"):
                yield Finding("svg-link", f"a link inside an SVG (to \"{a.get('href')}\") has no <title> (WCAG 2.4.4)",
                              "add a <title> child with the full name (src/blog_graph.py does this for the graph)")


def check_tables(doc: Node):
    for t in doc.find_all("table"):
        if not t.find_all("th"):
            yield Finding("table-header", "a table has no header cells (WCAG 1.3.1)",
                          "give the Markdown table a header row (the first row, followed by | - | - |)",
                          in_content=t.in_prose(), needle=("<table", "|"))


def check_media(doc: Node):
    for v in doc.find_all("video"):
        if not any(t.get("kind") in ("captions", "subtitles") for t in v.find_all("track")):
            yield Finding("video-captions", "a <video> has no captions track (WCAG 1.2.2)",
                          "add <track kind=\"captions\" src=\"….vtt\" srclang=\"en\">", in_content=v.in_prose(), needle="<video")
    for f in doc.find_all("iframe"):
        if not (f.get("title") or "").strip():
            yield Finding("iframe-title", "an <iframe> has no title (WCAG 4.1.2)", "add title=\"what it shows\"",
                          in_content=f.in_prose(), needle="<iframe")


PAGE_CHECKS = [check_document, check_skip_link, check_headings, check_ids, check_links_and_buttons,
               check_images, check_mermaid, check_svgs, check_tables, check_media]


# --------------------------------------------------------------------------- CSS checks

def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    def chan(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")


def css_rules(css: str):
    """(selector, declarations, line) for every plain rule, including those inside @media."""
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m[0].count("\n"), css, flags=re.S)
    for m in RULE.finditer(css):
        selector = squash(m[1])
        decls = {}
        for d in m[2].split(";"):
            if ":" in d:
                k, v = d.split(":", 1)
                decls[k.strip()] = v.strip()
        yield selector, decls, css.count("\n", 0, m.start(2)) + 1


def css_files(out: Path) -> list[Path]:
    """The CSS the pages actually link, in cascade order."""
    links = re.findall(r'<link rel="stylesheet" href="/assets/([^"?]+)', (out / "index.html").read_text(encoding="utf-8"))
    return [out / "assets" / f for f in links if (out / "assets" / f).is_file()]


def source_of_css(path: Path, out: Path) -> str:
    """docs/assets/x.css is a copy of static/x.css; report the file the author edits."""
    rel = path.relative_to(out / "assets")
    src = ROOT / "static" / rel
    if src.is_file():
        return str(src.relative_to(ROOT))
    if path.name == "pygments.css":
        return "src/build.py (Pygments style, written to assets/pygments.css)"
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def check_css(out: Path):
    tokens: dict[str, tuple[str, str, int]] = {}  # --name -> (value, file, line), later files override
    colors: dict[str, dict[str, tuple[str, str, int]]] = defaultdict(dict)
    for path in css_files(out):
        name = source_of_css(path, out)
        for selector, decls, line in css_rules(path.read_text(encoding="utf-8")):
            for k, v in decls.items():
                if selector == ":root" and k.startswith("--"):
                    tokens[k] = (v, name, line)
                m = re.fullmatch(r'\[data-color="(\w+)"\]', selector)
                if m and k.startswith("--"):
                    colors[m[1]][k] = (v, name, line)
                if k == "color" and "var(--c-strong)" in v:
                    yield Finding("strong-as-text", f"`{selector}` uses --c-strong for text, which is unreadable on white for green "
                                  "and yellow (WCAG 1.4.3, DESIGN.md §1)", "use --c-ink for text; --c-strong is for fills only",
                                  file=name, line=line)
                if selector in ("html", ":root") and k == "font-size" and v.endswith("px"):
                    yield Finding("root-font-px", f"`{selector} {{ font-size: {v} }}` overrides the reader's default text size "
                                  "set in the browser (WCAG 1.4.4, best practice)", "use font-size: 100%", file=name, line=line)
                if ":focus" in selector and ":focus-visible" not in selector and k == "outline" and v.split()[0] in ("none", "0"):
                    base = selector.replace(":focus", ":focus-visible")
                    if not any(base in s for s, *_ in css_rules(path.read_text(encoding="utf-8"))):
                        yield Finding("focus-hidden", f"`{selector}` removes the focus outline with no :focus-visible replacement "
                                      "(WCAG 2.4.7)", f"add a `{base}` rule that shows focus another way", file=name, line=line)
            # .w is whitespace: its colour is never visible
            if "pygments" in path.name and "color" in decls and selector.startswith(".highlight") and selector != ".highlight .w":
                hexes = HEX.findall(decls["color"])
                bg = tokens.get("--bg", ("#ffffff",))[0]
                if hexes and HEX.fullmatch(bg) and contrast(hexes[0], bg) < 4.5:
                    yield Finding("contrast", f"code colour {hexes[0]} on {bg} is {contrast(hexes[0], bg):.2f}:1, needs 4.5:1 "
                                  f"(`{selector}`, WCAG 1.4.3)", "pick a darker Pygments style in build.py, or override the colour",
                                  file=name, line=line)

    def value(name: str, scope: dict) -> tuple[str | None, str, int]:
        v, f, ln = scope.get(name) or tokens.get(name) or (None, "", 0)
        for _ in range(5):  # resolve var(--x) chains
            if v is None:
                break
            m = re.fullmatch(r"var\((--[\w-]+)(?:,\s*(.+))?\)", v)
            if not m:
                break
            v = (scope.get(m[1]) or tokens.get(m[1]) or (m[2], f, ln))[0]
        return (v if v and HEX.fullmatch(v) else None), f, ln

    # (foreground token, background token, minimum ratio, where it is used)
    neutral = [("--fg", "--bg", 4.5, "body text"), ("--muted", "--bg", 4.5, "secondary text"),
               ("--line", "--bg", 3.0, "edges and borders (WCAG 1.4.11)")]
    per_color = [("--c-ink", "--bg", 4.5, "links and coloured text"),
                 ("--c-ink", "--c-pale", 4.5, "coloured text on pale backgrounds"),
                 ("--fg", "--c-pale", 4.5, "text in pills, breadcrumbs, table headers"),
                 ("--c-on-strong", "--c-strong", 4.5, "text on strong fills: active switch, root node, draft badge")]
    checks = [("", {}, p) for p in neutral] + [(c, scope, p) for c, scope in colors.items() for p in per_color]
    for color, scope, (fg, bg, need, use) in checks:
        (a, fa, la), (b, fb, lb) = value(fg, scope), value(bg, scope)
        if a and b and (ratio := contrast(a, b)) < need:
            where = f"{color}: " if color else ""
            yield Finding("contrast", f"{where}{fg} {a} on {bg} {b} is {ratio:.2f}:1, needs {need:g}:1 ({use}, WCAG "
                          f"{'1.4.11' if need == 3 else '1.4.3'})",
                          "darken the text colour or the fill; for text on --c-strong, a dark --c-on-strong such as #151515",
                          file=fa or fb, line=la or lb)


# --------------------------------------------------------------------------- sources

def page_sources(content: Path) -> dict[str, Path]:
    """URL -> the Markdown file whose text is on that page, using the build's own content loader."""
    sys.path.insert(0, str(ROOT / "src"))
    import build  # noqa: PLC0415  (only needed to map pages to sources)

    with contextlib.redirect_stdout(io.StringIO()):  # the build prints its own warnings
        blog = build.load_section(content / "blog", None, drafts=True, title="Blog")
    out: dict[str, Path] = {"/": content / "home.md"}

    def walk(s) -> None:
        if s.source:
            out[s.url] = s.source
        for p in s.posts:
            out[p.url] = p.source
        for c in s.children:
            walk(c)

    walk(blog)
    return out


def locate(source: Path, needle: str | tuple[str, ...]) -> int | None:
    """Line of the first of `needle` found in the source. "```mermaid#2" means the third Mermaid fence."""
    if not needle or not source.is_file():
        return None
    lines = source.read_text(encoding="utf-8").splitlines()
    for n in (needle,) if isinstance(needle, str) else needle:
        if m := re.fullmatch(r"(```mermaid)#(\d+)", n):
            hits = [i for i, ln in enumerate(lines, 1) if ln.strip().startswith(m[1])]
            if int(m[2]) < len(hits):
                return hits[int(m[2])]
        elif line := next((i for i, ln in enumerate(lines, 1) if n in ln), None):
            return line
    return None


# --------------------------------------------------------------------------- running

def url_of(page: Path, out: Path) -> str:
    rel = page.relative_to(out).as_posix()
    return "/" + rel.removesuffix("index.html") if rel.endswith("index.html") else "/" + rel


def check_site(out: Path, content: Path) -> list[Finding]:
    sources = page_sources(content)
    merged: dict[tuple, Finding] = {}

    def add(f: Finding, url: str | None) -> None:
        key = (f.rule, f.message, f.file, f.line)
        kept = merged.setdefault(key, f)
        if url and url not in kept.pages:
            kept.pages.append(url)

    for page in sorted(out.rglob("*.html")):
        url = url_of(page, out)
        doc = parse(page.read_text(encoding="utf-8"))
        for check in PAGE_CHECKS:
            for f in check(doc):
                src = sources.get(url)
                if f.in_content and src:
                    f.file = str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else str(src)
                    f.line = locate(src, f.needle)
                add(f, url)
    for f in check_css(out):
        add(f, None)
    return sorted(merged.values(), key=lambda f: (f.file == "", f.file, f.line or 0, f.rule))


def report(findings: list[Finding], out: Path, pages: int) -> None:
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"Accessibility check of {shown}/ ({pages} pages)")
    for f in findings:
        if f.file:
            where = f"{f.file}:{f.line}" if f.line else f.file
            if f.in_content and f.pages:
                where += f" ({f.pages[0]})"
        else:
            n = len(f.pages)
            where = f"template, on {'every page' if n == pages else f'{n} page' + ('s' if n > 1 else '')}"
            where += f" ({', '.join(f.pages[:3])}{', …' if n > 3 else ''})"
        print(f"warning: \n\tWhere: {where}\n\tWhat: {f.message} [{f.rule}]")
        print(f"fix: \n\t{f.fix}\n")
    rules = len({f.rule for f in findings})
    print(f"{len(findings)} warning(s) from {rules} rule(s)." if findings else "No accessibility problems found.")
    print("Static checks only: still look at mobile width and Wider spacing in the preview (reflow, overlap).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the built site for accessibility problems.")
    parser.add_argument("--out", type=Path, default=ROOT / "docs", help="built site to check (default: docs/)")
    parser.add_argument("--content", type=Path, default=ROOT / "content", help=argparse.SUPPRESS)
    parser.add_argument("--strict", action="store_true", help="exit with status 1 if anything is found")
    args = parser.parse_args()
    out, content = args.out.resolve(), args.content.resolve()
    if not (out / "index.html").is_file():
        raise SystemExit(f"  error: {out} has no index.html; build the site first (uv run src/build.py)")
    findings = check_site(out, content)
    report(findings, out, len(list(out.rglob("*.html"))))
    if args.strict and findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
