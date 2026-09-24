from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd


def load_inputs(data_dir: Path, out_dir: Path):
    edges_path = data_dir / "edges.parquet"
    top_path = out_dir / "top_nodes.csv"
    roles_path = out_dir / "nodes_roles.csv"

    missing = [p for p in (edges_path, top_path, roles_path) if not p.exists()]
    if missing:
        names = ", ".join(str(p) for p in missing)
        raise FileNotFoundError(
            "Не найдены необходимые файлы: "
            + names
            + "\nСначала запустите pipeline.py, чтобы создать CSV-результаты."
        )

    edges = pd.read_parquet(edges_path)
    top = pd.read_csv(top_path)
    roles = pd.read_csv(roles_path)

    required_edges = {"src", "dst", "sum_kzt"}
    required_top = {"rank", "gid", "role", "priority_score"}
    required_roles = {"gid", "role", "role_score", "cluster_id", "priority_score"}

    if not required_edges.issubset(edges.columns):
        raise ValueError(f"edges.parquet: нужны колонки {sorted(required_edges)}")
    if not required_top.issubset(top.columns):
        raise ValueError(f"top_nodes.csv: нужны колонки {sorted(required_top)}")
    if not required_roles.issubset(roles.columns):
        raise ValueError(f"nodes_roles.csv: нужны колонки {sorted(required_roles)}")

    for c in ("src", "dst"):
        edges[c] = edges[c].astype("int64")
    top["gid"] = top["gid"].astype("int64")
    roles["gid"] = roles["gid"].astype("int64")

    return edges, top, roles


def short_gid(gid: int) -> str:
    s = str(int(gid))
    return f"…{s[-6:]}"


def make_ranking(top: pd.DataFrame, out_dir: Path, top_n: int) -> Path:
    plot_df = top.sort_values("rank").head(top_n).copy()

    labels = [
        f"#{int(r.rank)} · {short_gid(int(r.gid))} · {r.role}"
        for r in plot_df.itertuples(index=False)
    ]

    fig_h = max(7.5, 0.43 * len(plot_df) + 2.0)
    fig, ax = plt.subplots(figsize=(12, fig_h))

    y = np.arange(len(plot_df))
    scores = plot_df["priority_score"].astype(float).to_numpy()

    ax.barh(y, scores)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Priority score")
    ax.set_title(f"QazLedger MoneyGraph — Top {len(plot_df)} Nodes")
    ax.grid(axis="x", alpha=0.22)

    for i, score in enumerate(scores):
        ax.text(min(score + 0.01, 0.97), i, f"{score:.4f}", va="center", fontsize=8)

    fig.text(
        0.01,
        0.01,
        "Labels use the last 6 digits of GID. Full GIDs are available in output/top_nodes.csv.",
        fontsize=8,
        alpha=0.75,
    )

    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path = out_dir / "top20_ranking.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def _connector_candidates(edges: pd.DataFrame, top_ids: set[int]) -> pd.DataFrame:
    relevant = edges[
        edges["src"].isin(top_ids) | edges["dst"].isin(top_ids)
    ].copy()

    if relevant.empty:
        return pd.DataFrame(columns=["gid", "top_links", "sum_kzt"])

    rows = []
    candidate_ids = set(relevant["src"]).union(set(relevant["dst"])) - top_ids

    for gid in candidate_ids:
        part = relevant[(relevant["src"] == gid) | (relevant["dst"] == gid)]
        neighbors = set()

        for r in part.itertuples(index=False):
            if int(r.src) in top_ids:
                neighbors.add(int(r.src))
            if int(r.dst) in top_ids:
                neighbors.add(int(r.dst))

        if len(neighbors) >= 2:
            rows.append(
                {
                    "gid": int(gid),
                    "top_links": len(neighbors),
                    "sum_kzt": float(part["sum_kzt"].sum()),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["gid", "top_links", "sum_kzt"])

    return (
        pd.DataFrame(rows)
        .sort_values(["top_links", "sum_kzt"], ascending=False)
        .reset_index(drop=True)
    )


def _edge_widths(g: nx.DiGraph) -> list[float]:
    values = np.array(
        [float(d.get("sum_kzt", 0.0)) for _, _, d in g.edges(data=True)],
        dtype=float,
    )

    if len(values) == 0:
        return []

    logged = np.log1p(np.maximum(values, 0.0))
    lo = float(logged.min())
    hi = float(logged.max())

    if hi <= lo:
        return [1.4] * len(values)

    scaled = (logged - lo) / (hi - lo)
    return (0.7 + 3.0 * scaled).tolist()


def make_network(
    edges: pd.DataFrame,
    top: pd.DataFrame,
    roles: pd.DataFrame,
    out_dir: Path,
    top_n: int,
    max_connectors: int,
) -> Path:
    top_df = top.sort_values("rank").head(top_n).copy()
    top_ids = set(top_df["gid"].astype(int))

    direct_top_edges = edges[
        edges["src"].isin(top_ids) & edges["dst"].isin(top_ids)
    ].copy()

    connector_ids: set[int] = set()

    if len(direct_top_edges) < max(5, top_n // 3):
        candidates = _connector_candidates(edges, top_ids)
        connector_ids = set(
            candidates.head(max_connectors)["gid"].astype(int).tolist()
        )

    selected_ids = top_ids | connector_ids

    selected_edges = edges[
        edges["src"].isin(selected_ids) & edges["dst"].isin(selected_ids)
    ].copy()

    g = nx.DiGraph()
    g.add_nodes_from(selected_ids)

    for r in selected_edges.itertuples(index=False):
        u, v = int(r.src), int(r.dst)
        weight = float(r.sum_kzt)

        if g.has_edge(u, v):
            g[u][v]["sum_kzt"] += weight
        else:
            g.add_edge(u, v, sum_kzt=weight)

    rank_lookup = top_df.set_index("gid")["rank"].to_dict()
    priority_lookup = roles.set_index("gid")["priority_score"].to_dict()

    isolated_top = sorted(
        [n for n in top_ids if n in g and g.degree(n) == 0],
        key=lambda gid: int(rank_lookup.get(gid, 9999)),
    )
    g.remove_nodes_from(isolated_top)

    isolated_connectors = [n for n in connector_ids if n in g and g.degree(n) == 0]
    g.remove_nodes_from(isolated_connectors)
    connector_ids -= set(isolated_connectors)

    if g.number_of_nodes() == 0:
        raise RuntimeError(
            "В выбранном Top-N нет отображаемых связей. "
            "Попробуйте увеличить --max-connectors."
        )

    # Финальная презентационная раскладка:
    # больше расстояния + больше итераций для снижения наложений.
    k = max(1.15, 3.0 / max(np.sqrt(g.number_of_nodes()), 1.0))
    pos = nx.spring_layout(
        g,
        seed=42,
        k=k,
        iterations=500,
        weight=None,
        scale=3.0,
    )

    fig, ax = plt.subplots(figsize=(16, 12))

    top_nodes = [n for n in g.nodes if n in top_ids]
    connector_nodes = [n for n in g.nodes if n not in top_ids]

    top_sizes = [
        1000 + 1700 * float(priority_lookup.get(n, 0.0))
        for n in top_nodes
    ]

    if connector_nodes:
        nx.draw_networkx_nodes(
            g,
            pos,
            nodelist=connector_nodes,
            node_size=280,
            node_shape="s",
            alpha=0.42,
            ax=ax,
        )

    nx.draw_networkx_nodes(
        g,
        pos,
        nodelist=top_nodes,
        node_size=top_sizes,
        node_shape="o",
        alpha=0.88,
        ax=ax,
    )

    nx.draw_networkx_edges(
        g,
        pos,
        arrows=True,
        arrowsize=16,
        width=_edge_widths(g),
        alpha=0.36,
        connectionstyle="arc3,rad=0.035",
        ax=ax,
    )

    # Только rank + последние 6 цифр GID.
    # Роли уже показаны на ranking-графике и в top_nodes.csv.
    labels = {
        n: f"#{int(rank_lookup.get(n, 0))}\n{short_gid(n)}"
        for n in top_nodes
    }

    nx.draw_networkx_labels(
        g,
        pos,
        labels=labels,
        font_size=8,
        ax=ax,
    )

    ax.set_title(
        "QazLedger MoneyGraph — Key Top-20 Subgraph\n"
        f"{g.number_of_nodes()} displayed nodes · {g.number_of_edges()} directed edges"
    )

    note_lines = [
        "Large circles: Top-20 nodes",
        "Small squares: connector nodes",
        "Edge width: relative sum_kzt",
        "Node labels: rank + last 6 digits of GID",
        "Roles are shown in top20_ranking.png and top_nodes.csv",
    ]

    if isolated_top:
        isolated_text = ", ".join(
            f"#{int(rank_lookup[g])} {short_gid(g)}"
            for g in isolated_top
        )
        note_lines.append(
            f"Top nodes without links in selected subgraph: {isolated_text}"
        )

    ax.text(
        0.01,
        0.01,
        "\n".join(note_lines),
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        ha="left",
        alpha=0.78,
    )

    ax.axis("off")
    fig.tight_layout()

    path = out_dir / "top20_network.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser(
        description="QazLedger MoneyGraph: визуализация Top-N и ключевой сети"
    )
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="output")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--max-connectors", type=int, default=25)
    args = ap.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    edges, top, roles = load_inputs(data_dir, out_dir)

    top_n = max(1, min(int(args.top), len(top)))

    ranking_path = make_ranking(top, out_dir, top_n)
    network_path = make_network(
        edges,
        top,
        roles,
        out_dir,
        top_n,
        max(0, int(args.max_connectors)),
    )

    print("QazLedger MoneyGraph visualization complete")
    print(f"ranking: {ranking_path}")
    print(f"network: {network_path}")


if __name__ == "__main__":
    main()
