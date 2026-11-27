# Design system

The visual rules of the site. The look is the **graph** theme: the blog presented as a graph
of nodes and edges, drawn in the flat, saturated style of the logo.

Where it lives: [static/style.css](static/style.css) holds the layout, the tokens and the shared components;
[static/themes/graph.css](static/themes/graph.css) holds the look (it overrides tokens and adds the graph decorations).
`content/site.yml` → `theme: graph` selects the theme file.

**Light mode only** (decided on 2026-11-16). There is no dark mode, so don't add `prefers-color-scheme` rules.

---

## 1. Identity and colour

### The logo

Six flat variants in [static/logos/](static/logos/), each a 250×250 square with a solid background and a monogram drawn in 10px round strokes:

| Variant | Background | Strokes | Used for |
| - | - | - | - |
| `green-logo.svg` | `#00ff00` | `#004500` | default: Home, Contact, Blog root, macros without a colour, favicon |
| `blue-logo.svg` | `#0400ff` | `#e9e9ff` | macros with `color: blue` (AI) |
| `red-logo.svg` | `#ff0000` | `#ffe8e8` | macros with `color: red` (Takes) |
| `violet-logo.svg` | `#8800ff` | `#f3e5ff` | macros with `color: violet` (none yet) |
| `yellow-logo.svg` | `#ffe600` | `#3c3600` | macros with `color: yellow` (none yet) |
| `white-logo.svg` | white | `#2c2c2c` | not used yet |

The sidebar logo always matches the colour of the current page.

### Colour per macro category

Each macro category picks one logo colour in its `_index.md` (`color: green | red | blue | violet | yellow`). Everything below it inherits that colour: its folder pages, its posts, its nodes and its list items, plus the logo, the active menu node, the view switch and the wider-spacing switch on those pages.

Technically, a `data-color` attribute (on `<body>` and on any list item or node) sets four tokens:

| Token | Green | Red | Blue | Violet | Yellow | Use it for |
| - | - | - | - | - | - | - |
| `--c-strong` | `#00ff00` | `#ff0000` | `#0400ff` | `#8800ff` | `#ffe600` | **fills only**: nodes, active pills, switch "on", timeline dots |
| `--c-on-strong` | `#004500` | `#200000` | `#e9e9ff` | `#f3e5ff` | `#3c3600` | text/knobs placed **on** a `--c-strong` fill |
| `--c-ink` | `#006b00` | `#c40000` | `#0400ff` | `#8800ff` | `#6b5f00` | **text**: links, trail labels, menu initials, focus outline |
| `--c-pale` | `#e6ffe6` | `#ffe8e8` | `#e9e9ff` | `#f3e5ff` | `#fff9cc` | backgrounds: folder nodes, hover, breadcrumbs, table headers |

Rules:
- **`--c-on-strong` must reach 4.5:1 on `--c-strong`.** It usually matches the logo strokes, except red: the logo's pale `#ffe8e8` strokes give only 3.42:1 on `#ff0000`, so the UI uses a dark red (`#200000`, 4.95:1), as green and yellow do.
- **Never use `--c-strong` for small text.** Pure `#00ff00` or `#ffe600` on white is nearly invisible. Text always uses `--c-ink`, which passes WCAG AA on white.
- To add another colour, add a logo variant, a `[data-color="…"]` rule in `style.css` and the name in `COLORS` in [src/build.py](src/build.py).

### Neutrals (graph theme)

| Token | Value | Use |
| - | - | - |
| `--bg` | `#ffffff` | page, sidebar, text backing |
| `--fg` / `--line` | `#151515` | text, every edge and border |
| `--muted` | `#555555` | secondary text, "links to" edges |
| dot grid | `#dcdcdc`, 1px dots every 22px | page background ("graph paper") |

---

## 2. The graph language

Everything that represents structure is drawn as a graph:

| Element | Drawn as |
| - | - |
| Edges | `2px solid #151515` (`--edge`), straight, no shadows |
| Round nodes | 14px circles (`--node-r: 7px`), 2px black outline, filled `--bg`, `--c-pale` or `--c-strong` |
| Folder nodes | pills (`border-radius: 999px`), 2px outline, `--c-pale` fill (`--c-strong` for the root) |
| Post nodes (leaves) | rectangles with a 2px **dashed** outline, white fill (solid outline on hover) |
| Canvases (graph frame) | square frame, 2px outline, white fill |

Where it's applied:
- **Menu (sidebar):** nodes on a vertical edge, with the current page's node filled `--c-strong`. On mobile the edge runs horizontally.
- **Breadcrumbs:** a chain of pills joined by short horizontal edges.
- **Post lists:** a timeline. A vertical edge runs down the list with one `--c-strong` dot per post (square dots in a series).
- **Folder pages:** a map with a **Folders | Graph** switch (graph by default, remembered per browser):
  - *Folders:* an indented tree. Pills for folders with post counts, dashed boxes for posts, elbow connectors.
  - *Graph:* a node-link drawing ([src/blog_graph.py](src/blog_graph.py)). Circle size shows the level (root 14, macro 11, category 9, sub 8, post 6 SVG units). The root and macros are filled `--c-strong`, other folders `--c-pale`, posts white, drafts dashed. Edges:
    - *contains*: solid.
    - *next part*: solid and slightly thicker, with an arrow.
    - *links to*: dashed, `--muted`, with an arrow.

    A legend under the canvas explains them (colour is never the only cue). Labels sit under the nodes, with a white halo (`paint-order: stroke`).
- **Text on the dot grid:** `.prose` and `.lead` get a white backing (`box-shadow: 0 0 0 .75rem var(--bg)`) so dots never sit behind running text.

---

## 3. Typography

| Role | Font | Details |
| - | - | - |
| Body | Inter 400 (self-hosted variable font, `static/fonts/inter/`) | 16px, line-height 1.65 |
| Headings | Inter 800 | tracking −0.02em, `text-wrap: balance` |
| Meta (dates, paths, labels, list headings, switch) | system monospace (`ui-monospace, SF Mono, Menlo, Consolas`) | 0.78rem; list headings uppercase, +0.06em tracking |
| Code | same monospace | 0.88rem |

Heading scale: h1 `clamp(2rem, 1.5rem + 2vw, 2.75rem)`, h2 1.5rem, h3 1.2rem, h4 1rem.
**One `<h1>` per page.** The page/post title is the h1, and the build shifts Markdown headings down one level (`#` → `<h2>`). Anchors keep the heading text (`## Reasons` → `#reasons`).

Post titles in lists: Inter 800, 1.25rem. Dates are formatted `16 Nov 2026`.

---

## 4. Layout

- **Sidebar** (desktop): fixed, 220px wide. From top to bottom: the logo square (links home), the menu, then the preferences pinned to the bottom. Separated from the content by a 2px edge.
- **Content:** a **single column, centred in the space right of the sidebar**. Its width is `--measure: 38rem`, about 70 characters per line. Everything goes in it: headers, intro, maps (both views), lists, posts and the footer. Keep it that way: content left-aligned against the sidebar looks crowded. If the graph ever outgrows the column, give only `.views` a wider lane centred on the same axis, rather than moving the column.
- **Vertical rhythm:** 2.5rem under page headers, 3rem above list headings, 5rem above the footer.
- **Mobile (≤ 760px):**
  - The sidebar becomes a top bar: a 64px logo plus the menu in a row.
  - The preferences get their own thin row under the bar.
  - The column takes the full width minus 1rem gutters.
  - The Folders/Graph switch is hidden and the folder tree is always shown, because graph labels would be too small.
- **Never** introduce horizontal page scroll. Wide tables and code scroll inside themselves.

---

## 5. Components

| Component | Where | Notes |
| - | - | - |
| Post item | `_macros.html` → `post_item` | date + trail (folders below the current page, in `--c-ink`), title, summary; `data-color` of its macro |
| Breadcrumbs | `_macros.html` → `breadcrumbs` | each pill carries its folder's colour |
| Folder tree | `_macros.html` → `blog_map` | recursive; posts as leaves |
| Graph canvas | `section.html` + `blog_graph.py` | two SVGs (normal and wide spacing) + legend |
| View switch | `section.html` | segmented pill, exclusive buttons, `aria-pressed` |
| Audio player | `post.html` + `listen.js` | a voice switch (same pill as the view switch, also on mobile, remembered as `pref-voice`), then one native `<audio controls>` per voice with only the chosen one shown; caption with the length, "synthetic voice", MP3 downloads. Switching voice continues from the same point. Only voices with a recording are offered |
| Series navigation | `post.html` | "Part n of m" in the meta; previous/next pills at the end |
| Draft badge | `.draft` | `--c-strong` fill, uppercase mono; only visible in `--drafts` builds |
| Preferences | `base.html` sidebar + `prefs.js` | see §6 |
| Skip link | `base.html`, first element of `<body>` | "Skip to content" → `<main id="content">`; off-screen until focused, then a white pill over the logo |

---

## 6. Accessibility rules

Decisions here are evidence-based. Keep them that way: check the research before adding "accessibility" features.

- **Contrast:** body text `#151515` on white; secondary `#555`; coloured text only in `--c-ink` (AA). Saturated logo colours are fills only.
- **Wider spacing preference** (sidebar switch): applies the [WCAG 2.2 SC 1.4.12](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html) values:
  - letter spacing 0.12em, word spacing 0.16em, line height 1.9, paragraph spacing 2em;
  - set on every element so `em` follows each element's own size;
  - code, Mermaid, KaTeX and graph SVGs are excluded, except that the graph has its own **wide variant**: a separate layout with wider label boxes.
  - Letter and word spacing must grow **together**: extra letter spacing alone slows reading ([Galliussi et al., 2020](https://doi.org/10.1007/s11881-020-00194-x)), while larger spacing can help readers with dyslexia ([Zorzi et al., 2012](https://doi.org/10.1073/pnas.1205566109)).
  - Turning it on is also a live test of SC 1.4.12: nothing may clip or overlap.
- **No dyslexia fonts.** OpenDyslexic was tried and removed. The controlled studies found no benefit for OpenDyslexic ([Wery & Diliberto, 2017](https://doi.org/10.1007/s11881-016-0127-1)) or Dyslexie ([Kuster et al., 2018](https://doi.org/10.1007/s11881-017-0154-6)), and [Dyslexia Scotland](https://dyslexiascotland.org.uk/dyslexia-friendly-typed-formats) notes spacing matters more than typeface.
- **Switch styling:** black when off; when on, filled `--c-strong` with a `--c-on-strong` knob and a black outline.
- **Controls:** real `<button>`s with visible text labels (no `title` tooltips as names) and `aria-pressed` state; `:focus-visible` outline 2px `--c-ink`.
- **Graph:** each node is a link with a `<title>` (full title, "(draft)" when relevant); the legend names every edge style; the post list below always repeats the content in text.
- **Audio version** of every post (synthetic voice, read by Kokoro; see README). Text-to-speech has a small to moderate benefit on reading comprehension for readers with reading disabilities ([Wood et al., 2018](https://www.sciencegate.app/document/10.1177/0022219416688170)). It uses the native `<audio>` player (keyboard and screen-reader accessible, speed control, no JS), never autoplays, and says the voice is synthetic. The page text is the transcript, so no captions are needed.
- **Text size** follows the reader's browser setting (`html { font-size: 100% }`, all sizes in `rem`/`em`).
- **Skip link** as the first Tab stop on every page.
- **Line length** ≤ about 70 characters; **one h1** per page; headings in order.
- **Checked automatically** by [src/a11y.py](src/a11y.py) on the built site: language, titles, landmarks, skip link, headings, ids and anchors, link and button names, image alt text, Mermaid `accTitle`/`accDescr`, SVG names, table headers, media captions, and the colour tokens above (contrast of every `data-color` pair, `--c-strong` never used for text, focus outline never removed). Add a rule there when you add a rule here.

---

## 7. Adding things

- **A new preference:** a button in `base.html` with `data-pref`/`data-value` (add `data-exclusive` and `data-default` for a group of exclusive options), plus `:root[data-<pref>="<value>"]` rules in CSS. `prefs.js` and the inline `<head>` script handle saving and applying with no changes. Values live in `localStorage` as `pref-<name>`.
- **A new component:** use the tokens (`--edge`, `--c-*`, `--font-meta`, …), never raw colours, so macro colours keep working.
- **A new colour:** see §1.
