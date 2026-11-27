"""Static site generator for riccardo-gottardi.github.io.

    content/  +  templates/  +  static/   ->   docs/   (served by GitHub Pages)

The blog is organised by the folder tree of content/blog/ only:

    content/blog/<macro>/                           level 1: macro category
    content/blog/<macro>/<category>/                level 2: category
    content/blog/<macro>/<category>/<sub>/          level 3: sub category (a series by default)
    <any level>/<post>.md                           a post
    <any level>/<post>/index.md (+ images)          a post with its own files
    <any folder>/_index.md                          optional title/description/order/color/series

Every folder becomes a page, URLs mirror the tree, numeric prefixes ("01-")
only set the order. See README.md for the authoring workflow.

Run with:  uv run src/build.py [--serve] [--drafts]
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import functools
import hashlib
import html as html_lib
import http.server
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter
import mistune
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

import blog_graph
import speech

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
LICENSE_SEPARATOR = "-" * 71  # in content/LICENSE: the notice above it, the license text below
AUDIO = ROOT / "audio"  # recordings made by src/audio.py: <key>.mp3 + manifest.json

MAX_DEPTH = 3  # macro / category / sub category
SERIES_LEVEL = 3  # folders at this level are a series by default; `series:` in _index.md overrides it
POST_KEYS = {"title", "date", "summary", "order", "draft"}
INDEX_KEYS = {"title", "description", "order", "color", "series"}
COLORS = {"green", "red", "blue", "violet", "yellow"}  # the logo variants in static/logos/
DEFAULT_COLOR = "green"
ORDER_PREFIX = re.compile(r"^(\d+)[-_ ]+(.+)$")
LEADING_H1 = re.compile(r"\A\s*#[ \t]+(.+?)[ \t#]*(?:\n|\Z)")


class BuildError(Exception):
    """A problem in the content that the author has to fix."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def warn(path: Path, msg: str) -> None:
    print(f"  warning: {rel(path)}: {msg}")


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_order(name: str) -> tuple[int | None, str]:
    """'01-intro' -> (1, 'intro');  'intro' -> (None, 'intro')."""
    m = ORDER_PREFIX.match(name)
    return (int(m[1]), m[2]) if m else (None, name)


def humanize(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().capitalize()


# ---------------------------------------------------------------- markdown


class Renderer(mistune.HTMLRenderer):
    """Adds heading ids (for #anchors), Pygments highlighting and Mermaid blocks."""

    def __init__(self) -> None:
        super().__init__(escape=False)  # your own content: raw HTML allowed
        self._ids: dict[str, int] = {}

    def heading(self, text: str, level: int, **attrs) -> str:
        level = min(level + 1, 6)  # the page title is the only <h1>: "# X" in markdown -> <h2>
        base = slugify(re.sub(r"<[^>]+>", "", text)) or "section"
        n = self._ids.get(base, 0)
        self._ids[base] = n + 1
        anchor = base if n == 0 else f"{base}-{n}"
        return f'<h{level} id="{anchor}">{text}</h{level}>\n'

    def block_code(self, code: str, info: str | None = None) -> str:
        lang = info.split(None, 1)[0] if info else ""
        if lang == "mermaid":
            return f'<pre class="mermaid">{html_lib.escape(code)}</pre>\n'
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            return super().block_code(code, info)
        return highlight(code, lexer, HtmlFormatter(cssclass="highlight"))


def render_markdown(text: str) -> str:
    md = mistune.create_markdown(
        renderer=Renderer(),
        plugins=["table", "strikethrough", "footnotes", "task_lists", "url", "math"],
    )
    return md(text)


# Citations: a paragraph under a "References" heading that starts with "[Key]" is an entry;
# a "[Key]" in the text before it becomes a link to that entry, and the entry links back.
REF_HEADING = re.compile(r'<h[2-6] id="(?:references|bibliography)">.*?</h[2-6]>\n?')
REF_ENTRY = re.compile(r"<p>\[([A-Za-z][\w+.-]*)\](?=\s)(.*?)</p>", re.S)
CITE_KEY = re.compile(r"\[([A-Za-z][\w+.-]*)\]")
LOOKS_LIKE_CITE = re.compile(r"[A-Z][A-Za-z]*\+?\d{2}")  # alphabetic style: Hof25, Bai+22, ZZ24
# text that must not get links: tags, code, existing links, math
NO_CITE = re.compile(r'<(pre|code|a)\b.*?</\1>|<(span|div) class="math">.*?</\2>|<[^>]+>', re.S)


def link_citations(html: str, src: Path) -> str:
    m = REF_HEADING.search(html)
    if not m:
        return html
    body, refs = html[:m.end()], html[m.end():]
    ids: dict[str, str] = {}
    for e in REF_ENTRY.finditer(refs):
        key = e[1]
        if key in ids:
            raise BuildError(f"{rel(src)}: reference [{key}] is listed twice; keep one entry per key")
        ids[key] = "ref-" + slugify(key)
    if not ids:
        return html

    cites: dict[str, list[str]] = {}

    def cite(c: re.Match) -> str:
        key = c[1]
        if key not in ids:
            if LOOKS_LIKE_CITE.fullmatch(key):
                warn(src, f"[{key}] looks like a citation but has no entry under References")
            return c[0]
        back = f"cite-{slugify(key)}-{len(cites.setdefault(key, [])) + 1}"
        cites[key].append(back)
        return f'<a class="cite" id="{back}" href="#{ids[key]}">[{key}]</a>'

    out, pos = [], 0
    for skip in NO_CITE.finditer(body):
        out += [CITE_KEY.sub(cite, body[pos:skip.start()]), skip[0]]
        pos = skip.end()
    out.append(CITE_KEY.sub(cite, body[pos:]))

    def entry(e: re.Match) -> str:
        key = e[1]
        backs = cites.get(key, [])
        if not backs:
            warn(src, f"reference [{key}] is never cited in the text")
        links = "".join(
            f' <a class="cite-back" href="#{b}" aria-label="Back to citation {i}">↩{"" if i == 1 else i}</a>'
            for i, b in enumerate(backs, 1)
        )
        return f'<p class="ref" id="{ids[key]}">[{key}]{e[2]}{links}</p>'

    return "".join(out) + REF_ENTRY.sub(entry, refs)


def first_paragraph(html: str, limit: int = 220) -> str:
    m = re.search(r"<p>(.*?)</p>", html, re.S)
    if not m:
        return ""
    text = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", "", m[1])).split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


# ---------------------------------------------------------------- content


def load_doc(path: Path, allowed: set[str]) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    try:
        doc = frontmatter.loads(text)
    except yaml.YAMLError as e:
        raise BuildError(f"{rel(path)}: invalid front matter: {e}") from e
    if not doc.metadata and re.match(r"(%s)\s*:" % "|".join(allowed), text):
        raise BuildError(f"{rel(path)}: front matter must start with a '---' line")
    for key in sorted(set(doc.metadata) - allowed):
        warn(path, f"unknown front-matter key {key!r} (known: {', '.join(sorted(allowed))})")
    return dict(doc.metadata), doc.content


def parse_date(value, path: Path) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise BuildError(f"{rel(path)}: date must be YYYY-MM-DD, got {value!r}") from None


def git_created(path: Path) -> dt.date | None:
    """Date of the commit that first added the file (following renames)."""
    try:
        out = subprocess.run(
            ["git", "log", "--follow", "--diff-filter=A", "--format=%as", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return None
    return dt.date.fromisoformat(out[-1]) if out else None


@dataclass(eq=False)
class Section:
    """A folder of content/blog/. Level 0 is the blog itself."""

    key: str
    title: str
    description: str
    html: str
    order: int | None
    url: str
    level: int
    parent: Section | None = None
    color: str = DEFAULT_COLOR  # set in a macro's _index.md, inherited by everything below
    is_series: bool = False  # direct posts are ordered parts with prev/next links (`series:` in _index.md)
    children: list[Section] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)  # posts directly in this folder
    all_posts: list[Post] = field(default_factory=list)  # this folder and below, newest first
    graph_svg: str = ""  # node-link drawing of this folder and below
    graph_svg_wide: str = ""  # the same, laid out for the "Wider spacing" preference
    source: Path | None = None  # the folder's _index.md, if it has one

    @property
    def ancestors(self) -> list[Section]:
        chain, s = [], self.parent
        while s is not None:
            chain.insert(0, s)
            s = s.parent
        return chain


@dataclass(eq=False)
class Post:
    source: Path
    slug: str
    title: str
    date: dt.date
    summary: str
    html: str
    section: Section
    order: int | None
    draft: bool
    bundle: Path | None  # folder whose other files are copied next to the post
    links_to: list[Post] = field(default_factory=list)  # other posts linked from the text
    prev: Post | None = None
    next: Post | None = None
    audio: list[dict] = field(default_factory=list)  # recordings next to the post: {id, label, file, minutes}

    @property
    def url(self) -> str:
        return f"{self.section.url}{self.slug}/"

    @property
    def breadcrumbs(self) -> list[Section]:
        return [*self.section.ancestors, self.section]

    def path_below(self, section: Section | None) -> list[Section]:
        """Folders between `section` (exclusive) and the post, for list items."""
        level = section.level if section else 0
        return [s for s in self.breadcrumbs if s.level > level]

    @property
    def part(self) -> int:
        return self.section.posts.index(self) + 1

    @property
    def color(self) -> str:
        return self.section.color

    @property
    def has_math(self) -> bool:
        return 'class="math' in self.html

    @property
    def has_mermaid(self) -> bool:
        return 'class="mermaid"' in self.html


def is_post(path: Path) -> bool:
    return (path.is_file() and path.suffix == ".md") or (path.is_dir() and (path / "index.md").is_file())


def entries(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if not p.name.startswith((".", "_")))


def load_post(path: Path, section: Section, drafts: bool) -> Post | None:
    bundle = path if path.is_dir() else None
    src = path / "index.md" if bundle else path
    meta, body = load_doc(src, POST_KEYS)
    if meta.get("draft") and not drafts:
        return None
    prefix, name = split_order(path.name if bundle else path.stem)
    title = meta.get("title")
    if not title:
        m = LEADING_H1.match(body)
        if m:
            title, body = m[1], body[m.end():]
        else:
            title = humanize(name)
    date = parse_date(meta["date"], src) if meta.get("date") else (git_created(src) or dt.date.today())
    html = link_citations(render_markdown(body), src)
    return Post(
        source=src, slug=slugify(name), title=str(title), date=date,
        summary=str(meta.get("summary") or first_paragraph(html)), html=html,
        section=section, order=meta.get("order", prefix), draft=bool(meta.get("draft")),
        bundle=bundle,
    )


def load_section(folder: Path, parent: Section | None, drafts: bool, title: str = "") -> Section:
    prefix, name = split_order(folder.name)
    meta, body = load_doc(folder / "_index.md", INDEX_KEYS) if (folder / "_index.md").is_file() else ({}, "")
    level = parent.level + 1 if parent else 0
    key = slugify(name)
    color = meta.get("color") or (parent.color if parent else DEFAULT_COLOR)
    if color not in COLORS:
        raise BuildError(f"{rel(folder / '_index.md')}: color must be one of {', '.join(sorted(COLORS))}, got {color!r}")
    series = meta.get("series", level == SERIES_LEVEL)
    if not isinstance(series, bool):
        raise BuildError(f"{rel(folder / '_index.md')}: series must be true or false, got {series!r}")
    section = Section(
        key=key, title=str(meta.get("title") or title or humanize(name)),
        description=str(meta.get("description", "")),
        html=render_markdown(body) if body.strip() else "",
        order=meta.get("order", prefix), level=level, parent=parent,
        url=f"{parent.url}{key}/" if parent else "/blog/", color=color, is_series=series,
        source=folder / "_index.md" if (folder / "_index.md").is_file() else None,
    )
    for entry in entries(folder):
        if is_post(entry):
            if level == 0:
                raise BuildError(f"{rel(entry)}: posts must live inside a macro category folder, e.g. content/blog/ai/{entry.name}")
            post = load_post(entry, section, drafts)
            if post:
                section.posts.append(post)
        elif entry.is_dir():
            if level == MAX_DEPTH:
                raise BuildError(f"{rel(entry)}: too deep, the blog has {MAX_DEPTH} levels (macro/category/sub). "
                                 "For a post with images, put an index.md inside the folder.")
            child = load_section(entry, section, drafts)
            if child.all_posts:  # empty folders are skipped
                section.children.append(child)
        elif entry.suffix != ".md":
            warn(entry, "ignored: files other than posts only belong inside a post folder (<post>/index.md)")

    if section.is_series:
        section.posts.sort(key=lambda p: (p.order is None, p.order or 0, p.date, p.title.lower()))
        for a, b in zip(section.posts, section.posts[1:]):
            a.next, b.prev = b, a
    else:
        section.posts.sort(key=lambda p: p.date, reverse=True)
    section.children.sort(key=lambda s: (s.order is None, s.order or 0, s.title.lower()))
    section.all_posts = sorted(
        [*section.posts, *(p for c in section.children for p in c.all_posts)],
        key=lambda p: p.date, reverse=True,
    )
    return section


LINK = re.compile(r'href="(/blog/[^"#?]*)')


def link_posts(posts: list[Post]) -> None:
    """Record which posts link to which other posts (edges of the blog graph)."""
    by_url = {p.url: p for p in posts}
    for p in posts:
        for href in LINK.findall(p.html):
            target = by_url.get(href if href.endswith("/") else href + "/")
            if target and target is not p and target not in p.links_to:
                p.links_to.append(target)


def add_graphs(section: Section) -> None:
    section.graph_svg = blog_graph.svg_for(section)
    section.graph_svg_wide = blog_graph.svg_for(section, wide=True)
    for c in section.children:
        add_graphs(c)


def check_urls(blog: Section) -> None:
    seen: dict[str, Path | str] = {}

    def claim(url: str, what: Path | str) -> None:
        if url in seen:
            raise BuildError(f"{rel(what) if isinstance(what, Path) else what} and "
                             f"{rel(seen[url]) if isinstance(seen[url], Path) else seen[url]} both map to {url}")
        seen[url] = what

    def walk(s: Section) -> None:
        claim(s.url, f"folder {s.title!r}")
        for p in s.posts:
            claim(p.url, p.source)
        for c in s.children:
            walk(c)

    walk(blog)


# ---------------------------------------------------------------- build


@dataclass(frozen=True)
class Voice:
    id: str  # from the label, e.g. "female": the reader's choice is saved under this name
    label: str  # shown on the voice switch, e.g. "Female"
    voice: str  # Kokoro voice, e.g. af_heart
    speed: float


def audio_voices(site: dict) -> list[Voice]:
    """The voices of the `audio:` block of site.yml, the default first; empty when audio is off."""
    cfg = site.get("audio")
    if not cfg:
        return []
    hint = ("content/site.yml: `audio:` needs a list of `voices:`, each with `label:` and `voice:` "
            "(e.g. `- {label: Female, voice: af_heart}`), and optionally `speed:` (e.g. 1.0)")
    speed, entries = cfg.get("speed", 1.0), cfg.get("voices")
    if not isinstance(speed, (int, float)) or not isinstance(entries, list) or not entries:
        raise BuildError(hint)
    voices = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("label"), str) or not isinstance(e.get("voice"), str):
            raise BuildError(hint)
        voices.append(Voice(slugify(e["label"]), e["label"], e["voice"], float(speed)))
    if len({v.id for v in voices}) < len(voices):
        raise BuildError("content/site.yml: two `audio:` voices have the same label; give each its own")
    return voices


def content_license(site: dict) -> dict:
    """`content_license:` of site.yml (posts and their audio): {name, url}."""
    lic = site.get("content_license")
    if not isinstance(lic, dict) or not all(isinstance(lic.get(k), str) for k in ("name", "url")):
        raise BuildError("content/site.yml: `content_license:` needs `name:` (e.g. CC BY-NC-ND 4.0) and `url:`")
    return lic


def speech_jobs(content: Path, drafts: bool) -> list[dict]:
    """What src/audio.py must record: one entry per post and voice, with the spoken text and cache key."""
    site = yaml.safe_load((content / "site.yml").read_text(encoding="utf-8"))
    voices = audio_voices(site)
    if not voices:
        raise BuildError("content/site.yml: no `audio:` block, so there is nothing to record")
    lic = content_license(site)
    jobs = []
    for p in load_section(content / "blog", None, drafts, title="Blog").all_posts:
        text = speech.spoken_text(p.title, p.html)
        page = f"{str(site.get('url', '')).rstrip('/')}{p.url}"
        for v in voices:
            # ID3 tags: they travel with a downloaded file, away from the page and its footer
            tags = {
                "title": p.title,
                "artist": site["name"],
                "date": str(p.date.year),
                "copyright": f"© {p.date.year} {site['name']}, {lic['name']}",
                "LICENSE": lic["url"],
                "comment": f"Audio version of {page}, read by a synthetic voice (Kokoro, {v.voice}). "
                           f"License: {lic['name']}, {lic['url']}",
            }
            jobs.append({"key": speech.audio_key(text, v.voice, v.speed), "voice": v.voice, "speed": v.speed,
                         "source": rel(p.source), "url": p.url, "text": text, "tags": tags})
    return jobs


def build(content: Path, out: Path, drafts: bool = False) -> None:
    site = yaml.safe_load((content / "site.yml").read_text(encoding="utf-8"))
    content_license(site)  # the footer needs it
    blog = load_section(content / "blog", None, drafts, title="Blog")
    check_urls(blog)
    link_posts(blog.all_posts)
    add_graphs(blog)
    posts = blog.all_posts
    intro = ""
    if (content / "home.md").is_file():
        intro = render_markdown(load_doc(content / "home.md", set())[1])

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out / "assets")
    (out / "assets" / "pygments.css").write_text(HtmlFormatter(style="default").get_style_defs(".highlight"))
    (out / ".nojekyll").touch()

    def asset(path: str) -> str:
        """URL of a file in assets/, versioned by its content so browsers never keep a stale copy."""
        file = out / "assets" / path
        if not file.is_file():
            raise BuildError(f"templates: asset {path!r} not found in static/ (check the path in the template)")
        return f"/assets/{path}?v={hashlib.sha256(file.read_bytes()).hexdigest()[:8]}"

    env.globals["asset"] = asset

    def render(template: str, url: str, **ctx) -> None:
        target = out / url.strip("/") / "index.html" if url.endswith("/") else out / url
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(site=site, **ctx), encoding="utf-8")

    recent = site.get("home", {}).get("recent_posts", 3)
    render("home.html", "/", active="home", intro=intro, posts=posts[:recent])
    render("contact.html", "/contact/", active="contact")
    render("404.html", "404.html", active="")

    # docs/ is wiped on every build, so its license notice is generated too (the logo's own
    # LICENSE arrives with static/). Full texts: content/LICENSE (posts, audio) and LICENSE (MIT).
    texts = {}
    for name, path in (("content_license_text", content / "LICENSE"), ("mit_text", ROOT / "LICENSE")):
        if not path.is_file():
            raise BuildError(f"{rel(path)}: missing; the published site's LICENSE includes its text")
        text = path.read_text(encoding="utf-8")
        # content/LICENSE starts with a notice (scope, third-party material) that docs/LICENSE
        # words for itself: keep only the license text after the dashed separator line
        _, sep, after = text.partition(f"\n{LICENSE_SEPARATOR}\n")
        texts[name] = (after if sep else text).strip()
    # assets/pygments.css is generated from Pygments' "default" style: its BSD license goes along
    pyg = importlib.metadata.distribution("pygments")
    texts["pygments_version"] = pyg.version
    texts["pygments_text"] = (pyg.read_text("licenses/LICENSE") or pyg.read_text("LICENSE") or "").strip()
    if not texts["pygments_text"]:
        raise BuildError("the installed Pygments has no LICENSE file; docs/LICENSE must include it (reinstall: uv sync)")
    render("LICENSE.txt", "LICENSE", **texts)

    voices = audio_voices(site)
    manifest = json.loads((AUDIO / "manifest.json").read_text()) if (AUDIO / "manifest.json").is_file() else {}
    missing: list[Post] = []

    def attach_audio(p: Post) -> None:
        """Copy the post's recordings next to it, those src/audio.py has made for its current text."""
        text = speech.spoken_text(p.title, p.html) if voices else ""
        for v in voices:
            key = speech.audio_key(text, v.voice, v.speed)
            mp3 = AUDIO / f"{key}.mp3"
            if not mp3.is_file():
                if p not in missing:
                    missing.append(p)
                continue
            file = f"audio-{v.id}.mp3"
            dest = out / p.url.strip("/") / file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mp3, dest)
            minutes = max(1, round(manifest.get(key, {}).get("seconds", 60) / 60))
            p.audio.append({"id": v.id, "label": v.label, "file": file, "minutes": minutes})

    def render_section(s: Section) -> None:
        render("section.html", s.url, active="blog", section=s, color=s.color)
        for p in s.posts:
            attach_audio(p)
            render("post.html", p.url, active="blog", post=p, color=p.color)
            if p.bundle:
                for f in p.bundle.rglob("*"):
                    if f.is_file() and f.name != "index.md" and not f.name.startswith("."):
                        dest = out / p.url.strip("/") / f.relative_to(p.bundle)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, dest)
        for c in s.children:
            render_section(c)

    render_section(blog)
    n_drafts = sum(p.draft for p in posts)
    if missing:
        print(f"  note: {len(missing)} post(s) without an up-to-date recording (missing voices are not offered); "
              f"run `uv run src/audio.py{' --drafts' if drafts else ''}` to record them")
    print(f"Built {len(posts)} post(s){f' incl. {n_drafts} draft(s)' if n_drafts else ''} -> {rel(out)}/")


def safe_build(content: Path, out: Path, drafts: bool) -> bool:
    try:
        build(content, out, drafts)
        return True
    except BuildError as e:
        print(f"  error: {e}")
    except Exception as e:  # template errors etc.; keep the dev server alive
        print(f"  error: {type(e).__name__}: {e}")
    return False


def watch(rebuild, folders: list[Path]) -> None:
    def snapshot() -> dict[Path, int]:
        return {p: p.stat().st_mtime_ns for f in folders for p in f.rglob("*") if p.is_file()}

    last = snapshot()
    while True:
        time.sleep(1)
        now = snapshot()
        if now != last:
            last = now
            print("Change detected, rebuilding…")
            rebuild()


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """Adds HTTP Range requests (206 Partial Content), like GitHub Pages: without them browsers
    can't seek in the audio player (clicks on the track and arrow keys jump back to 0:00)."""

    RANGE = re.compile(r"bytes=(\d*)-(\d*)$")

    def send_head(self):
        m = self.RANGE.match(self.headers.get("Range", "").strip())
        path = Path(self.translate_path(self.path))
        if not m or not path.is_file() or m[0] == "bytes=-":
            return super().send_head()
        size = path.stat().st_size
        if m[1]:
            start, end = int(m[1]), min(int(m[2]) if m[2] else size - 1, size - 1)
        else:  # "bytes=-N": the last N bytes
            start, end = max(size - int(m[2]), 0), size - 1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        f = path.open("rb")
        f.seek(start)
        self._remaining = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(self._remaining))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        self._remaining = None
        while remaining > 0 and (chunk := source.read(min(64 * 1024, remaining))):
            outputfile.write(chunk)
            remaining -= len(chunk)

    def end_headers(self):
        if not self.headers.get("Range"):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


def serve(out: Path, port: int) -> None:
    handler = functools.partial(RangeHandler, directory=out)
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving http://127.0.0.1:{port}  (rebuilds on change, Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static site into docs/.")
    parser.add_argument("--serve", action="store_true", help="serve locally and rebuild on every change")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--drafts", action="store_true", help="include posts with 'draft: true'")
    parser.add_argument("--content", type=Path, default=ROOT / "content", help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, default=ROOT / "docs", help=argparse.SUPPRESS)
    parser.add_argument("--speech", action="store_true", help=argparse.SUPPRESS)  # JSON for src/audio.py
    args = parser.parse_args()
    content, out = args.content.resolve(), args.out.resolve()

    if args.speech:
        try:
            with contextlib.redirect_stdout(sys.stderr):  # warnings must not end up in the JSON
                jobs = speech_jobs(content, args.drafts)
            print(json.dumps(jobs, ensure_ascii=False))
        except BuildError as e:
            raise SystemExit(f"error: {e}")
        return

    ok = safe_build(content, out, args.drafts)
    if args.serve:
        rebuild = functools.partial(safe_build, content, out, args.drafts)
        threading.Thread(target=watch, args=(rebuild, [content, TEMPLATES, STATIC]), daemon=True).start()
        serve(out, args.port)
    elif not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
