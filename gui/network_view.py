"""Tab hiển thị mạng xã hội (social network) suy ra từ eventlog: vẽ đồ thị và
bảng các chỉ số cấu trúc mạng (degree, betweenness, closeness, density...).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import networkx as nx
import pandas as pd

from core.social_network import (
    build_handover_graph,
    build_collaboration_graph,
    compute_node_metrics,
    compute_overall_metrics,
)

MODE_HANDOVER = "Bàn giao công việc (handover)"
MODE_COLLAB = "Cùng xử lý case (collaboration)"


class NetworkView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.eventlog = pd.DataFrame()
        self._graphs = {}

        self._build_widgets()

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(side="top", fill="x")

        ttk.Label(top, text="Loại mạng:").pack(side="left")
        self.mode_var = tk.StringVar(value=MODE_HANDOVER)
        mode_cb = ttk.Combobox(
            top, textvariable=self.mode_var, state="readonly",
            values=[MODE_HANDOVER, MODE_COLLAB], width=32,
        )
        mode_cb.pack(side="left", padx=(6, 12))
        mode_cb.bind("<<ComboboxSelected>>", lambda e: self._render())

        self.info_var = tk.StringVar(value="Chưa có dữ liệu. Hãy bấm 'Tính hiệu suất' ở trên trước.")
        ttk.Label(top, textvariable=self.info_var, foreground="#666666").pack(side="left")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Left: graph drawing --------------------------------------------
        graph_frame = ttk.Frame(body)
        body.add(graph_frame, weight=3)

        self.figure = plt.Figure(figsize=(6, 5), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Right: metrics ----------------------------------------------------
        right = ttk.Frame(body)
        body.add(right, weight=2)

        ttk.Label(right, text="Chỉ số tổng quan mạng", font=("", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.overall_text = tk.Text(right, height=10, wrap="word", relief="solid", borderwidth=1)
        self.overall_text.pack(fill="x", pady=(0, 10))
        self.overall_text.configure(state="disabled")

        ttk.Label(right, text="Chỉ số theo từng nhân viên", font=("", 10, "bold")).pack(anchor="w", pady=(0, 4))

        table_frame = ttk.Frame(right)
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, show="headings")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    # --------------------------------------------------------------- logic
    def set_eventlog(self, eventlog: pd.DataFrame):
        """eventlog: normalized wide dataframe (case_id, activity, resource,
        start_time, end_time), as produced by data_loader.build_wide_eventlog."""
        self.eventlog = eventlog
        self._graphs = {}
        if eventlog is None or eventlog.empty:
            self.info_var.set("Không có dữ liệu eventlog hợp lệ để dựng mạng.")
            return
        n_resources = eventlog["resource"].nunique()
        n_cases = eventlog["case_id"].nunique()
        self.info_var.set(f"{n_resources} nhân viên, {n_cases} case, {len(eventlog)} sự kiện.")
        self._render()

    def _get_graph(self):
        mode = self.mode_var.get()
        if mode not in self._graphs:
            if mode == MODE_HANDOVER:
                self._graphs[mode] = build_handover_graph(self.eventlog)
            else:
                self._graphs[mode] = build_collaboration_graph(self.eventlog)
        return self._graphs[mode]

    def _render(self):
        self.ax.clear()
        if self.eventlog is None or self.eventlog.empty:
            self.canvas.draw()
            return

        G = self._get_graph()
        directed = G.is_directed()

        if G.number_of_nodes() == 0:
            self.ax.text(0.5, 0.5, "Không có dữ liệu", ha="center", va="center")
            self.canvas.draw()
            self._set_overall_text({})
            self._set_table(pd.DataFrame())
            return

        pos = nx.spring_layout(G, seed=42, weight="weight", k=1.2 / max(1, G.number_of_nodes() ** 0.5))

        weights = [d.get("weight", 1) for _, _, d in G.edges(data=True)]
        max_w = max(weights) if weights else 1
        widths = [0.6 + 3.0 * (w / max_w) for w in weights]

        degree_centrality = nx.degree_centrality(G)
        max_dc = max(degree_centrality.values()) if degree_centrality else 1
        node_sizes = [400 + 1600 * (degree_centrality.get(n, 0) / max_dc if max_dc else 0) for n in G.nodes]

        nx.draw_networkx_nodes(G, pos, ax=self.ax, node_size=node_sizes, node_color="#6fa8dc", edgecolors="#2f5f8f")
        nx.draw_networkx_labels(G, pos, ax=self.ax, font_size=8)
        nx.draw_networkx_edges(
            G, pos, ax=self.ax, width=widths, edge_color="#999999",
            arrows=True, arrowstyle="-|>" if directed else "-", arrowsize=14,
            connectionstyle="arc3,rad=0.08",
        )
        edge_labels = {(u, v): d.get("weight", 1) for u, v, d in G.edges(data=True)}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, ax=self.ax, font_size=7)

        self.ax.set_axis_off()
        self.ax.set_title(self.mode_var.get(), fontsize=10)
        self.figure.tight_layout()
        self.canvas.draw()

        self._set_overall_text(compute_overall_metrics(G))
        self._set_table(compute_node_metrics(G))

    def _set_overall_text(self, metrics: dict):
        self.overall_text.configure(state="normal")
        self.overall_text.delete("1.0", "end")
        for k, v in metrics.items():
            self.overall_text.insert("end", f"{k}: {v}\n")
        self.overall_text.configure(state="disabled")

    def _set_table(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(df.columns)
        for col in df.columns:
            self.tree.heading(col, text=col)
            width = max(90, min(200, 10 + 8 * len(str(col))))
            self.tree.column(col, width=width, anchor="center")
        for _, row in df.iterrows():
            self.tree.insert("", "end", values=list(row))
