#!/usr/bin/env python3
"""Render the Mermaid story graph to a standalone SVG file.

This uses a lightweight Sugiyama-style layered layout with iterative barycenter
ordering to reduce edge crossings without depending on Graphviz or Mermaid CLI.
"""

from __future__ import annotations

import argparse
import html
import re
from collections import deque
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Set, Tuple

NODE_RE = re.compile(r'^\s*P(\d+)\["(\d+)"\]\s*$')
EDGE_RE = re.compile(r'^\s*P(\d+)\s*-->\s*P(\d+)\s*$')

NODE_W = 72
NODE_H = 40
LAYER_GAP = 146
ROW_GAP = 52
MARGIN_X = 40
MARGIN_Y = 40
FONT_SIZE = 11

DEFAULT_NODE_FILL = "#e2e8f0"
DEFAULT_NODE_STROKE = "#475569"
DEFAULT_EDGE_STROKE = "#94a3b8"
TERMINAL_NODE_FILL = "#fee2e2"
TERMINAL_NODE_STROKE = "#b91c1c"
MAIN_TRUNK_NODE_FILL = "#dbeafe"
MAIN_TRUNK_NODE_STROKE = "#1d4ed8"
MAIN_TRUNK_EDGE_STROKE = "#2563eb"


def parse_graph(graph_path: Path) -> Tuple[List[int], Dict[int, List[int]]]:
    nodes: Set[int] = set()
    edges: Dict[int, List[int]] = {}

    for line in graph_path.read_text(encoding="utf-8").splitlines():
        node_match = NODE_RE.match(line)
        if node_match:
            node = int(node_match.group(1))
            nodes.add(node)
            edges.setdefault(node, [])
            continue

        edge_match = EDGE_RE.match(line)
        if edge_match:
            src = int(edge_match.group(1))
            dst = int(edge_match.group(2))
            nodes.add(src)
            nodes.add(dst)
            edges.setdefault(src, [])
            edges.setdefault(dst, [])
            if dst not in edges[src]:
                edges[src].append(dst)

    return sorted(nodes), edges


def build_predecessors(nodes: List[int], edges: Dict[int, List[int]]) -> Dict[int, List[int]]:
    predecessors = {node: [] for node in nodes}
    for src in nodes:
        for dst in edges.get(src, []):
            predecessors.setdefault(dst, []).append(src)
    for node in predecessors:
        predecessors[node].sort()
    return predecessors


def topological_order(nodes: List[int], edges: Dict[int, List[int]]) -> List[int]:
    indegree = {node: 0 for node in nodes}
    for src in nodes:
        for dst in edges.get(src, []):
            indegree[dst] = indegree.get(dst, 0) + 1

    queue = deque(sorted(node for node in nodes if indegree.get(node, 0) == 0))
    order: List[int] = []

    while queue:
        src = queue.popleft()
        order.append(src)
        for dst in sorted(edges.get(src, [])):
            indegree[dst] -= 1
            if indegree[dst] == 0:
                queue.append(dst)

    # Fallback for imperfect graphs with residual cycles.
    remaining = [node for node in nodes if node not in set(order)]
    return order + sorted(remaining)


def compute_levels(nodes: List[int], edges: Dict[int, List[int]]) -> Dict[int, int]:
    order = topological_order(nodes, edges)
    predecessors = build_predecessors(nodes, edges)
    levels: Dict[int, int] = {}

    for node in order:
        preds = predecessors.get(node, [])
        if not preds:
            levels[node] = 0
        else:
            levels[node] = max(levels.get(pred, 0) for pred in preds) + 1

    for node in nodes:
        levels.setdefault(node, 0)

    return levels


def build_layers(nodes: List[int], levels: Dict[int, int]) -> Dict[int, List[int]]:
    layers: Dict[int, List[int]] = {}
    for node in nodes:
        layers.setdefault(levels[node], []).append(node)
    for level in layers:
        layers[level].sort()
    return layers


def neighbor_positions(neighbors: Iterable[int], positions: Dict[int, int]) -> List[int]:
    return [positions[n] for n in neighbors if n in positions]


def barycenter_value(node: int, neighbors: Iterable[int], positions: Dict[int, int], fallback: int) -> float:
    samples = neighbor_positions(neighbors, positions)
    if not samples:
        return float(fallback)
    return mean(samples)


def reduce_crossings(nodes: List[int], edges: Dict[int, List[int]], levels: Dict[int, int]) -> Dict[int, List[int]]:
    predecessors = build_predecessors(nodes, edges)
    layers = build_layers(nodes, levels)
    max_level = max(layers, default=0)

    for _ in range(8):
        # Downward sweep: align by predecessors.
        for level in range(1, max_level + 1):
            prev_positions = {node: index for index, node in enumerate(layers.get(level - 1, []))}
            current_order = {node: index for index, node in enumerate(layers.get(level, []))}
            layers[level].sort(
                key=lambda node: (
                    barycenter_value(node, predecessors.get(node, []), prev_positions, current_order[node]),
                    node,
                )
            )

        # Upward sweep: align by successors.
        for level in range(max_level - 1, -1, -1):
            next_positions = {node: index for index, node in enumerate(layers.get(level + 1, []))}
            current_order = {node: index for index, node in enumerate(layers.get(level, []))}
            layers[level].sort(
                key=lambda node: (
                    barycenter_value(node, edges.get(node, []), next_positions, current_order[node]),
                    node,
                )
            )

    return layers


def find_terminal_nodes(nodes: List[int], edges: Dict[int, List[int]]) -> Set[int]:
    return {node for node in nodes if not edges.get(node, [])}


def find_main_trunk(nodes: List[int], edges: Dict[int, List[int]], start: int = 2) -> Tuple[Set[int], Set[Tuple[int, int]]]:
    if start not in nodes:
        return set(), set()

    trunk_nodes: Set[int] = {start}
    trunk_edges: Set[Tuple[int, int]] = set()
    current = start
    visited = {start}

    while True:
        targets = sorted(edges.get(current, []))
        if not targets:
            break

        next_node = targets[0]
        trunk_edges.add((current, next_node))
        if next_node in visited:
            break
        trunk_nodes.add(next_node)
        visited.add(next_node)
        current = next_node

    return trunk_nodes, trunk_edges

def compute_positions(nodes: List[int], edges: Dict[int, List[int]]) -> Tuple[Dict[int, Tuple[int, int]], int, int]:
    levels = compute_levels(nodes, edges)
    layers = reduce_crossings(nodes, edges, levels)

    positions: Dict[int, Tuple[int, int]] = {}
    max_layer_size = max((len(layer_nodes) for layer_nodes in layers.values()), default=0)

    for level in sorted(layers):
        layer_nodes = layers[level]
        layer_height = max(0, (len(layer_nodes) - 1) * ROW_GAP)
        top_offset = MARGIN_Y + ((max_layer_size - 1) * ROW_GAP - layer_height) // 2
        for row, node in enumerate(layer_nodes):
            x = MARGIN_X + (level * LAYER_GAP)
            y = top_offset + (row * ROW_GAP)
            positions[node] = (x, y)

    width = MARGIN_X * 2 + (max(levels.values(), default=0) * LAYER_GAP) + NODE_W + 40
    height = MARGIN_Y * 2 + (max(0, max_layer_size - 1) * ROW_GAP) + NODE_H + 20
    return positions, width, height


def render_svg(nodes: List[int], edges: Dict[int, List[int]]) -> str:
    positions, width, height = compute_positions(nodes, edges)
    terminal_nodes = find_terminal_nodes(nodes, edges)
    main_trunk_nodes, main_trunk_edges = find_main_trunk(nodes, edges, start=2)
    predecessors = build_predecessors(nodes, edges)

    lines: List[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    lines.append('<defs>')
    lines.append('<marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
    lines.append('<polygon points="0 0, 10 3.5, 0 7" fill="#4b5563" />')
    lines.append('</marker>')
    lines.append('</defs>')
    lines.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" />')

    for src in nodes:
        x1, y1 = positions[src]
        for dst in edges.get(src, []):
            if dst not in positions:
                continue
            x2, y2 = positions[dst]
            start_x = x1 + NODE_W
            start_y = y1 + (NODE_H // 2)
            end_x = x2
            end_y = y2 + (NODE_H // 2)
            bend1_x = start_x + max(24, (end_x - start_x) * 0.35)
            bend2_x = end_x - max(24, (end_x - start_x) * 0.35)
            path = f'M {start_x} {start_y} C {bend1_x:.1f} {start_y}, {bend2_x:.1f} {end_y}, {end_x} {end_y}'
            is_trunk = (src, dst) in main_trunk_edges
            stroke = MAIN_TRUNK_EDGE_STROKE if is_trunk else DEFAULT_EDGE_STROKE
            stroke_width = "2.6" if is_trunk else "1.4"
            opacity = "0.95" if is_trunk else "0.85"
            lines.append(f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity}" marker-end="url(#arrow)" class="edge" data-src="{src}" data-dst="{dst}" title="Page {src} → Page {dst}" />')

    for node in nodes:
        x, y = positions[node]
        incoming = len(predecessors.get(node, []))
        outgoing = len(edges.get(node, []))
        page_label = html.escape(str(node))

        if node in main_trunk_nodes:
            fill = MAIN_TRUNK_NODE_FILL
            stroke = MAIN_TRUNK_NODE_STROKE
            stroke_width = "2"
            node_class = "node node-main"
            subtitle = "main path"
        elif node in terminal_nodes:
            fill = TERMINAL_NODE_FILL
            stroke = TERMINAL_NODE_STROKE
            stroke_width = "1.6"
            node_class = "node node-terminal"
            subtitle = "ending"
        else:
            fill = DEFAULT_NODE_FILL
            stroke = DEFAULT_NODE_STROKE
            stroke_width = "1.2"
            node_class = "node node-branch"
            subtitle = f"{outgoing} choice{'s' if outgoing != 1 else ''}"

        title_text = f"Page {page_label} — {subtitle}, {incoming} incoming, {outgoing} outgoing"
        desc_text = f"Story node for page {page_label}. {incoming} incoming edges and {outgoing} outgoing edges."

        lines.append(f'<g id="node-{page_label}" class="{node_class}" data-page="{page_label}" data-incoming="{incoming}" data-outgoing="{outgoing}">')
        lines.append(f'<title>{html.escape(title_text)}</title>')
        lines.append(f'<desc>{html.escape(desc_text)}</desc>')
        lines.append(f'<rect x="{x}" y="{y}" rx="8" ry="8" width="{NODE_W}" height="{NODE_H}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" />')
        lines.append(
            f'<text x="{x + NODE_W / 2}" y="{y + NODE_H / 2 - 4}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="{FONT_SIZE}" fill="#0f172a">'
            f'<tspan x="{x + NODE_W / 2}" dy="0">Page {page_label}</tspan>'
            f'<tspan x="{x + NODE_W / 2}" dy="1.3em">{html.escape(subtitle)}</tspan>'
            '</text>'
        )
        lines.append('</g>')

    lines.append('</svg>')
    return '\n'.join(lines) + '\n'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Mermaid story graph to SVG.")
    parser.add_argument("--graph", type=Path, default=Path("output/cot-story-graph.mmd"))
    parser.add_argument("--output", type=Path, default=Path("output/cot-story-graph.svg"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.graph.exists():
        raise FileNotFoundError(f"Graph file not found: {args.graph}")

    nodes, edges = parse_graph(args.graph)
    svg = render_svg(nodes, edges)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")

    print(f"Nodes: {len(nodes)}")
    print(f"SVG file: {args.output}")


if __name__ == "__main__":
    main()
