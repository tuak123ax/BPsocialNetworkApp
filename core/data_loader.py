"""Load and normalize eventlog.csv and standardTime.csv.

Both files can come in slightly different shapes (different column names,
different date formats, long vs wide event logs). This module tries to
auto-detect the right columns and falls back to letting the caller supply an
explicit mapping (see gui/column_mapping_dialog.py).
"""
from __future__ import annotations

import pandas as pd

# Candidate column names (lower-cased) for auto-detection -------------------

CASE_CANDIDATES = ["case_id", "case id", "case", "caseid", "id case", "instance", "instance id"]
TASK_ID_CANDIDATES = ["task_id", "task id", "taskid", "id task", "mã task", "ma task", "mã công việc"]
ACTIVITY_CANDIDATES = ["activity", "task", "task_name", "activity name", "task name", "công việc", "hoạt động"]
RESOURCE_CANDIDATES = [
    "resource", "employee", "nhan vien", "nhân viên", "assignee", "user", "actor",
    "người thực hiện", "personname", "person_name", "person name", "người thực hiện",
    "tên nhân viên", "ten nhan vien", "nhân sự",
]
START_CANDIDATES = ["start_time", "start time", "starttime", "start", "start timestamp", "thời gian bắt đầu", "bat dau"]
END_CANDIDATES = ["end_time", "end time", "endtime", "end", "complete timestamp", "complete_time", "thời gian kết thúc", "ket thuc"]
# Cột "finishTime"/"finish_time" trong một số eventlog là THỜI LƯỢNG đã tính sẵn
# (vd "194 phút"), không phải mốc thời gian kết thúc — không dùng để dò cột end,
# vì để tránh nhầm parse chuỗi thời lượng thành timestamp.
FINISH_DURATION_CANDIDATES = ["finishtime", "finish_time", "finish time", "thời gian hoàn thành"]
TIMESTAMP_CANDIDATES = ["timestamp", "time", "datetime", "date"]
TRANSITION_CANDIDATES = ["lifecycle:transition", "lifecycle transition", "transition", "status", "event_type"]

TASK_NAME_CANDIDATES = ACTIVITY_CANDIDATES
STANDARD_TIME_CANDIDATES = [
    "standard_time", "standard time", "standardtime", "thời gian chuẩn",
    "thoi gian chuan", "sla", "expected_time", "expected time", "duration",
]
UNIT_CANDIDATES = ["unit", "đơn vị", "don vi", "time_unit"]

START_TRANSITION_VALUES = {"start", "assign", "schedule", "resume", "begin", "bắt đầu"}
END_TRANSITION_VALUES = {"complete", "end", "finish", "ate_complete", "hoàn thành", "kết thúc"}


class ColumnDetectionError(Exception):
    """Raised when a required column cannot be auto-detected."""

    def __init__(self, message: str, columns: list):
        super().__init__(message)
        self.columns = columns


def _find_column(columns, candidates):
    lower_map = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    # loose contains-match fallback
    for cand in candidates:
        for lc, orig in lower_map.items():
            if cand in lc:
                return orig
    return None


def read_csv_flexible(file_path: str) -> pd.DataFrame:
    """Read a CSV trying a couple of common separators/encodings."""
    last_err = None
    for sep in [None, ",", ";", "\t"]:
        for enc in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                df = pd.read_csv(file_path, sep=sep, engine="python", encoding=enc)
                if df.shape[1] > 1:
                    return df
            except Exception as e:  # noqa: BLE001
                last_err = e
    if last_err:
        raise last_err
    raise ValueError(f"Không thể đọc file: {file_path}")


def detect_eventlog_columns(df: pd.DataFrame) -> dict:
    """Best-effort detection of the columns needed from the event log.

    Returns a dict with keys: case, task_id, activity, resource, start, end,
    timestamp, transition. Any key whose value is None was not detected.
    `task_id` is optional: khi có, nó được ưu tiên dùng để đối chiếu chính xác
    với id Task trong file BPMN (đáng tin hơn so với so khớp theo tên activity).
    """
    cols = list(df.columns)
    mapping = {
        "case": _find_column(cols, CASE_CANDIDATES),
        "task_id": _find_column(cols, TASK_ID_CANDIDATES),
        "activity": _find_column(cols, ACTIVITY_CANDIDATES),
        "resource": _find_column(cols, RESOURCE_CANDIDATES),
        "start": _find_column(cols, START_CANDIDATES),
        "end": _find_column(cols, END_CANDIDATES),
        "timestamp": _find_column(cols, TIMESTAMP_CANDIDATES),
        "transition": _find_column(cols, TRANSITION_CANDIDATES),
    }
    return mapping


def detect_standard_time_columns(df: pd.DataFrame) -> dict:
    cols = list(df.columns)
    mapping = {
        "task_id": _find_column(cols, TASK_ID_CANDIDATES),
        "task": _find_column(cols, TASK_NAME_CANDIDATES),
        "standard_time": _find_column(cols, STANDARD_TIME_CANDIDATES),
        "unit": _find_column(cols, UNIT_CANDIDATES),
    }
    return mapping


def build_wide_eventlog(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Return a normalized dataframe with columns:
    case_id, task_id (có thể rỗng), activity, resource, start_time, end_time
    (as datetime).

    Supports two shapes:
      * wide: mapping has 'start' and 'end' columns already.
      * long: mapping has 'timestamp' + 'transition', one row per
        lifecycle event; rows are pivoted into start/end per
        (case_id, activity) occurrence.
    """
    case_col = mapping.get("case")
    activity_col = mapping.get("activity")
    resource_col = mapping.get("resource")
    task_id_col = mapping.get("task_id")

    if not (case_col and activity_col and resource_col):
        raise ColumnDetectionError(
            "Không xác định được cột Case/Activity/Resource trong eventlog.csv",
            list(df.columns),
        )

    start_col = mapping.get("start")
    end_col = mapping.get("end")

    if start_col and end_col:
        cols = [case_col, activity_col, resource_col, start_col, end_col]
        names = ["case_id", "activity", "resource", "start_time", "end_time"]
        if task_id_col:
            cols.insert(1, task_id_col)
            names.insert(1, "task_id")
        out = df[cols].copy()
        out.columns = names
        out["start_time"] = pd.to_datetime(out["start_time"], errors="coerce")
        out["end_time"] = pd.to_datetime(out["end_time"], errors="coerce")
        if "task_id" not in out.columns:
            out["task_id"] = None
        return out.dropna(subset=["start_time", "end_time"])

    # Long format: pivot on lifecycle transition.
    ts_col = mapping.get("timestamp")
    trans_col = mapping.get("transition")
    if not (ts_col and trans_col):
        raise ColumnDetectionError(
            "eventlog.csv cần có cột start/end hoặc timestamp + lifecycle:transition",
            list(df.columns),
        )

    cols = [case_col, activity_col, resource_col, ts_col, trans_col]
    names = ["case_id", "activity", "resource", "timestamp", "transition"]
    if task_id_col:
        cols.insert(1, task_id_col)
        names.insert(1, "task_id")
    tmp = df[cols].copy()
    tmp.columns = names
    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
    tmp["transition_norm"] = tmp["transition"].astype(str).str.strip().str.lower()

    group_keys = ["case_id", "task_id", "activity"] if task_id_col else ["case_id", "activity"]
    tmp["occurrence"] = tmp.groupby(group_keys).cumcount() // 2

    starts = tmp[tmp["transition_norm"].isin(START_TRANSITION_VALUES)]
    ends = tmp[tmp["transition_norm"].isin(END_TRANSITION_VALUES)]

    group_occ = group_keys + ["occurrence"]
    starts_g = starts.groupby(group_occ, as_index=False).agg(
        resource=("resource", "first"), start_time=("timestamp", "min")
    )
    ends_g = ends.groupby(group_occ, as_index=False).agg(
        end_time=("timestamp", "max")
    )

    merged = pd.merge(starts_g, ends_g, on=group_occ, how="inner")
    merged = merged.drop(columns=["occurrence"])
    if "task_id" not in merged.columns:
        merged["task_id"] = None
    return merged.dropna(subset=["start_time", "end_time"])


UNIT_TO_MINUTES = {
    "second": 1 / 60, "seconds": 1 / 60, "s": 1 / 60, "giây": 1 / 60,
    "minute": 1, "minutes": 1, "min": 1, "phút": 1,
    "hour": 60, "hours": 60, "h": 60, "giờ": 60,
    "day": 1440, "days": 1440, "ngày": 1440,
}


def build_standard_time_table(df: pd.DataFrame, mapping: dict, default_unit: str = "minutes") -> pd.DataFrame:
    """Return normalized dataframe: task_id (có thể rỗng), task, standard_minutes."""
    task_col = mapping.get("task")
    time_col = mapping.get("standard_time")
    unit_col = mapping.get("unit")
    task_id_col = mapping.get("task_id")

    if not (task_col and time_col):
        raise ColumnDetectionError(
            "Không xác định được cột Task/Standard time trong standardTime.csv",
            list(df.columns),
        )

    cols = [task_col, time_col]
    names = ["task", "standard_value"]
    if task_id_col:
        cols.insert(0, task_id_col)
        names.insert(0, "task_id")
    out = df[cols].copy()
    out.columns = names
    out["standard_value"] = pd.to_numeric(out["standard_value"], errors="coerce")

    if unit_col:
        units = df[unit_col].astype(str).str.strip().str.lower()
    else:
        units = pd.Series([default_unit.lower()] * len(df))

    factors = units.map(lambda u: UNIT_TO_MINUTES.get(u, UNIT_TO_MINUTES.get(default_unit.lower(), 1)))
    out["standard_minutes"] = out["standard_value"] * factors.values
    out["task"] = out["task"].astype(str).str.strip()
    if "task_id" in out.columns:
        out["task_id"] = out["task_id"].astype(str).str.strip()
    else:
        out["task_id"] = None
    return out.dropna(subset=["standard_minutes"])
