from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path



def wrap_text(text: str, width: int = 22) -> str:
    return "\n".join(textwrap.wrap(str(text), width=width))


def extract_node(token: str):
    """
    Parse Mermaid node syntax:
      A[Text]
      B{Decision}
      C(Text)
      D
    Returns: (node_id, label, shape)
    """
    token = token.strip()

    patterns = [
        (r'^([A-Za-z0-9_]+)\[(.+)\]$', 'rect'),
        (r'^([A-Za-z0-9_]+)\{(.+)\}$', 'diamond'),
        (r'^([A-Za-z0-9_]+)\((.+)\)$', 'round'),
        (r'^([A-Za-z0-9_]+)$', 'plain'),
    ]

    for pattern, shape in patterns:
        m = re.match(pattern, token)
        if m:
            node_id = m.group(1)
            label = m.group(2) if len(m.groups()) > 1 else node_id
            return node_id, label.strip(), shape

    raise ValueError(f"Could not parse Mermaid node: {token}")


def split_mermaid_chain(line: str):
    """
    Supports:
      A --> B
      A -->|Yes| B
      A -- Yes --> B
      A --> B --> C
    """
    token_pattern = re.compile(r'(-->\|[^|]+\||--\s*[^-][^-]*?\s*-->|-->)')
    parts = token_pattern.split(line)
    return [p.strip() for p in parts if p and p.strip()]


def parse_edge_operator(op: str) -> str:
    """
    Parse Mermaid edge operators:
      -->
      -->|Yes|
      -- Yes -->
    """
    op = op.strip()

    m = re.match(r'^-->\|(.+)\|$', op)
    if m:
        return m.group(1).strip()

    m = re.match(r'^--\s*(.+?)\s*-->$', op)
    if m:
        return m.group(1).strip()

    return '' if op == '-->' else ''


def parse_mermaid_flowchart(mermaid_text: str):
    """
    Parse simplified Mermaid flowcharts.
    Supports:
      flowchart TD
      A[Start] --> B[Next]
      B -->|Yes| C[Approved]
      B -- No --> D[Rejected]
      A --> B --> C
    """
    lines = [line.strip() for line in mermaid_text.strip().splitlines() if line.strip()]

    if not lines:
        return [], {}, {}

    if lines[0].lower().startswith("flowchart"):
        lines = lines[1:]

    edges = []
    node_labels = {}
    node_shapes = {}

    for line in lines:
        if line.lower().startswith(("classdef ", "class ", "style ", "linkstyle ", "subgraph ", "end")):
            continue

        parts = split_mermaid_chain(line)
        if len(parts) < 3:
            continue

        for i in range(0, len(parts) - 2, 2):
            left_raw = parts[i]
            op = parts[i + 1]
            right_raw = parts[i + 2]

            try:
                left_id, left_label, left_shape = extract_node(left_raw)
                right_id, right_label, right_shape = extract_node(right_raw)
            except ValueError:
                continue

            edge_label = parse_edge_operator(op)

            node_labels[left_id] = left_label
            node_labels[right_id] = right_label
            node_shapes[left_id] = left_shape
            node_shapes[right_id] = right_shape
            edges.append((left_id, right_id, edge_label))

    return edges, node_labels, node_shapes


def compute_hierarchical_positions(graph: nx.DiGraph):
    """
    Create a basic top-down layout for DAG-like graphs.
    Falls back to spring layout if needed.
    """
    try:
        roots = [n for n in graph.nodes() if graph.in_degree(n) == 0]
        if not roots:
            raise ValueError("No roots found")

        levels = {}
        frontier = roots
        visited = set()
        level = 0

        while frontier:
            next_frontier = []
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)
                levels[node] = level
                for succ in graph.successors(node):
                    if succ not in visited:
                        next_frontier.append(succ)
            frontier = list(dict.fromkeys(next_frontier))
            level += 1

        for node in graph.nodes():
            if node not in levels:
                levels[node] = level

        level_map = {}
        for node, lvl in levels.items():
            level_map.setdefault(lvl, []).append(node)

        pos = {}
        for lvl, nodes in sorted(level_map.items()):
            count = len(nodes)
            for idx, node in enumerate(nodes):
                x = (idx + 1) / (count + 1)
                y = -lvl
                pos[node] = (x, y)

        return pos
    except Exception:
        return nx.spring_layout(graph, seed=42, k=2.0)


def mermaid_to_png(mermaid_text: str, output_path: str):
    """
    Render Mermaid-like flowchart to PNG.
    """
    import networkx as nx
    import matplotlib.pyplot as plt

    edges, node_labels, node_shapes = parse_mermaid_flowchart(mermaid_text)

    if not edges:
        raise ValueError("Could not parse Mermaid flowchart content.")

    g = nx.DiGraph()
    for src, dst, edge_label in edges:
        g.add_node(src)
        g.add_node(dst)
        g.add_edge(src, dst, label=edge_label)

    pos = compute_hierarchical_positions(g)

    plt.figure(figsize=(14, 10))
    ax = plt.gca()
    ax.set_axis_off()

    nx.draw_networkx_edges(
        g,
        pos,
        arrows=True,
        arrowstyle='-|>',
        arrowsize=18,
        width=1.5,
        connectionstyle='arc3,rad=0.03'
    )

    shape_map = {
        'rect': 's',
        'diamond': 'D',
        'round': 'o',
        'plain': 'o'
    }

    for shape_name, marker in shape_map.items():
        nodes = [n for n in g.nodes() if node_shapes.get(n, 'plain') == shape_name]
        if nodes:
            nx.draw_networkx_nodes(
                g,
                pos,
                nodelist=nodes,
                node_shape=marker,
                node_size=5000,
                linewidths=1.5
            )

    wrapped_labels = {node: wrap_text(node_labels.get(node, node), 22) for node in g.nodes()}
    nx.draw_networkx_labels(g, pos, labels=wrapped_labels, font_size=9)

    edge_labels = {(u, v): d.get("label", "") for u, v, d in g.edges(data=True) if d.get("label")}
    if edge_labels:
        nx.draw_networkx_edge_labels(g, pos, edge_labels=edge_labels, font_size=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close()


def replace_mermaid_blocks(md_text: str, asset_dir: Path) -> str:
    """
    Replace fenced mermaid blocks with generated PNG images.
    """
    asset_dir.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(r"```mermaid\s+(.*?)```", re.DOTALL | re.IGNORECASE)
    counter = 1

    def repl(match):
        nonlocal counter
        mermaid_code = match.group(1).strip()
        img_name = f"mermaid_diagram_{counter}.png"
        img_path = asset_dir / img_name

        try:
            mermaid_to_png(mermaid_code, str(img_path))
            replacement = f"\n![Flowchart]({img_path.as_posix()})\n"
        except Exception:
            replacement = (
                "\n\n**Flowchart could not be rendered automatically.**\n\n"
                "```text\n"
                f"{mermaid_code}\n"
                "```\n"
            )

        counter += 1
        return replacement

    return pattern.sub(repl, md_text)


def preprocess_markdown(md_text: str, asset_dir: Path) -> str:
    return replace_mermaid_blocks(md_text, asset_dir)


def link_callback(uri, rel):
    """
    Resolve local image/file paths for xhtml2pdf.
    """
    path = Path(uri)

    if path.is_absolute() and path.exists():
        return str(path)

    if rel:
        rel_path = Path(rel) / uri
        if rel_path.exists():
            return str(rel_path.resolve())

    cwd_path = Path.cwd() / uri
    if cwd_path.exists():
        return str(cwd_path.resolve())

    return uri


def build_html_from_markdown(md_text: str) -> str:
    import markdown
    html_body = markdown.markdown(
        md_text,
        extensions=[
            "extra",
            "tables",
            "fenced_code",
            "toc",
            "sane_lists",
            "nl2br"
        ]
    )

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4;
                margin: 0.8in;
            }}

            body {{
                font-family: Helvetica, Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #222;
            }}

            h1 {{
                font-size: 24pt;
                margin-bottom: 10px;
                border-bottom: 2px solid #444;
                padding-bottom: 6px;
            }}

            h2 {{
                font-size: 18pt;
                margin-top: 20px;
                margin-bottom: 8px;
                color: #333;
            }}

            h3 {{
                font-size: 14pt;
                margin-top: 16px;
                margin-bottom: 6px;
                color: #444;
            }}

            h4, h5, h6 {{
                margin-top: 12px;
                margin-bottom: 6px;
            }}

            p {{
                margin: 8px 0;
            }}

            strong {{
                font-weight: bold;
            }}

            em {{
                font-style: italic;
            }}

            ul, ol {{
                margin-top: 6px;
                margin-bottom: 10px;
                margin-left: 22px;
            }}

            li {{
                margin-bottom: 4px;
            }}

            blockquote {{
                border-left: 4px solid #999;
                padding-left: 10px;
                color: #555;
                margin: 10px 0;
            }}

            code {{
                font-family: Courier, monospace;
                background-color: #f4f4f4;
                padding: 2px 4px;
                border: 1px solid #ddd;
            }}

            pre {{
                font-family: Courier, monospace;
                background-color: #f4f4f4;
                border: 1px solid #ddd;
                padding: 10px;
                white-space: pre-wrap;
                word-wrap: break-word;
                font-size: 9pt;
            }}

            pre code {{
                background-color: transparent;
                border: none;
                padding: 0;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 12px 0;
                table-layout: fixed;
            }}

            th, td {{
                border: 1px solid #999;
                padding: 6px;
                vertical-align: top;
                word-wrap: break-word;
                font-size: 10pt;
            }}

            th {{
                background-color: #eaeaea;
                font-weight: bold;
            }}

            img {{
                max-width: 100%;
                display: block;
                margin: 12px 0;
            }}

            hr {{
                border: none;
                border-top: 1px solid #999;
                margin: 16px 0;
            }}
        </style>
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """


def md_to_pdf(md_file: str, pdf_file: str) -> None:
    """Convert a Markdown file to PDF using xhtml2pdf.

    Mermaid fenced code blocks are rendered as PNG diagrams via matplotlib/networkx.
    Raises FileNotFoundError if *md_file* does not exist, RuntimeError on PDF failure.
    """
    md_path = Path(md_file)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file}")

    asset_dir = md_path.parent / "generated_assets"
    md_text = md_path.read_text(encoding="utf-8")

    processed_md = preprocess_markdown(md_text, asset_dir)
    html_output = build_html_from_markdown(processed_md)

    from xhtml2pdf import pisa
    with open(pdf_file, "wb") as pdf:
        result = pisa.CreatePDF(
            src=html_output,
            dest=pdf,
            link_callback=link_callback
        )

    if result.err:
        raise RuntimeError("PDF generation failed")
