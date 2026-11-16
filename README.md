# riccardo-gottardi.github.io

My personal site and blog, built by a small Python static site generator
([src/build.py](src/build.py)) into `docs/`, which GitHub Pages serves.

This file is the guide to **writing content**. See also [DESIGN.md](DESIGN.md) for the visual rules and
[CLAUDE.md](CLAUDE.md) for the tech stack, the development pipeline, conventions and past decisions.

## Commands

```bash
uv run src/build.py                     # build into docs/
uv run src/build.py --serve             # build, serve on http://127.0.0.1:8000, rebuild on every change
uv run src/build.py --serve --drafts --out .preview   # preview with drafts, without touching docs/
```

Don't commit a `docs/` built with `--drafts`: run a plain build before committing.

## Where things live

| Path | What it is |
| - | - |
| `content/home.md` | Home page introduction |
| `content/site.yml` | Site name, tagline, contact links, number of recent posts on the home page |
| `content/blog/` | The blog: folder tree = structure (see below) |
| `templates/` | Jinja2 templates |
| `static/` | `style.css` (layout), `themes/graph.css` (look), `prefs.js`, logos: copied to `docs/assets/` |

## Writing for the blog

The folder tree of `content/blog/` **is** the blog structure. Each level of nesting is a level of the hierarchy:

```
content/blog/
  ai/                              level 1: macro category      -> /blog/ai/
    _index.md                      optional folder settings
    agentic-ai/                    level 2: category            -> /blog/ai/agentic-ai/
      agents-usage.md              a post                       -> /blog/ai/agentic-ai/agents-usage/
    computer-vision/
      spatial-perception/          level 3: sub category (series)
        01-intro.md                part 1                       -> /blog/ai/computer-vision/spatial-perception/intro/
        02-project-definition.md   part 2
        03-results/                a post with its own files
          index.md
          plot.png                 referenced as ![](plot.png)
  takes/
    vibe-coding.md                 posts can sit at any level
```

- **Every folder becomes a page** that lists every post below it, newest first.
  At the top it has a map with a **Folders | Graph** switch: the folder tree, or a node-link graph
  (drawn at build time by [src/blog_graph.py](src/blog_graph.py)) whose edges are *contains*, *next part* of a series,
  and *links to* (any link in a post's text to another post).
- **Level 3 folders are series**: their posts are listed in order and get "Part 2 of 3" and previous/next links.
- **Max 3 levels.** A deeper folder is an error, unless it contains an `index.md`, which makes it a post.
- **Ordering**: a number prefix (`01-`, `02-`) sets the order of posts and folders and is removed from the URL.
  Without one, series are ordered by date and folders alphabetically.
- **Empty folders are ignored**, so you can create the structure before writing.
- **Moving a file changes its URL.**

### A post with images

A post is either a single `.md` file, or a folder containing `index.md` plus the post's files (images, data…).
The folder's name is the post's name, and its files are published next to the post, so `![](plot.png)` works.
The `index.md` is what tells the build that the folder is a post and not a category.

### Front matter (all optional)

```yaml
---
title: How I use AI agents   # default: first "# Heading" of the text, else the file name
date: 2026-11-16             # default: date the file was first committed, today if not committed yet
summary: One sentence.       # default: first paragraph (used in lists and as the page description)
order: 2                     # default: number prefix of the file name
draft: true                  # hidden unless you build with --drafts
---
```

The front matter needs both `---` lines. Without the first one the build stops with an error.

### Folder settings: `_index.md` (optional)

```yaml
---
title: AI                   # default: folder name, "computer-vision" -> "Computer vision"
description: One sentence.  # shown under the folder page's title
order: 1                    # default: number prefix of the folder name
color: blue                 # green | red | blue (the logo variants), inherited by everything below; default green
---
Optional intro text shown on the folder's page.
```

You only need it when the automatic name is wrong (acronyms like "AI"), or to add a description.

### Markdown extras

Tables, footnotes, task lists, `$$ math $$` (KaTeX), fenced code with syntax highlighting,
```` ```mermaid ```` diagrams, and `#anchor` links to any heading (`## Reasons` -> `#reasons`).

## License

This repository holds work under three different terms:

| What | Terms |
| - | - |
| The site generator and templates: `src/`, `templates/`, `static/` (except `static/logos/`), and the config files | [MIT License](LICENSE) |
| The logo and its variants: `static/logos/`, and their copies under `docs/assets/logos/` | © 2026 Riccardo Gottardi, all rights reserved ([details](static/logos/LICENSE)) |
| The written content: `content/`, and the pages generated from it in `docs/` (except the logo) | © 2026 Riccardo Gottardi, [CC BY-NC-ND 4.0](content/LICENSE) |
| Code snippets inside the posts | [MIT License](LICENSE) |

The MIT License does **not** cover the logo or the written content.

Quotations and other material by third parties, in the posts, remain under their authors' terms: the licenses
above cover only what I wrote.

- **Logo:** you may not copy, modify, or redistribute it without written permission ([terms](static/logos/LICENSE)).
- **Posts:** you may share them unchanged, for non-commercial purposes, if you credit the author and link to the
  [license](https://creativecommons.org/licenses/by-nc-nd/4.0/). Modified versions, translations included, and
  commercial use need written permission.
- **Code snippets** in the posts may be reused under the [MIT License](LICENSE).
