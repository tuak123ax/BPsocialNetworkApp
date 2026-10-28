"""Generic modal dialog letting the user map dataframe columns to the fields
the analyzer needs, used as a fallback when auto-detection fails or the user
wants to double check it.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

NONE_LABEL = "-- Không chọn --"


class ColumnMappingDialog(tk.Toplevel):
    """fields: list of dicts: {key, label, detected (optional str), required (bool)}
    extra_widgets: optional callable(frame) -> dict of {key: tk.Variable} for
        extra controls (e.g. a default time-unit combobox).
    """

    def __init__(self, parent, title: str, columns: list, fields: list, extra: dict | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None
        self._vars = {}

        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text=title, font=("", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        options = [NONE_LABEL] + list(columns)
        row = 1
        for f in fields:
            label = f["label"] + (" *" if f.get("required") else "")
            ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            var = tk.StringVar(value=f.get("detected") or NONE_LABEL)
            cb = ttk.Combobox(container, textvariable=var, values=options, state="readonly", width=32)
            cb.grid(row=row, column=1, sticky="ew", pady=4)
            self._vars[f["key"]] = var
            row += 1

        self._extra_vars = {}
        if extra:
            for key, (label, values, default) in extra.items():
                ttk.Label(container, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
                var = tk.StringVar(value=default)
                cb = ttk.Combobox(container, textvariable=var, values=values, state="readonly", width=32)
                cb.grid(row=row, column=1, sticky="ew", pady=4)
                self._extra_vars[key] = var
                row += 1

        note = ttk.Label(
            container,
            text="(*) bắt buộc. Với eventlog: cần Start+End, hoặc Timestamp+Lifecycle transition.",
            foreground="#666666",
            wraplength=360,
        )
        note.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 10))
        row += 1

        btns = ttk.Frame(container)
        btns.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Hủy", command=self._on_cancel).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_visibility()
        self.center_on(parent)

    def center_on(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")

    def _on_ok(self):
        mapping = {}
        for key, var in self._vars.items():
            val = var.get()
            mapping[key] = None if val == NONE_LABEL else val
        for key, var in self._extra_vars.items():
            mapping[key] = var.get()
        self.result = mapping
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


def ask_eventlog_mapping(parent, columns, detected):
    fields = [
        {"key": "case", "label": "Case ID", "detected": detected.get("case"), "required": True},
        {"key": "task_id", "label": "Task ID (nếu có)", "detected": detected.get("task_id"), "required": False},
        {"key": "activity", "label": "Activity / Task", "detected": detected.get("activity"), "required": True},
        {"key": "resource", "label": "Resource / Nhân viên", "detected": detected.get("resource"), "required": True},
        {"key": "start", "label": "Start time (định dạng rộng)", "detected": detected.get("start"), "required": False},
        {"key": "end", "label": "End time (định dạng rộng)", "detected": detected.get("end"), "required": False},
        {"key": "timestamp", "label": "Timestamp (định dạng dài)", "detected": detected.get("timestamp"), "required": False},
        {"key": "transition", "label": "Lifecycle transition (định dạng dài)", "detected": detected.get("transition"), "required": False},
    ]
    dlg = ColumnMappingDialog(parent, "Ánh xạ cột - eventlog.csv", columns, fields)
    parent.wait_window(dlg)
    return dlg.result


def ask_standard_time_mapping(parent, columns, detected):
    fields = [
        {"key": "task_id", "label": "Task ID (nếu có)", "detected": detected.get("task_id"), "required": False},
        {"key": "task", "label": "Task / Loại công việc", "detected": detected.get("task"), "required": True},
        {"key": "standard_time", "label": "Thời gian chuẩn (số)", "detected": detected.get("standard_time"), "required": True},
        {"key": "unit", "label": "Đơn vị (cột, nếu có)", "detected": detected.get("unit"), "required": False},
    ]
    extra = {
        "default_unit": ("Đơn vị mặc định (nếu không có cột đơn vị)", ["minutes", "hours", "days"], "minutes"),
    }
    dlg = ColumnMappingDialog(parent, "Ánh xạ cột - standardTime.csv", columns, fields, extra=extra)
    parent.wait_window(dlg)
    return dlg.result
