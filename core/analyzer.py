"""Core computation: employee performance per task type, with a late-rate
column, cross-referencing the BPMN model, the event log and the standard
time table.
"""
from __future__ import annotations

import pandas as pd

from .bpmn_parser import BpmnModel


def _canonical_task(activity: str, bpmn: BpmnModel, task_id: str | None = None) -> tuple:
    """Map a raw activity string (và task_id nếu có) từ eventlog sang tên task
    chuẩn theo BPMN. Ưu tiên đối chiếu theo task_id (chính xác hơn) trước khi
    dùng activity (theo id rồi theo tên, không phân biệt hoa/thường).
    Returns (canonical_name, bpmn_type, in_bpmn: bool).
    """
    id_idx = bpmn.id_index()
    name_idx = bpmn.name_index()

    tid = (task_id or "").strip()
    if tid and tid.lower() not in ("", "nan", "none") and tid in id_idx:
        t = id_idx[tid]
        return t.name, t.element_type, True

    raw = (activity or "").strip()
    if raw in id_idx:
        t = id_idx[raw]
        return t.name, t.element_type, True

    key = raw.lower()
    if key in name_idx:
        t = name_idx[key]
        return t.name, t.element_type, True

    return raw, "(không có trong BPMN)", False


def compute_performance(
    eventlog: pd.DataFrame,
    standard_time: pd.DataFrame,
    bpmn: BpmnModel,
) -> pd.DataFrame:
    """eventlog: columns case_id, activity, resource, start_time, end_time.
    standard_time: columns task, standard_minutes.
    bpmn: parsed BpmnModel.

    Returns a dataframe with one row per (employee, task) with performance
    metrics, including a "Tỷ lệ trễ hạn (%)" column.
    """
    if eventlog.empty:
        raise ValueError("Eventlog rỗng hoặc không đọc được dữ liệu hợp lệ.")

    df = eventlog.copy()
    has_task_id_col = "task_id" in df.columns
    if not has_task_id_col:
        df["task_id"] = None
    canon = df.apply(lambda r: _canonical_task(r["activity"], bpmn, r.get("task_id")), axis=1)
    df["task"] = canon.apply(lambda x: x[0])
    df["bpmn_type"] = canon.apply(lambda x: x[1])
    df["in_bpmn"] = canon.apply(lambda x: x[2])

    df["actual_minutes"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60.0
    df = df[df["actual_minutes"] >= 0]

    std_by_name = standard_time.set_index(
        standard_time["task"].str.strip().str.lower()
    )["standard_minutes"].to_dict()
    std_by_id = {}
    if "task_id" in standard_time.columns:
        st_id = standard_time[standard_time["task_id"].notna()]
        st_id = st_id[st_id["task_id"].astype(str).str.strip().str.lower().isin(["", "nan", "none"]) == False]
        std_by_id = st_id.set_index(st_id["task_id"].astype(str).str.strip())["standard_minutes"].to_dict()

    def lookup_standard(row):
        tid = str(row.get("task_id") or "").strip()
        if tid and tid.lower() not in ("", "nan", "none") and tid in std_by_id:
            return std_by_id[tid]
        return std_by_name.get((row["task"] or "").strip().lower())

    df["standard_minutes"] = df.apply(lookup_standard, axis=1)
    df["has_standard"] = df["standard_minutes"].notna()
    df["is_late"] = df["has_standard"] & (df["actual_minutes"] > df["standard_minutes"])

    grouped = df.groupby(["resource", "task", "bpmn_type"], as_index=False)

    result = grouped.agg(
        so_luong_cong_viec=("actual_minutes", "count"),
        thoi_gian_chuan=("standard_minutes", "mean"),
        so_lan_tre_han=("is_late", "sum"),
    )

    result["ty_le_tre_han_%"] = (result["so_lan_tre_han"] / result["so_luong_cong_viec"] * 100).round(2)

    result = result.rename(
        columns={
            "resource": "Nhân viên",
            "task": "Loại task",
            "so_luong_cong_viec": "Số lượng công việc",
            "thoi_gian_chuan": "Thời gian chuẩn TB (phút)",
            "so_lan_tre_han": "Số lần trễ hạn",
            "ty_le_tre_han_%": "Tỷ lệ trễ hạn (%)",
        }
    )

    result["Thời gian chuẩn TB (phút)"] = result["Thời gian chuẩn TB (phút)"].round(2)

    ordered_cols = [
        "Nhân viên", "Loại task",
        "Số lượng công việc", "Thời gian chuẩn TB (phút)",
        "Số lần trễ hạn", "Tỷ lệ trễ hạn (%)",
    ]
    result = result[ordered_cols].sort_values(["Nhân viên", "Loại task"]).reset_index(drop=True)
    return result


def compute_employee_summary(detail: pd.DataFrame) -> pd.DataFrame:
    """Roll the per-(employee, task) table up to one row per employee."""
    if detail.empty:
        return detail

    g = detail.groupby("Nhân viên", as_index=False).agg(
        **{
            "Tổng công việc": ("Số lượng công việc", "sum"),
            "Tổng số lần trễ hạn": ("Số lần trễ hạn", "sum"),
        }
    )
    g["Tổng số lần đúng hạn"] = g["Tổng công việc"] - g["Tổng số lần trễ hạn"]
    g["Tỷ lệ trễ hạn (%)"] = (g["Tổng số lần trễ hạn"] / g["Tổng công việc"] * 100).round(2)
    g = g[["Nhân viên", "Tổng công việc", "Tổng số lần đúng hạn", "Tổng số lần trễ hạn", "Tỷ lệ trễ hạn (%)"]]
    return g.sort_values("Nhân viên").reset_index(drop=True)
