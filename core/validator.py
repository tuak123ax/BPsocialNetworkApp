"""Kiểm tra 3 file đầu vào (BPMN, eventlog, standardTime) có khớp và làm việc
được với nhau hay không, trước/độc lập với việc tính hiệu suất.

Không raise lỗi cho các vấn đề "mềm" (task lạ, thiếu standard time...) — chỉ
tổng hợp thành báo cáo issues/warnings/infos để người dùng tự quyết định có
tiếp tục tính hay không. Chỉ những vấn đề khiến việc tính toán chắc chắn sai/
không chạy được mới xếp vào "issues" (lỗi).
"""
from __future__ import annotations

import pandas as pd

from .analyzer import _canonical_task
from .bpmn_parser import BpmnModel


def validate_consistency(
    bpmn: BpmnModel,
    wide_eventlog: pd.DataFrame,
    standard_table: pd.DataFrame,
    n_raw_events: int | None = None,
) -> dict:
    """Trả về dict:
    {n_bpmn_tasks, n_events, n_cases, n_resources, n_standard_rows,
     issues: [str], warnings: [str], infos: [str], ok: bool}
    `ok=False` nghĩa là có lỗi có thể khiến việc tính hiệu suất sai/không
    chạy được (khác với warnings chỉ là các điểm cần lưu ý).
    """
    issues: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    n_bpmn_tasks = len(bpmn.tasks)

    if wide_eventlog is None or wide_eventlog.empty:
        issues.append(
            "Eventlog không có dòng dữ liệu hợp lệ nào (sau khi loại các dòng "
            "thiếu case/activity/resource hoặc không đọc được thời gian bắt đầu/kết thúc)."
        )
        return {
            "n_bpmn_tasks": n_bpmn_tasks, "n_events": 0, "n_cases": 0, "n_resources": 0,
            "n_standard_rows": len(standard_table) if standard_table is not None else 0,
            "issues": issues, "warnings": warnings, "infos": infos, "ok": False,
        }

    df = wide_eventlog.copy()
    if "task_id" not in df.columns:
        df["task_id"] = None

    canon = df.apply(lambda r: _canonical_task(r.get("activity"), bpmn, r.get("task_id")), axis=1)
    df["canonical_task"] = canon.apply(lambda x: x[0])
    df["in_bpmn"] = canon.apply(lambda x: x[2])

    n_events = len(df)
    n_cases = df["case_id"].nunique() if "case_id" in df.columns else 0
    n_resources = df["resource"].nunique() if "resource" in df.columns else 0

    if n_raw_events is not None and n_raw_events > n_events:
        dropped = n_raw_events - n_events
        warnings.append(
            f"{dropped}/{n_raw_events} dòng trong eventlog.csv bị loại vì thiếu dữ liệu "
            "hoặc không đọc được ngày giờ bắt đầu/kết thúc."
        )

    # 1) Eventlog có activity/taskId không khớp BPMN nào ------------------
    unmatched = df[~df["in_bpmn"]]
    if not unmatched.empty:
        counts = unmatched.groupby("activity").size().sort_values(ascending=False)
        total = int(counts.sum())
        detail = ", ".join(f"{name} ({cnt})" for name, cnt in counts.items())
        warnings.append(
            f"{total} sự kiện trong eventlog có activity/taskId KHÔNG khớp task nào trong BPMN: {detail}. "
            "Các dòng này vẫn được tính nhưng không dùng được tên/id chuẩn hoá từ BPMN."
        )

    # 2) Task trong BPMN chưa từng xuất hiện trong eventlog ----------------
    matched_names = set(df.loc[df["in_bpmn"], "canonical_task"].unique())
    bpmn_task_names = {t.name for t in bpmn.tasks}
    bpmn_not_in_eventlog = sorted(bpmn_task_names - matched_names)
    if bpmn_not_in_eventlog:
        warnings.append(
            f"{len(bpmn_not_in_eventlog)} task trong BPMN chưa từng xuất hiện trong eventlog: "
            + ", ".join(bpmn_not_in_eventlog)
        )

    # 3) standardTime.csv có dòng nào không khớp task nào trong BPMN -------
    std = standard_table.copy() if standard_table is not None else pd.DataFrame(columns=["task"])
    n_standard_rows = len(std)
    id_idx = bpmn.id_index()
    name_idx = bpmn.name_index()

    def _std_matches_bpmn(row) -> bool:
        tid = str(row.get("task_id") or "").strip()
        if tid and tid.lower() not in ("", "nan", "none") and tid in id_idx:
            return True
        name = str(row.get("task") or "").strip().lower()
        return name in name_idx

    if not std.empty:
        std["_matches_bpmn"] = std.apply(_std_matches_bpmn, axis=1)
        std_not_in_bpmn = std.loc[~std["_matches_bpmn"], "task"].tolist()
        if std_not_in_bpmn:
            warnings.append(
                f"{len(std_not_in_bpmn)} dòng trong standardTime.csv không khớp task nào trong BPMN: "
                + ", ".join(std_not_in_bpmn)
            )
    else:
        issues.append("standardTime.csv không có dòng dữ liệu hợp lệ nào.")

    # 4) Eventlog có task chưa có standard time (sẽ không tính được trễ hạn)
    std_by_name = set(std["task"].astype(str).str.strip().str.lower()) if not std.empty else set()
    std_by_id = set()
    if not std.empty and "task_id" in std.columns:
        ids = std.loc[std["task_id"].notna(), "task_id"].astype(str).str.strip()
        std_by_id = set(ids[~ids.str.lower().isin(["", "nan", "none"])])

    def _has_standard(row) -> bool:
        tid = str(row.get("task_id") or "").strip()
        if tid and tid.lower() not in ("", "nan", "none") and tid in std_by_id:
            return True
        return (row.get("canonical_task") or "").strip().lower() in std_by_name

    df["_has_standard"] = df.apply(_has_standard, axis=1)
    missing_std = df[~df["_has_standard"]]
    if not missing_std.empty:
        counts = missing_std.groupby("canonical_task").size().sort_values(ascending=False)
        total = int(counts.sum())
        detail = ", ".join(f"{name} ({cnt})" for name, cnt in counts.items())
        warnings.append(
            f"{total} sự kiện thuộc các task CHƯA có Standard Time tương ứng "
            f"(sẽ không tính được trễ hạn cho các sự kiện này): {detail}"
        )

    # 5) standardTime.csv có dòng không được task nào trong eventlog dùng đến
    if not std.empty:
        used_names = set(df["canonical_task"].astype(str).str.strip().str.lower().unique())
        used_ids = set(df["task_id"].dropna().astype(str).str.strip().unique())

        def _std_unused(row) -> bool:
            tid = str(row.get("task_id") or "").strip()
            if tid and tid in used_ids:
                return False
            name = str(row.get("task") or "").strip().lower()
            return name not in used_names

        std["_unused"] = std.apply(_std_unused, axis=1)
        unused_list = std.loc[std["_unused"], "task"].tolist()
        if unused_list:
            infos.append(
                f"{len(unused_list)} dòng trong standardTime.csv chưa được dùng đến "
                "(không có sự kiện eventlog nào thuộc task này): " + ", ".join(unused_list)
            )

    # 6) Thời gian kết thúc trước thời gian bắt đầu ------------------------
    if "start_time" in df.columns and "end_time" in df.columns:
        negative = int(((df["end_time"] - df["start_time"]).dt.total_seconds() < 0).sum())
        if negative:
            issues.append(
                f"{negative} sự kiện có thời gian kết thúc SỚM HƠN thời gian bắt đầu — "
                "dữ liệu có thể bị sai; các dòng này sẽ bị loại khi tính hiệu suất."
            )

    return {
        "n_bpmn_tasks": n_bpmn_tasks,
        "n_events": n_events,
        "n_cases": n_cases,
        "n_resources": n_resources,
        "n_standard_rows": n_standard_rows,
        "issues": issues,
        "warnings": warnings,
        "infos": infos,
        "ok": not issues,
    }
