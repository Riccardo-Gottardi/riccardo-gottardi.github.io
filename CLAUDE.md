# Project guide: riccardo-gottardi.github.io

Personal site and blog. A small, home-made Python static site generator turns `content/` into
`docs/`, which GitHub Pages serves. The focus for now is the **blog**; the home page is only an intro
plus the latest posts.

- How to **write content** (folder taxonomy, front matter, `_index.md`): [README.md](README.md)
- The **visual system** (colours, graph language, type, layout, accessibility): [DESIGN.md](DESIGN.md)
- This file: stack, architecture, pipeline, conventions, decisions.

## Tech stack

| Layer | Choice |
| - | - |
| Language / env | Python ≥ 3.14, managed with **uv** (`pyproject.toml`, `uv.lock`, `.python-version`) |
| Templating | Jinja2 (autoescape on; `| safe` only for HTML the build rendered itself) |
| Markdown | mistune 3 with plugins `table, strikethrough, footnotes, task_lists, url, math`; raw HTML allowed |
| Highlighting | Pygments (`docs/assets/pygments.css` is generated) |
| Front matter | python-frontmatter + PyYAML |
| Fonts | Inter (variable, @fontsource-variable/inter 5.3.0, OFL) self-hosted in `static/fonts/inter/`; system monospace |
| Client libs (self-hosted in `static/vendor/`, only on pages that need them) | KaTeX 0.16.9 for math, Mermaid 11.17.2 (`mermaid.min.js`) for ```` ```mermaid ```` blocks. Pages contact no third-party server: keep it that way (copy a new library's files, with its LICENSE, from the npm tarball after checking its integrity hash) |
| JavaScript | none needed to read the site; `static/prefs.js` and a tiny inline `<head>` script handle the display preferences |
| Hosting | GitHub Pages from `main` branch, `/docs` folder (`docs/.nojekyll` is written by the build) |

No Node, no bundler, no framework. Keep it that way unless there is a strong reason.

## Architecture

```
content/                    source of truth (see README)
  site.yml                  name, tagline, theme, home.recent_posts, contact links
  home.md                   home intro
  blog/<macro>/[<category>/[<sub>/]]<post>.md | <post>/index.md
src/build.py                loads the tree, renders every page, copies static/, serve + watch
src/blog_graph.py           blog graph -> deterministic force layout -> inline SVG (normal + wide variants)
src/a11y.py                 accessibility checker of a built site (first piece of the publication pipeline)
src/speech.py               a post's HTML -> the text read aloud, and its recording's cache key
src/audio.py                records posts with Kokoro TTS (standalone uv script, Python <3.13), cache in audio/
static/listen.js            voice switch of the audio player: continues from the same point in the other voice
audio/                      <key>.mp3 recordings + manifest.json (lengths) + LICENSE (CC BY-NC-ND); committed, made once per text version
templates/                  base, home, section (every folder page), post, contact, 404, _macros, LICENSE.txt (-> docs/LICENSE)
static/style.css            layout, tokens, shared components, preferences, wider spacing
static/themes/graph.css     the look (selected by `theme:` in site.yml)
static/prefs.js             preference buttons (toggle or exclusive group), saved in localStorage
static/logos/               logo variants (green/red/blue/white)
static/fonts/inter/         Inter woff2 (latin, latin-ext) + OFL LICENSE
static/vendor/              KaTeX and Mermaid, each with its LICENSE (third-party, not MIT-licensed by us)
docs/                       GENERATED output, committed for GitHub Pages; wiped on every build
.preview/                   local preview output (gitignored)
```

The build in [src/build.py](src/build.py) runs these steps:
1. `load_section` walks `content/blog/` recursively into `Section` (folders, level 0–3) and `Post` objects. Titles, dates, summaries, order and colours are derived when the front matter omits them.
2. `check_urls` rejects collisions.
3. `link_posts` finds post-to-post links (the "links to" edges).
4. `add_graphs` stores two SVGs per folder.
5. The pages and `docs/LICENSE` (terms per part of the site + full CC BY-NC-ND and MIT texts) are rendered. Each post gets the recordings in `audio/` that match its current spoken text, one per voice, copied as `audio-<voice>.mp3`, and a player.

`BuildError` is for author mistakes: it carries a file path and a fix hint and stops the build with a clear message. Unknown front-matter keys are warnings.

## Development pipeline

```bash
uv run src/build.py --serve --drafts --out .preview   # local preview on http://127.0.0.1:8000, rebuilds on save
uv run src/build.py                                    # production build into docs/ (no drafts)
uv run src/a11y.py [--out .preview] [--strict]         # accessibility check of the built site
uv run src/audio.py [--drafts] [--prune]               # record new/changed posts (then rebuild)
```

1. Write or edit content. Mark unfinished posts `draft: true`.
2. Preview with the first command. In the Claude desktop app this is the `site` entry of `.claude/launch.json`.
   - The watcher reloads **content, templates and static** files, but **not Python code**. After editing `src/*.py`, restart the server.
3. Run the **plain build** (second command) before committing, so drafts never reach `docs/`.
4. Commit `content/` changes **and** the regenerated `docs/` together, then push to `main`. GitHub Pages publishes `docs/`.

Checks before committing:
- The build prints no `error:`, and every `warning:` is understood.
- `uv run src/a11y.py` prints no new `warning:`. It reads the built HTML/CSS (templates and content), points content problems to the `.md` line, and gives a `fix:` per rule. `--strict` exits 1 on any finding, for the future publication pipeline.
- Look at the changed pages in the preview: desktop, mobile (≤ 760px), and with **Wider spacing** on (the WCAG 1.4.12 check, see DESIGN.md §6).
- No horizontal page scroll.

There is no test suite yet. Error paths have been checked by hand with throwaway content copies (`--content <dir> --out <dir>`, hidden CLI options meant for exactly that).

## Conventions

- **Content structure:** folders only. Depth = level: macro → category → sub-category, maximum 3 levels. A folder is a series (ordered parts, prev/next) at level 3 or with `series: true` in its `_index.md`.
  - A folder with `index.md` is a post with its own files.
  - Number prefixes (`01-`) set the order and are stripped from URLs.
  - URLs mirror the tree, so moving a file changes its URL.
- **Colours:** set once per macro in `_index.md` (`color:`) and inherited. In templates, put `data-color` on any element that represents a post or folder.
- **CSS:** use tokens only (`--fg`, `--edge`, `--c-ink`, `--c-strong`, …); layout and structure go in `style.css`, appearance goes in the theme file. Every component must survive the wider-spacing preference.
- **Templates:** one `<h1>` per page; shared fragments go in `_macros.html`; folder pages all use `section.html`. Link files from `static/` with `{{ asset('style.css') }}`, never a bare `/assets/...` path: it adds a content hash (`?v=…`) so browsers never keep a stale copy.
- **Python:** standard library + the listed dependencies; dataclasses for the model; deterministic output (no randomness, so rebuilds don't create diffs).
- **Commits:** only when asked. End messages with the attribution line required by the session.

## Decision log

| Date | Decision | Why |
| - | - | - |
| 2026-11-16 | Blog taxonomy from **folders only** (front-matter `category:` dropped) | single source of truth, no tag typos, the tree is visible in the editor |
| 2026-11-16 | Dates fall back to the git creation date, then today | adding a post needs no front matter at all |
| 2026-11-16 | OpenDyslexic toggle replaced by a **Wider spacing** toggle | research shows no benefit from dyslexia fonts, some for spacing (DESIGN.md §6) |
| 2026-11-16 | Five themes compared live; **graph** + **network** merged into the final `graph` theme | the blog presented as a graph, matching the logo's flat style |
| 2026-11-16 | Colour per macro from the logo variants | ties sections to the identity |
| 2026-11-16 | Light mode only | owner's choice |
| 2026-11-16 | Graph laid out at build time (no JS), drawn twice (normal + wide spacing) | static, deterministic, readable in both spacing modes |
| 2026-11-16 | Single centred content column, maps included | content against the sidebar looked crowded |
| 2026-11-27 | Accessibility checker `src/a11y.py`, separate from the build, on the built output | first component of a build → check → publish pipeline; checking the output covers templates and content at once; static (no browser, no Node), so reflow stays a manual check |
| 2026-11-27 | Audio version: **Kokoro-82M** run locally at authoring time, MP3s cached by a hash of the spoken text and committed | natural voice (owner's priority) for free, offline, no API key; GitHub Pages can't run TTS, and caching keeps rebuilds deterministic |
| 2026-11-27 | Female and male voice, chosen by the reader (`audio: voices:`) | readers differ in which voice they find easier to follow; costs one recording per voice |
| 2026-11-27 | Dev server answers HTTP Range requests | Python's `http.server` doesn't, so browsers couldn't seek in the audio; GitHub Pages does |
| 2026-11-27 | Inter, KaTeX and Mermaid **self-hosted**, no CDN | loading Google Fonts sends visitors' IPs to Google without consent, which a German court held a GDPR breach (LG München I, 3 O 17493/20); the same reasoning covers other CDNs |
| 2026-11-27 | `series:` key in `_index.md` (default true only at level 3) | prev/next links for any folder, opt-in, without moving posts |

## Open items / ideas

- Content: `agents-usage.md` is a published two-line stub; the two spatial-perception posts are drafts; the home intro has small typos.
- Publication pipeline: build, then checks (conventions, `src/a11y.py --strict`, …), then publish. Only the accessibility checker exists so far.
- Possible: an `aliases:` front-matter key (redirect pages) if moving posts starts breaking links.
- Possible: optional `tags:` for cross-cutting links that don't change the structure.
- Possible: a wider lane for the graph view only, once the graph outgrows the column.
- Not used yet: `white-logo.svg`.
