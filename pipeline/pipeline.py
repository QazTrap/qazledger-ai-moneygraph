from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


def clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def minmax(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    lo, hi = float(s.min()), float(s.max())
    if hi <= lo:
        return pd.Series(np.zeros(len(s)), index=s.index, dtype=float)
    return (s - lo) / (hi - lo)


def safe_ratio(a: float, b: float) -> float:
    return 0.0 if b <= 0 else float(a / b)


def load_data(data_dir: Path):
    paths = {
        "edges": data_dir / "edges.parquet",
        "nodes": data_dir / "nodes.parquet",
        "tx": data_dir / "transactions.parquet",
    }
    missing = [p.name for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError("Не найдены: " + ", ".join(missing))

    edges = pd.read_parquet(paths["edges"])
    nodes = pd.read_parquet(paths["nodes"])
    tx = pd.read_parquet(paths["tx"])

    required = {
        "edges.parquet": (edges, {"src", "dst", "sum_kzt", "n_tx", "depth"}),
        "nodes.parquet": (nodes, {"gid", "depth", "is_seed"}),
        "transactions.parquet": (tx, {"src", "dst", "date", "sum_kzt"}),
    }
    for name, (df, cols) in required.items():
        absent = cols - set(df.columns)
        if absent:
            raise ValueError(f"{name}: отсутствуют поля {sorted(absent)}")

    edges = edges.copy()
    nodes = nodes.copy()
    tx = tx.copy()
    for c in ["src", "dst"]:
        edges[c] = edges[c].astype("int64")
        tx[c] = tx[c].astype("int64")
    nodes["gid"] = nodes["gid"].astype("int64")
    edges["sum_kzt"] = pd.to_numeric(edges["sum_kzt"], errors="coerce").fillna(0.0)
    edges["n_tx"] = pd.to_numeric(edges["n_tx"], errors="coerce").fillna(0).astype(int)
    tx["sum_kzt"] = pd.to_numeric(tx["sum_kzt"], errors="coerce").fillna(0.0)
    tx["date"] = pd.to_datetime(tx["date"], errors="coerce")
    nodes["depth"] = pd.to_numeric(nodes["depth"], errors="coerce").fillna(-1).astype(int)
    nodes["is_seed"] = nodes["is_seed"].fillna(False).astype(bool)
    return edges, nodes, tx


def build_graph(edges: pd.DataFrame, nodes: pd.DataFrame) -> nx.DiGraph:
    g = nx.DiGraph()
    for row in nodes.itertuples(index=False):
        g.add_node(int(row.gid), depth=int(row.depth), is_seed=bool(row.is_seed))
    for row in edges.itertuples(index=False):
        g.add_edge(int(row.src), int(row.dst), sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx))
    return g


def build_metrics(g: nx.DiGraph, edges: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    in_sum = edges.groupby("dst")["sum_kzt"].sum().to_dict()
    out_sum = edges.groupby("src")["sum_kzt"].sum().to_dict()
    pagerank = nx.pagerank(g, weight="sum_kzt")
    betweenness = nx.betweenness_centrality(g, weight=None, normalized=True)

    rows = []
    for gid in nodes["gid"].astype(int):
        incoming = float(in_sum.get(gid, 0.0))
        outgoing = float(out_sum.get(gid, 0.0))
        rows.append({
            "gid": gid,
            "depth": int(g.nodes[gid].get("depth", -1)),
            "is_seed": bool(g.nodes[gid].get("is_seed", False)),
            "in_degree": int(g.in_degree(gid)),
            "out_degree": int(g.out_degree(gid)),
            "in_sum_kzt": incoming,
            "out_sum_kzt": outgoing,
            "flow_ratio": safe_ratio(outgoing, incoming),
            "pagerank": float(pagerank.get(gid, 0.0)),
            "betweenness": float(betweenness.get(gid, 0.0)),
        })

    df = pd.DataFrame(rows)
    for c in ["in_degree", "out_degree", "in_sum_kzt", "out_sum_kzt", "pagerank", "betweenness"]:
        df[c + "_norm"] = minmax(df[c])
    return df


def add_clusters(g: nx.DiGraph, df: pd.DataFrame) -> pd.DataFrame:
    ug = nx.Graph()
    ug.add_nodes_from(g.nodes)
    for u, v, d in g.edges(data=True):
        w = float(d.get("sum_kzt", 1.0))
        if ug.has_edge(u, v):
            ug[u][v]["weight"] += w
        else:
            ug.add_edge(u, v, weight=w)

    try:
        communities = list(nx.community.louvain_communities(ug, weight="weight", seed=42))
    except Exception:
        communities = list(nx.community.greedy_modularity_communities(ug, weight="weight"))

    communities = sorted(communities, key=lambda c: (-len(c), min(c) if c else 0))
    cmap = {}
    for cid, community in enumerate(communities):
        for gid in community:
            cmap[int(gid)] = cid

    out = df.copy()
    out["cluster_id"] = out["gid"].map(cmap).fillna(-1).astype(int)
    return out


def add_roles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    q_in = max(3.0, float(out["in_degree"].quantile(0.90)))
    q_out = max(3.0, float(out["out_degree"].quantile(0.90)))
    q_pr = float(out["pagerank"].quantile(0.90))
    q_bw = float(out["betweenness"].quantile(0.90))

    roles, scores, evidence = [], [], []
    for r in out.itertuples(index=False):
        indeg, outdeg = int(r.in_degree), int(r.out_degree)
        incoming, outgoing = float(r.in_sum_kzt), float(r.out_sum_kzt)
        ratio, depth = float(r.flow_ratio), int(r.depth)

        if incoming > 0 and outgoing > 0 and r.pagerank >= q_pr and r.betweenness >= q_bw and indeg >= 2 and outdeg >= 2:
            role = "coordinator"
            score = clamp01(0.65 + 0.20 * r.pagerank_norm + 0.15 * r.betweenness_norm)
            why = f"Высокая центральность: in={indeg}, out={outdeg}; связывает несколько направлений потока."
        elif indeg >= q_in and incoming > 0:
            role = "consolidator"
            score = clamp01(0.60 + 0.20 * min(1.0, indeg / q_in) + 0.20 * r.in_sum_kzt_norm)
            why = f"Получает средства от {indeg} узлов; входящий поток {incoming:,.0f} KZT."
        elif outdeg >= q_out and outgoing > 0:
            role = "distributor"
            score = clamp01(0.60 + 0.20 * min(1.0, outdeg / q_out) + 0.20 * r.out_sum_kzt_norm)
            why = f"Распределяет средства на {outdeg} получателей; исходящий поток {outgoing:,.0f} KZT."
        elif incoming > 0 and outgoing > 0 and 0.80 <= ratio <= 1.20:
            role = "transit"
            score = max(0.60, clamp01(1.0 - abs(ratio - 1.0) / 0.20))
            why = f"Сквозной поток: out/in={ratio:.2f}; in={incoming:,.0f}, out={outgoing:,.0f} KZT."
        elif depth < 4 and incoming > 0 and outgoing <= incoming * 0.10:
            role = "terminal"
            score = clamp01(0.60 + 0.40 * (1.0 - safe_ratio(outgoing, incoming)))
            why = f"Средства в основном остаются: in={incoming:,.0f}, out={outgoing:,.0f} KZT; depth={depth}."
        else:
            role = "peripheral"
            score = 0.60
            if depth == 4 and outgoing == 0:
                why = "Периферия: depth=4 — граница выгрузки, поэтому отсутствие исходящих не доказывает terminal."
            else:
                why = f"Выраженной роли нет: in_degree={indeg}, out_degree={outdeg}."

        roles.append(role)
        scores.append(round(clamp01(score), 4))
        evidence.append(why[:200])

    out["role"] = roles
    out["role_score"] = scores
    out["evidence"] = evidence
    return out


def add_priority(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    role_bonus = {
        "coordinator": 1.00,
        "consolidator": 0.90,
        "distributor": 0.85,
        "transit": 0.70,
        "terminal": 0.55,
        "peripheral": 0.20,
    }
    activity = 0.30*out["in_degree_norm"] + 0.30*out["out_degree_norm"] + 0.20*out["in_sum_kzt_norm"] + 0.20*out["out_sum_kzt_norm"]
    centrality = 0.45*out["pagerank_norm"] + 0.55*out["betweenness_norm"]
    rb = out["role"].map(role_bonus).fillna(0.0)
    out["priority_score"] = (0.40*rb + 0.30*out["role_score"] + 0.15*activity + 0.15*centrality).clip(0,1).round(4)
    return out


def make_outputs(full: pd.DataFrame, edges: pd.DataFrame, out_dir: Path, top_n: int):
    nodes_roles = full[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]].copy()
    nodes_roles = nodes_roles.sort_values(["priority_score", "role_score"], ascending=False)

    cluster_rows = []
    for cid, part in full.groupby("cluster_id"):
        gids = set(part["gid"].astype(int))
        internal = edges[edges["src"].isin(gids) & edges["dst"].isin(gids)]
        top_gids = part.sort_values("priority_score", ascending=False)["gid"].head(5).astype(str).tolist()
        dominant = part["role"].value_counts().index[0] if len(part) else "unknown"
        cluster_rows.append({
            "cluster_id": int(cid),
            "n_nodes": int(len(part)),
            "n_seed": int(part["is_seed"].sum()),
            "sum_kzt_internal": round(float(internal["sum_kzt"].sum()), 2),
            "top_gids": ",".join(top_gids),
            "hypothesis": f"Кластер с преобладающей ролью {dominant}; узлов={len(part)}, seed={int(part['is_seed'].sum())}."
        })
    clusters = pd.DataFrame(cluster_rows).sort_values(["n_nodes", "sum_kzt_internal"], ascending=False)

    n = max(20, int(top_n))
    top = full.sort_values(["priority_score", "role_score"], ascending=False).head(n).copy()
    top.insert(0, "rank", range(1, len(top)+1))
    top["why"] = top["evidence"]
    top_nodes = top[["rank", "gid", "role", "priority_score", "why"]]

    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_roles.to_csv(out_dir / "nodes_roles.csv", index=False, encoding="utf-8-sig")
    clusters.to_csv(out_dir / "clusters.csv", index=False, encoding="utf-8-sig")
    top_nodes.to_csv(out_dir / "top_nodes.csv", index=False, encoding="utf-8-sig")
    return nodes_roles, clusters, top_nodes


def main():
    ap = argparse.ArgumentParser(description="QazLedger MoneyGraph: parquet -> CSV")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="output")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    edges, nodes, tx = load_data(Path(args.data))
    g = build_graph(edges, nodes)
    full = build_metrics(g, edges, nodes)
    full = add_clusters(g, full)
    full = add_roles(full)
    full = add_priority(full)
    nr, cl, tn = make_outputs(full, edges, Path(args.out), args.top)

    print("QazLedger MoneyGraph pipeline complete")
    print(f"nodes_roles.csv: {len(nr)} rows")
    print(f"clusters.csv: {len(cl)} rows")
    print(f"top_nodes.csv: {len(tn)} rows")


if __name__ == "__main__":
    main()
