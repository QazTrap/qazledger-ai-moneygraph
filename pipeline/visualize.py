from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
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


def make_ranking(top: pd.DataFrame, out_dir: Path, top_n: int) -> Path:
    plot_df = (
        top.sort_values("rank")
        .head(top_n)
        .copy()
    )

    labels = [
        f"#{int(r.rank)}  {int(r.gid)}  [{r.role}]"
        for r in plot_df.itertuples(index=False)
    ]

    fig_h = max(7.0, 0.42 * len(plot_df) + 2.0)
    fig, ax = plt.subplots(figsize=(12, fig_h))

    y = range(len(plot_df))
    ax.barh(y, plot_df["priority_score"].astype(float))
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Priority score")
    ax.set_title(f"QazLedger MoneyGraph — Top {len(plot_df)} Nodes")
    ax.grid(axis="x", alpha=0.25)

    for i, score in enumerate(plot_df["priority_score"].astype(float)):
        ax.text(min(score + 0.01, 0.98), i, f"{score:.4f}", va="center", fontsize=8)

    fig.tight_layout()
    path = out_dir / "top20_ranking.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _connector_candidates(edges: pd.DataFrame, top_ids: set[int]) -> pd.DataFrame:
    """
    Ищет промежуточные узлы, напрямую связанные минимум с двумя Top-узлами.
    Это помогает показать структуру, если среди самих Top-20 мало прямых рёбер.
    """
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

    # Сначала пытаемся показать прямые связи Top-N между собой.
    top_edges = edges[
        edges["src"].isin(top_ids) & edges["dst"].isin(top_ids)
    ].copy()

    connector_ids: set[int] = set()

    # Если прямых связей мало, добавляем ограниченное число полезных
    # промежуточных узлов, связанных минимум с двумя Top-узлами.
    if len(top_edges) < max(5, top_n // 3):
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

    role_lookup = roles.set_index("gid")["role"].to_dict()
    priority_lookup = roles.set_index("gid")["priority_score"].to_dict()
    rank_lookup = top_df.set_index("gid")["rank"].to_dict()

    # Удаляем изолированные connector-узлы, если они не попали в выбранные рёбра.
    for gid in list(connector_ids):
        if g.degree(gid) == 0:
            g.remove_node(gid)
            connector_ids.discard(gid)

    if g.number_of_nodes() == 0:
        raise RuntimeError("Не удалось построить сетевой граф.")

    fig, ax = plt.subplots(figsize=(15, 11))
    pos = nx.spring_layout(g, seed=42, k=None, weight=None)

    top_nodes = [n for n in g.nodes if n in top_ids]
    connector_nodes = [n for n in g.nodes if n not in top_ids]

    top_sizes = [
        700 + 1800 * float(priority_lookup.get(n, 0.0))
        for n in top_nodes
    ]
    connector_sizes = [260 for _ in connector_nodes]

    if connector_nodes:
        nx.draw_networkx_nodes(
            g,
            pos,
            nodelist=connector_nodes,
            node_size=connector_sizes,
            alpha=0.55,
            ax=ax,
        )

    nx.draw_networkx_nodes(
        g,
        pos,
        nodelist=top_nodes,
        node_size=top_sizes,
        alpha=0.90,
        ax=ax,
    )

    nx.draw_networkx_edges(
        g,
        pos,
        arrows=True,
        arrowsize=14,
        width=1.0,
        alpha=0.45,
        ax=ax,
    )

    labels = {}
    for n in top_nodes:
        rank = int(rank_lookup.get(n, 0))
        role = role_lookup.get(n, "")
        short_gid = str(n)[-6:]
        labels[n] = f"#{rank}\n{short_gid}\n{role}"

    nx.draw_networkx_labels(
        g,
        pos,
        labels=labels,
        font_size=7,
        ax=ax,
    )

    ax.set_title(
        f"QazLedger MoneyGraph — Top {len(top_nodes)} Network"
        + (f" (+{len(connector_nodes)} connectors)" if connector_nodes else "")
    )
    ax.axis("off")
    fig.tight_layout()

    path = out_dir / "top20_network.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
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
