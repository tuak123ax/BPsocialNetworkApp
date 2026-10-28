"""Phát hiện case bị BỎ SÓT task so với quy trình chuẩn trong file BPMN.

Ý tưởng: BPMN là nguồn chuẩn (source of truth) về trình tự các task. Với mỗi
case trong eventlog, nếu task liền trước (theo sequenceFlow trong BPMN) đã
được thực hiện xong nhưng task kế tiếp lại không hề xuất hiện trong case đó,
nhiều khả năng nhân viên phụ trách task liền trước đã quên chuyển tiếp / bỏ
sót task đó. Module này chỉ rõ: case nào, thiếu task gì, ai là người nhiều
khả năng đã bỏ sót (người vừa hoàn thành task ngay trước đó) và khi nào.

Nếu KHÔNG task liền trước nào được thực hiện trong case (ví dụ case đi theo
một nhánh rẽ khác của gateway) thì KHÔNG coi là bất thường — vì task đó vốn
không cần thực hiện ở nhánh này.
"""
from __future__ import annotations

import pandas as pd

from .bpmn_parser import BpmnModel

MISSING_DETAIL_COLS = [
    "Case",
    "Mã task bị thiếu",
    "Task bị thiếu",
    "Task liền trước đã hoàn thành",
    "Nhân viên nghi ngờ bỏ sót",
    "Hoàn thành task liền trước lúc",
    "Các nhân viên đã tham gia case",
]

# Cột theo đúng định dạng eventlog.csv "rộng" mà ứng dụng đọc được, để người
# dùng có thể sao chép/dán thẳng các dòng gợi ý vào file eventlog.csv gốc.
EVENTLOG_ADDENDUM_COLS = [
    "caseId", "taskId", "activity", "startTime", "endTime", "finishTime",
    "personName", "ghi_chu",
]

MISSING_BY_EMPLOYEE_COLS = [
    "Nhân viên nghi ngờ bỏ sót",
    "Số lần bị nghi bỏ sót task",
    "Số case liên quan",
    "Các task hay bị bỏ sót",
]


def _match_task(row, id_idx: dict, name_idx: dict):
    """Khớp 1 dòng eventlog (đã có task_id/activity) với BpmnTask, ưu tiên id."""
    tid = str(row.get("task_id") or "").strip()
    if tid and tid.lower() not in ("", "nan", "none") and tid in id_idx:
        return id_idx[tid]
    raw = str(row.get("activity") or "").strip()
    if raw in id_idx:
        return id_idx[raw]
    key = raw.lower()
    if key in name_idx:
        return name_idx[key]
    return None


def detect_missing_tasks(bpmn: BpmnModel, wide_eventlog: pd.DataFrame) -> dict:
    """Trả về {"detail": DataFrame, "by_employee": DataFrame}."""
    if wide_eventlog is None or wide_eventlog.empty or "case_id" not in wide_eventlog.columns:
        return {
            "detail": pd.DataFrame(columns=MISSING_DETAIL_COLS),
            "by_employee": pd.DataFrame(columns=MISSING_BY_EMPLOYEE_COLS),
        }

    df = wide_eventlog.copy()
    if "task_id" not in df.columns:
        df["task_id"] = None

    id_idx = bpmn.id_index()
    name_idx = bpmn.name_index()
    df["_bpmn_task"] = df.apply(lambda r: _match_task(r, id_idx, name_idx), axis=1)
    df["_bpmn_task_id"] = df["_bpmn_task"].apply(lambda t: t.id if t is not None else None)

    rows = []
    for case_id, g in df.groupby("case_id"):
        matched = g[g["_bpmn_task_id"].notna()]
        if matched.empty:
            continue  # không đối chiếu được task nào với BPMN -> bỏ qua case này

        # với mỗi task_id, lấy dòng hoàn thành SAU CÙNG trong case (nếu lặp lại nhiều lần)
        last_by_task = (
            matched.sort_values("end_time").groupby("_bpmn_task_id", as_index=True).tail(1)
            .set_index("_bpmn_task_id")
        )
        executed_ids = set(last_by_task.index)
        all_resources = sorted(set(g["resource"].dropna().astype(str))) if "resource" in g.columns else []

        for t in bpmn.tasks:
            if not t.id or t.id in executed_ids:
                continue
            alternatives = bpmn.exclusive_alternatives.get(t.id, set())
            if alternatives & executed_ids:
                continue  # case đã đi nhánh KHÁC (loại trừ lẫn nhau) của cùng gateway -> không phải bất thường
            preds = bpmn.predecessors.get(t.id, [])
            done_preds = [p for p in preds if p in executed_ids]
            if preds and not done_preds:
                continue  # nhánh này của quy trình chưa được case đi tới -> không phải bất thường

            if done_preds:
                # chọn task liền trước hoàn thành MUỘN NHẤT làm điểm "đáng lẽ phải chuyển tiếp"
                best_pred_id = max(done_preds, key=lambda p: last_by_task.loc[p, "end_time"])
                pred_row = last_by_task.loc[best_pred_id]
                pred_name = id_idx[best_pred_id].name if best_pred_id in id_idx else best_pred_id
                suspect = str(pred_row.get("resource") or "(không rõ)")
                finished_at = pred_row.get("end_time")
            else:
                # t không có task liền trước nào trong BPMN (task đầu quy trình)
                # nhưng case đã có hoạt động khác -> vẫn coi là bất thường, chưa rõ ai phụ trách
                pred_name = "(đầu quy trình)"
                suspect = "(chưa xác định)"
                finished_at = None

            rows.append(
                {
                    "Case": case_id,
                    "Mã task bị thiếu": t.id,
                    "Task bị thiếu": t.name,
                    "Task liền trước đã hoàn thành": pred_name,
                    "Nhân viên nghi ngờ bỏ sót": suspect,
                    "Hoàn thành task liền trước lúc": finished_at,
                    "Các nhân viên đã tham gia case": ", ".join(all_resources),
                }
            )

    detail = pd.DataFrame(rows, columns=MISSING_DETAIL_COLS)
    if not detail.empty:
        detail = detail.sort_values(["Nhân viên nghi ngờ bỏ sót", "Case"]).reset_index(drop=True)

    if detail.empty:
        by_employee = pd.DataFrame(columns=MISSING_BY_EMPLOYEE_COLS)
    else:
        def _agg(g):
            return pd.Series(
                {
                    "Số lần bị nghi bỏ sót task": len(g),
                    "Số case liên quan": g["Case"].nunique(),
                    "Các task hay bị bỏ sót": ", ".join(sorted(set(g["Task bị thiếu"]))),
                }
            )

        by_employee = (
            detail.groupby("Nhân viên nghi ngờ bỏ sót", as_index=False)
            .apply(_agg, include_groups=False)
            .sort_values("Số lần bị nghi bỏ sót task", ascending=False)
            .reset_index(drop=True)
        )
        by_employee = by_employee[MISSING_BY_EMPLOYEE_COLS]

    return {"detail": detail, "by_employee": by_employee}


def build_eventlog_addendum(missing_detail: pd.DataFrame) -> pd.DataFrame:
    """Chuyển bảng "task bị thiếu" (`detect_missing_tasks(...)["detail"]`)
    thành các dòng theo đúng định dạng eventlog.csv "rộng" (caseId, taskId,
    activity, startTime, endTime, finishTime, personName), kèm cột ghi chú,
    để người dùng chỉ cần xác nhận/điền thêm rồi dán thẳng vào eventlog.csv.

    `startTime` được gợi ý = thời điểm hoàn thành task liền trước (điểm sớm
    nhất công việc này có thể bắt đầu); `endTime`/`finishTime` để trống vì
    ứng dụng không có dữ liệu thời gian thực tế của task bị thiếu.
    """
    if missing_detail is None or missing_detail.empty:
        return pd.DataFrame(columns=EVENTLOG_ADDENDUM_COLS)

    rows = []
    for _, r in missing_detail.iterrows():
        suspect = r["Nhân viên nghi ngờ bỏ sót"]
        person = "" if suspect in ("(chưa xác định)", "(không rõ)") else suspect
        start = r["Hoàn thành task liền trước lúc"]
        start_txt = "" if pd.isna(start) else str(start)
        ghi_chu = (
            f"Nghi thiếu sau khi hoàn thành \"{r['Task liền trước đã hoàn thành']}\""
            f"{' lúc ' + start_txt if start_txt else ''}. "
            "Vui lòng xác nhận người thực hiện, điền endTime/finishTime thực tế rồi mới thêm vào eventlog.csv."
        )
        rows.append(
            {
                "caseId": r["Case"],
                "taskId": r["Mã task bị thiếu"],
                "activity": r["Task bị thiếu"],
                "startTime": start_txt,
                "endTime": "",
                "finishTime": "",
                "personName": person,
                "ghi_chu": ghi_chu,
            }
        )
    return pd.DataFrame(rows, columns=EVENTLOG_ADDENDUM_COLS)
