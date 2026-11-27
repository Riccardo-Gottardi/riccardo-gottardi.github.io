"""The blog as a node-link graph, laid out at build time and drawn as inline SVG.

Nodes are folders (root, macro, category, sub category) and posts. Edges:
    contains   folder -> what is inside it
    next       part n -> part n+1 of a series (directed)
    link       post -> post it links to in its text (directed)

The layout is deterministic (no randomness): a radial tree as the starting point,
then a force-directed refinement (Fruchterman & Reingold, 1991) that also keeps
labels apart. Colours and strokes come from the theme CSS.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

FONT = 12.5                 # label font size in SVG units
CHAR_W = 0.6 * FONT         # rough average character width, for label boxes
# "Wider spacing" preference (WCAG 1.4.12 values), applied to labels in the wide variant
WIDE_LETTER = 0.12 * FONT
WIDE_WORD = 0.16 * FONT
MAX_LABEL = 26              # longer titles are shortened (full title in the tooltip)
RADIUS = {0: 14, 1: 11, 2: 9, 3: 8}   # by folder level
POST_RADIUS = 6
KIND = {0: "root", 1: "macro", 2: "category", 3: "sub"}


@dataclass(eq=False)
class Node:
    label: str
    title: str
    url: str
    kind: str
    color: str
    r: float
    label_w: float = 0.0
    draft: bool = False
    x: float = 0.0
    y: float = 0.0

    @property
    def half_w(self) -> float:
        return max(self.r, self.label_w / 2)


@dataclass(eq=False)
class Edge:
    a: Node
    b: Node
    kind: str  # contains | next | link


def short(text: str) -> str:
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1].rstrip() + "…"


def label_width(label: str, wide: bool) -> float:
    width = len(label) * CHAR_W
    if wide:
        width += len(label) * WIDE_LETTER + label.count(" ") * WIDE_WORD
    return width


def build(section, wide: bool = False) -> tuple[list[Node], list[Edge], Node]:
    """Nodes and edges for `section` and everything below it."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    by_url: dict[str, Node] = {}

    def add(label, url, kind, color, r, draft=False) -> Node:
        n = Node(short(label), label, url, kind, color, r, label_width(short(label), wide), draft)
        nodes.append(n)
        by_url[url] = n
        return n

    def walk(s, parent: Node | None) -> Node:
        n = add(s.title, s.url, KIND[s.level], s.color, RADIUS[s.level])
        if parent:
            edges.append(Edge(parent, n, "contains"))
        for c in s.children:
            walk(c, n)
        post_nodes = []
        for p in s.posts:
            pn = add(p.title, p.url, "post", p.color, POST_RADIUS, p.draft)
            edges.append(Edge(n, pn, "contains"))
            post_nodes.append(pn)
        if s.is_series:
            edges.extend(Edge(a, b, "next") for a, b in zip(post_nodes, post_nodes[1:]))
        return n

    root = walk(section, None)
    for p in section.all_posts:
        for target in p.links_to:
            if target.url in by_url:
                edges.append(Edge(by_url[p.url], by_url[target.url], "link"))
    return nodes, edges, root


def layout(nodes: list[Node], edges: list[Edge], root: Node, iterations: int = 500) -> None:
    children: dict[Node, list[Node]] = {n: [] for n in nodes}
    for e in edges:
        if e.kind == "contains":
            children[e.a].append(e.b)

    def leaves(n: Node) -> int:
        return 1 if not children[n] else sum(leaves(c) for c in children[n])

    ring = 70.0

    def place(n: Node, a0: float, a1: float, depth: int) -> None:  # radial tree start
        mid = (a0 + a1) / 2
        n.x, n.y = depth * ring * math.cos(mid), depth * ring * math.sin(mid)
        total, a = leaves(n), a0
        for c in children[n]:
            span = (a1 - a0) * leaves(c) / total
            place(c, a, a + span, depth + 1)
            a += span

    place(root, -math.pi / 2, 3 * math.pi / 2, 0)

    k = 58.0                                   # ideal edge length
    weight = {"contains": 1.0, "next": 0.6, "link": 0.25}
    for i in range(iterations):
        temp = 25.0 * (1 - i / iterations) + 0.3
        disp = {n: [0.0, 0.0] for n in nodes}
        for ai, a in enumerate(nodes):           # repulsion, stronger when boxes overlap
            for b in nodes[ai + 1:]:
                dx, dy = a.x - b.x, a.y - b.y
                d = math.hypot(dx, dy)
                if d < 0.01:
                    dx, dy, d = 0.01 * (ai + 1), 0.01, 0.015
                force = k * k / d
                gap_x = a.half_w + b.half_w + 14 - abs(dx)
                gap_y = a.r + b.r + FONT + 18 - abs(dy)
                if gap_x > 0 and gap_y > 0:
                    force *= 4
                fx, fy = dx / d * force, dy / d * force
                disp[a][0] += fx; disp[a][1] += fy
                disp[b][0] -= fx; disp[b][1] -= fy
        for e in edges:                          # springs along edges
            dx, dy = e.a.x - e.b.x, e.a.y - e.b.y
            d = max(math.hypot(dx, dy), 0.01)
            force = d * d / k * weight[e.kind]
            fx, fy = dx / d * force, dy / d * force
            disp[e.a][0] -= fx; disp[e.a][1] -= fy
            disp[e.b][0] += fx; disp[e.b][1] += fy
        for n in nodes:
            if n is root:
                continue                          # pinned at the centre
            dx, dy = disp[n][0] - 0.06 * n.x, disp[n][1] - 0.06 * n.y   # gravity keeps it compact
            d = math.hypot(dx, dy)
            if d > 0:
                step = min(d, temp)
                n.x += dx / d * step
                n.y += dy / d * step
    separate_labels(nodes, root)


def box(n: Node) -> tuple[float, float, float, float]:
    """Area taken by a node and its label underneath: left, top, right, bottom."""
    return n.x - n.half_w - 6, n.y - n.r - 4, n.x + n.half_w + 6, n.y + n.r + FONT + 6


def separate_labels(nodes: list[Node], root: Node, passes: int = 200) -> None:
    """Push apart nodes whose boxes still overlap, along the axis that needs the least move."""
    for _ in range(passes):
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                al, at, ar, ab = box(a)
                bl, bt, br, bb = box(b)
                ox, oy = min(ar, br) - max(al, bl), min(ab, bb) - max(at, bt)
                if ox <= 0 or oy <= 0:
                    continue
                moved = True
                if ox < oy:
                    shift, axis = ox / 2 + 0.5, "x"
                    sign = 1 if a.x >= b.x else -1
                else:
                    shift, axis = oy / 2 + 0.5, "y"
                    sign = 1 if a.y >= b.y else -1
                for n, s in ((a, sign), (b, -sign)):
                    k = 2 if (a is root or b is root) else 1   # the root stays put, the other moves twice
                    if n is root:
                        continue
                    setattr(n, axis, getattr(n, axis) + s * shift * k)
        if not moved:
            return


def to_svg(nodes: list[Node], edges: list[Edge], label: str, variant: str) -> str:
    pad = 8
    min_x = min(n.x - n.half_w for n in nodes) - pad
    max_x = max(n.x + n.half_w for n in nodes) + pad
    min_y = min(n.y - n.r for n in nodes) - pad
    max_y = max(n.y + n.r + FONT + 6 for n in nodes) + pad
    w, h = max_x - min_x, max_y - min_y
    out = [
        f'<svg class="net net-{variant}" viewBox="{min_x:.1f} {min_y:.1f} {w:.1f} {h:.1f}" '
        f'width="{w:.0f}" height="{h:.0f}" role="group" aria-label="{html.escape(label)}">',
        f'<defs><marker id="net-arrow-{variant}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
        'orient="auto-start-reverse"><path class="net-arrowhead" d="M0,0 L10,5 L0,10 z"/></marker></defs>',
    ]
    order = {"contains": 0, "next": 1, "link": 2}
    for e in sorted(edges, key=lambda e: order[e.kind]):
        dx, dy = e.b.x - e.a.x, e.b.y - e.a.y
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        end = e.b.r + (3 if e.kind != "contains" else 0)
        x1, y1 = e.a.x + ux * e.a.r, e.a.y + uy * e.a.r
        x2, y2 = e.b.x - ux * end, e.b.y - uy * end
        marker = f' marker-end="url(#net-arrow-{variant})"' if e.kind != "contains" else ""
        out.append(f'<line class="net-edge net-{e.kind}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"{marker}/>')
    for n in nodes:
        cls = f"net-node net-{n.kind}" + (" net-draft" if n.draft else "")
        pos = f'x="{n.x:.1f}" y="{n.y + n.r + FONT:.1f}" text-anchor="middle"'
        label = html.escape(n.label)
        out.append(
            f'<a class="{cls}" href="{n.url}" data-color="{n.color}">'
            f"<title>{html.escape(n.title)}{' (draft)' if n.draft else ''}</title>"
            f'<circle cx="{n.x:.1f}" cy="{n.y:.1f}" r="{n.r}"/>'
            # The halo is a separate copy behind the label: a stroke on the label itself
            # would also stroke (and cut into) the hover underline.
            f'<text class="net-halo" aria-hidden="true" {pos}>{label}</text>'
            f'<text class="net-label" {pos}>{label}</text></a>'
        )
    out.append("</svg>")
    return "\n".join(out)


def svg_for(section, wide: bool = False) -> str:
    """The drawing for normal text spacing, or for the "Wider spacing" preference (wider labels,
    so a separate layout). Marker ids differ per variant, since both sit in the same page."""
    nodes, edges, root = build(section, wide)
    if len(nodes) < 2:
        return ""
    layout(nodes, edges, root)
    return to_svg(nodes, edges, f"Graph of {section.title}", "wide" if wide else "normal")
