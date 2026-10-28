"""Build a social network (organizational network) from the event log and
compute its structural metrics.

Two well-known process-mining network types are supported:

* "handover" — directed, weighted graph. An edge A -> B is added every time
  resource A finishes a task and resource B performs the very next task in
  the same case (classic "handover of work" network).
* "collaboration" — undirected, weighted graph. An edge A - B is added,
  weighted by the number of distinct cases where both A and B worked
  (regardless of order): who works together with whom.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd


def build_handover_graph(eventlog: pd.DataFrame) -> nx.DiGraph:
    """eventlog: columns case_id, activity, resource, start_time, end_time."""
    G = nx.DiGraph()
    for resource in eventlog["resource"].dropna().unique():
        G.add_node(resource)

    for case_id, group in eventlog.sort_values("start_time").groupby("case_id"):
        resources = group["resource"].tolist()
        for a, b in zip(resources, resources[1:]):
            if pd.isna(a) or pd.isna(b) or a == b:
                continue  # bỏ qua "bàn giao cho chính mình" (không phải handover thật)
            if G.has_edge(a, b):
                G[a][b]["weight"] += 1
            else:
                G.add_edge(a, b, weight=1)
    return G


def build_collaboration_graph(eventlog: pd.DataFrame) -> nx.Graph:
    """Undirected graph: edge weight = number of distinct cases two
    resources both worked on."""
    G = nx.Graph()
    for resource in eventlog["resource"].dropna().unique():
        G.add_node(resource)

    for case_id, group in eventlog.groupby("case_id"):
        people = sorted(set(group["resource"].dropna().tolist()))
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                a, b = people[i], people[j]
                if G.has_edge(a, b):
                    G[a][b]["weight"] += 1
                else:
                    G.add_edge(a, b, weight=1)
    return G


def compute_node_metrics(G) -> pd.DataFrame:
    """Return a dataframe with one row per node and standard SNA metrics.
    Works for both directed (handover) and undirected (collaboration) graphs.
    """
    directed = G.is_directed()
    n = G.number_of_nodes()

    rows = []
    if n == 0:
        return pd.DataFrame()

    degree_centrality = nx.degree_centrality(G)
    try:
        betweenness = nx.betweenness_centrality(G, weight="weight")
    except Exception:  # noqa: BLE001
        betweenness = {node: 0.0 for node in G.nodes}
    try:
        closeness = nx.closeness_centrality(G)
    except Exception:  # noqa: BLE001
        closeness = {node: 0.0 for node in G.nodes}
    try:
        pagerank = nx.pagerank(G, weight="weight")
    except Exception:  # noqa: BLE001
        pagerank = {node: 0.0 for node in G.nodes}

    if directed:
        in_w = dict(G.in_degree(weight="weight"))
        out_w = dict(G.out_degree(weight="weight"))
    else:
        deg_w = dict(G.degree(weight="weight"))

    for node in G.nodes:
        row = {"Nhân viên": node}
        if directed:
            row["Bậc vào (In-degree)"] = G.in_degree(node)
            row["Bậc ra (Out-degree)"] = G.out_degree(node)
            row["Tổng lượt nhận việc"] = in_w.get(node, 0)
            row["Tổng lượt bàn giao"] = out_w.get(node, 0)
        else:
            row["Bậc (Degree)"] = G.degree(node)
            row["Tổng số lượt tương tác"] = deg_w.get(node, 0)
        row["Độ trung tâm bậc (Degree centrality)"] = round(degree_centrality.get(node, 0), 4)
        row["Độ trung tâm trung gian (Betweenness)"] = round(betweenness.get(node, 0), 4)
        row["Độ trung tâm gần (Closeness)"] = round(closeness.get(node, 0), 4)
        row["PageRank"] = round(pagerank.get(node, 0), 4)
        rows.append(row)

    df = pd.DataFrame(rows)
    sort_col = "Độ trung tâm bậc (Degree centrality)"
    return df.sort_values(sort_col, ascending=False).reset_index(drop=True)


def compute_overall_metrics(G) -> dict:
    """Return a dict of network-level (whole-graph) statistics.

    Chỉ giữ lại các chỉ số dễ hiểu/hữu ích để nhìn nhanh bức tranh tổng thể
    và chỉ đích danh nhân viên nổi bật theo 3 loại độ trung tâm quan trọng
    nhất (bậc, trung gian, gần) — bỏ các chỉ số kỹ thuật ít giá trị hành
    động hơn (bậc trung bình, số thành phần liên thông, hệ số phân cụm...).
    """
    n = G.number_of_nodes()
    e = G.number_of_edges()
    directed = G.is_directed()

    metrics = {
        "Số nút (nhân viên)": n,
        "Số cạnh (quan hệ)": e,
        "Mật độ mạng (Density)": round(nx.density(G), 4) if n > 1 else 0.0,
    }

    if n > 0:
        total_weight = sum(d.get("weight", 1) for _, _, d in G.edges(data=True))
        metrics["Tổng số lượt tương tác"] = total_weight

    if directed:
        metrics["Liên thông mạnh (Strongly connected)"] = "Có" if nx.is_strongly_connected(G) else "Không"
    else:
        metrics["Liên thông (Connected)"] = "Có" if nx.is_connected(G) else "Không"

    if n > 0:
        def _top(label: str, values: dict):
            if not values:
                return
            top = max(values, key=values.get)
            metrics[label] = f"{top} ({values[top]:.2f})"

        try:
            _top("Nhân viên trung tâm nhất (Degree)", nx.degree_centrality(G))
        except Exception:  # noqa: BLE001
            pass
        try:
            _top("Nhân viên trung gian nhiều nhất (Betweenness)", nx.betweenness_centrality(G, weight="weight"))
        except Exception:  # noqa: BLE001
            pass
        try:
            _top("Nhân viên gần trung tâm nhất (Closeness)", nx.closeness_centrality(G))
        except Exception:  # noqa: BLE001
            pass

    return metrics
