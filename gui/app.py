"""Main Tkinter application window."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:  # thư viện chưa cài -> vẫn chạy được, chỉ mất kéo-thả
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False

from core.bpmn_parser import parse_bpmn
from core.data_loader import (
    read_csv_flexible,
    detect_eventlog_columns,
    detect_standard_time_columns,
    build_wide_eventlog,
    build_standard_time_table,
    ColumnDetectionError,
)
from core.analyzer import compute_performance, compute_employee_summary
from core.validator import validate_consistency
from core.gap_analysis import detect_missing_tasks, build_eventlog_addendum
from gui.column_mapping_dialog import ask_eventlog_mapping, ask_standard_time_mapping
from gui.network_view import NetworkView

APP_TITLE = "Phân tích Hiệu suất Nhân viên theo Quy trình BPMN"


class UserCancelled(Exception):
    """Người dùng bấm Hủy ở hộp thoại ánh xạ cột thủ công."""


class FilePickerRow(ttk.Frame):
    """Một dòng chọn file: vừa bấm nút duyệt file, vừa có thể kéo-thả file
    trực tiếp từ Finder/Explorer vào vùng thả bên dưới.

    Vùng thả hiển thị RÕ tên file đã chọn (không chỉ đường dẫn đầy đủ dễ bị
    cắt mất phần tên khi 3 file cùng nằm chung thư mục), và tự đổi màu +
    ghi "✓ Đã nhận: ..." ngay khi nhận file để người dùng biết chắc đã xong.
    """

    ZONE_IDLE_BG = "#fafafa"
    ZONE_HOVER_BG = "#dceeff"
    ZONE_OK_BG = "#e6f6e6"

    def __init__(self, parent, label, filetypes, extensions=None, on_change=None):
        super().__init__(parent)
        self.path_var = tk.StringVar()
        self.filetypes = filetypes
        self.extensions = [e.lower() for e in extensions] if extensions else None
        self.on_change = on_change

        ttk.Label(self, text=label, width=16).pack(side="left")

        # Vùng thả: một khung viền nét đứt to, dễ nhắm khi kéo file vào.
        self.drop_zone = tk.Frame(
            self, bg=self.ZONE_IDLE_BG, highlightthickness=2,
            highlightbackground="#bbbbbb", highlightcolor="#bbbbbb",
        )
        self.drop_zone.pack(side="left", fill="x", expand=True, padx=(6, 6), ipady=4)

        placeholder = "Chưa chọn file — kéo-thả vào đây" if DND_AVAILABLE else "Chưa chọn file"
        self.name_var = tk.StringVar(value=placeholder)
        self.name_label = tk.Label(
            self.drop_zone, textvariable=self.name_var, bg=self.ZONE_IDLE_BG,
            fg="#666666", anchor="w", font=("", 10, "bold"),
        )
        self.name_label.pack(fill="x", padx=8, anchor="w")

        self.path_hint_var = tk.StringVar(value="")
        self.path_label = tk.Label(
            self.drop_zone, textvariable=self.path_hint_var, bg=self.ZONE_IDLE_BG,
            fg="#999999", anchor="w", font=("", 8),
        )
        self.path_label.pack(fill="x", padx=8, anchor="w")

        ttk.Button(self, text="Chọn file...", command=self._browse).pack(side="left")

        if DND_AVAILABLE:
            # Đăng ký kéo-thả trên cả khung lẫn 2 label bên trong (thay vì
            # một ô Entry) vì Entry là widget nhập liệu, dễ "giành" sự kiện
            # chuột trước khi hệ điều hành kịp báo Drop cho Tk.
            for widget in (self.drop_zone, self.name_label, self.path_label):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
                widget.dnd_bind("<<Drop>>", self._on_drop)

    def _browse(self):
        path = filedialog.askopenfilename(filetypes=self.filetypes)
        if path:
            self._set_path(path)

    def _paint(self, bg):
        self.drop_zone.configure(bg=bg)
        self.name_label.configure(bg=bg)
        self.path_label.configure(bg=bg)

    def _on_drag_enter(self, event):
        self._paint(self.ZONE_HOVER_BG)
        return event.action

    def _on_drag_leave(self, event):
        self._paint(self.ZONE_OK_BG if self.path_var.get() else self.ZONE_IDLE_BG)
        return event.action

    def _on_drop(self, event):
        try:
            self._handle_drop_data(event.data)
        except Exception as e:  # noqa: BLE001 - không để lỗi kéo-thả âm thầm biến mất
            self._paint(self.ZONE_IDLE_BG)
            messagebox.showerror("Lỗi kéo-thả file", f"Không xử lý được file vừa thả:\n{e}")
        return getattr(event, "action", "copy")

    def _handle_drop_data(self, raw_data: str):
        paths = self.tk.splitlist(raw_data)
        if not paths:
            self._paint(self.ZONE_IDLE_BG)
            return
        path = paths[0]
        if path.startswith("file://"):
            from urllib.parse import unquote, urlparse
            path = unquote(urlparse(path).path)

        if len(paths) > 1:
            messagebox.showinfo("Kéo-thả file", "Chỉ nhận 1 file, đã lấy file đầu tiên:\n" + path)

        if self.extensions and not any(path.lower().endswith(ext) for ext in self.extensions):
            self._paint(self.ZONE_IDLE_BG if not self.path_var.get() else self.ZONE_OK_BG)
            messagebox.showwarning(
                "Sai định dạng file",
                f"File thả vào không đúng định dạng cho phép ({', '.join(self.extensions)}):\n{path}",
            )
            return

        self._set_path(path)

    def _set_path(self, path):
        import os as _os
        self.path_var.set(path)
        self.name_var.set(f"✓ {_os.path.basename(path)}")
        self.path_hint_var.set(path)
        self._paint(self.ZONE_OK_BG)
        if self.on_change:
            self.on_change(path)

    def get(self):
        return self.path_var.get().strip()


class DataFrameTable(ttk.Frame):
    """A scrollable ttk.Treeview bound to a pandas DataFrame."""

    def __init__(self, parent):
        super().__init__(parent)
        self.tree = ttk.Treeview(self, show="headings")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.tag_configure("late_high", background="#fde2e2")
        self.df = pd.DataFrame()

    def set_dataframe(self, df: pd.DataFrame):
        self.df = df
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(df.columns)
        for col in df.columns:
            self.tree.heading(col, text=col)
            width = max(90, min(220, 10 + 8 * len(str(col))))
            self.tree.column(col, width=width, anchor="center")

        late_col = "Tỷ lệ trễ hạn (%)"
        for _, row in df.iterrows():
            tags = ()
            if late_col in df.columns:
                try:
                    if float(row[late_col]) >= 30:
                        tags = ("late_high",)
                except (TypeError, ValueError):
                    pass
            self.tree.insert("", "end", values=list(row), tags=tags)


_AppBase = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk


BG_MAIN = "#f4f5f7"
BG_CARD = "#ffffff"
FG_TEXT = "#1f2328"
FG_MUTED = "#5a6270"
ACCENT = "#2f6fed"


class App(_AppBase):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x680")
        self.minsize(900, 560)

        self.detail_df = pd.DataFrame()
        self.summary_df = pd.DataFrame()

        # File BPMN là nguồn chuẩn (source of truth); phải "Kiểm tra dữ liệu"
        # đạt (không lỗi/cảnh báo) thì mới cho bấm "Tính hiệu suất". Kết quả
        # kiểm tra được cache lại để Tính hiệu suất không phải đọc/ánh xạ lại.
        self._validated_paths = None
        self._validated_inputs = None

        self._setup_style()
        self._build_widgets()

    # ---------------------------------------------------------------- style
    def _setup_style(self):
        """Ép dùng theme 'clam' + màu nền/chữ tường minh để giao diện luôn dễ
        đọc (một số bản Tk trên macOS/Homebrew render theme mặc định bị lỗi
        màu, ví dụ nền hồng chữ trắng)."""
        self.configure(bg=BG_MAIN)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG_MAIN, foreground=FG_TEXT, fieldbackground=BG_CARD)
        style.configure("TFrame", background=BG_MAIN)
        style.configure("TLabel", background=BG_MAIN, foreground=FG_TEXT)
        style.configure("TButton", background=BG_CARD, foreground=FG_TEXT, padding=6)
        style.map("TButton", background=[("active", "#e5e9f0")])
        style.configure("TNotebook", background=BG_MAIN)
        style.configure(
            "TNotebook.Tab", background="#e5e9f0", foreground=FG_TEXT, padding=(12, 6)
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_CARD)],
            foreground=[("selected", FG_TEXT)],
        )
        style.configure(
            "Treeview", background=BG_CARD, fieldbackground=BG_CARD, foreground=FG_TEXT, rowheight=24
        )
        style.configure(
            "Treeview.Heading", background="#e5e9f0", foreground=FG_TEXT
        )
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        style.configure("TProgressbar", background=ACCENT)

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        top = ttk.Frame(self, padding=12)
        top.pack(side="top", fill="x")

        ttk.Label(top, text=APP_TITLE, font=("", 14, "bold")).pack(anchor="w", pady=(0, 10))

        self.bpmn_picker = FilePickerRow(
            top, "File BPMN (.bpmn):",
            [("BPMN files", "*.bpmn *.xml"), ("All files", "*.*")],
            extensions=[".bpmn", ".xml"],
            on_change=self._invalidate_validation,
        )
        self.bpmn_picker.pack(fill="x", pady=3)

        self.eventlog_picker = FilePickerRow(
            top, "Eventlog (.csv):",
            [("CSV files", "*.csv"), ("All files", "*.*")],
            extensions=[".csv"],
            on_change=self._invalidate_validation,
        )
        self.eventlog_picker.pack(fill="x", pady=3)

        self.standard_picker = FilePickerRow(
            top, "Standard Time (.csv):",
            [("CSV files", "*.csv"), ("All files", "*.*")],
            extensions=[".csv"],
            on_change=self._invalidate_validation,
        )
        self.standard_picker.pack(fill="x", pady=3)

        if not DND_AVAILABLE:
            ttk.Label(
                top,
                text="(Chưa cài tkinterdnd2 nên tạm thời không kéo-thả được file, vẫn dùng nút 'Chọn file...' bình thường)",
                foreground="#a06a00",
            ).pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(top)
        actions.pack(fill="x", pady=(10, 0))
        self.validate_btn = ttk.Button(actions, text="① Kiểm tra dữ liệu", command=self.on_validate)
        self.validate_btn.pack(side="left")

        self.calc_btn = ttk.Button(
            actions, text="② Tính hiệu suất", command=self.on_calculate, state="disabled"
        )
        self.calc_btn.pack(side="left", padx=(8, 0))

        self.export_csv_btn = ttk.Button(actions, text="Xuất CSV...", command=lambda: self.on_export("csv"), state="disabled")
        self.export_csv_btn.pack(side="left", padx=(8, 0))

        self.export_xlsx_btn = ttk.Button(actions, text="Xuất Excel...", command=lambda: self.on_export("xlsx"), state="disabled")
        self.export_xlsx_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        # Results notebook -------------------------------------------------
        mid = ttk.Frame(self, padding=(12, 0, 12, 0))
        mid.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(mid)
        self.notebook.pack(fill="both", expand=True)

        detail_tab = ttk.Frame(self.notebook)
        summary_tab = ttk.Frame(self.notebook)
        missing_tab = ttk.Frame(self.notebook)
        self.missing_tab = missing_tab
        network_tab = ttk.Frame(self.notebook)
        self.notebook.add(detail_tab, text="Chi tiết theo Nhân viên & Task")
        self.notebook.add(summary_tab, text="Tổng hợp theo Nhân viên")
        self.notebook.add(missing_tab, text="Task bị bỏ sót")
        self.notebook.add(network_tab, text="Mạng xã hội")
        # Chỉ bật tab này khi kiểm tra dữ liệu phát hiện có task bị bỏ sót;
        # nếu dữ liệu sạch (tính hiệu suất được, không nghi ngờ thiếu task) thì
        # ẩn/khoá tab để tránh gây rối vì không có nội dung gì để xem.
        self.notebook.tab(missing_tab, state="disabled")

        self.detail_table = DataFrameTable(detail_tab)
        self.detail_table.pack(fill="both", expand=True, padx=4, pady=8)

        self.summary_table = DataFrameTable(summary_tab)
        self.summary_table.pack(fill="both", expand=True, padx=4, pady=8)

        missing_header = ttk.Frame(missing_tab)
        missing_header.pack(fill="x")
        ttk.Label(
            missing_header,
            text=(
                "Case có task LIỀN TRƯỚC (theo BPMN) đã hoàn thành nhưng task kế tiếp lại "
                "không xuất hiện — nhiều khả năng nhân viên phụ trách task liền trước đã bỏ "
                "sót/quên chuyển tiếp. Kết quả được tính lại mỗi khi bấm '① Kiểm tra dữ liệu'."
            ),
            wraplength=850, justify="left", padding=(4, 6, 4, 0),
        ).pack(side="left", fill="x", expand=True)
        self.export_missing_btn = ttk.Button(
            missing_header, text="Xuất CSV để bổ sung eventlog...",
            command=self.on_export_missing, state="disabled",
        )
        self.export_missing_btn.pack(side="right", padx=8, pady=6)

        missing_split = ttk.Frame(missing_tab)
        missing_split.pack(fill="both", expand=True)
        ttk.Label(missing_split, text="Theo nhân viên:", font=("", 9, "bold")).pack(anchor="w", padx=4, pady=(6, 0))
        self.missing_by_employee_table = DataFrameTable(missing_split)
        self.missing_by_employee_table.pack(fill="both", expand=False, padx=4, pady=(2, 8))
        self.missing_by_employee_table.tree.configure(height=6)

        ttk.Label(missing_split, text="Chi tiết theo case:", font=("", 9, "bold")).pack(anchor="w", padx=4)
        self.missing_detail_table = DataFrameTable(missing_split)
        self.missing_detail_table.pack(fill="both", expand=True, padx=4, pady=(2, 8))

        self.network_view = NetworkView(network_tab)
        self.network_view.pack(fill="both", expand=True)

        # Status bar ---------------------------------------------------------
        self.status_var = tk.StringVar(
            value="Sẵn sàng. Hãy chọn 3 file đầu vào rồi bấm '① Kiểm tra dữ liệu' trước."
        )
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=(8, 3))
        status.pack(side="bottom", fill="x")

    # -------------------------------------------------------------- actions
    def set_status(self, text: str):
        self.status_var.set(text)
        self.update_idletasks()

    def _gather_paths(self):
        """Đọc 3 đường dẫn file, báo lỗi nếu thiếu/không tồn tại. Trả về
        (bpmn_path, eventlog_path, standard_path) hoặc None nếu không hợp lệ."""
        bpmn_path = self.bpmn_picker.get()
        eventlog_path = self.eventlog_picker.get()
        standard_path = self.standard_picker.get()

        missing = [name for name, p in [
            ("File BPMN", bpmn_path), ("Eventlog", eventlog_path), ("Standard Time", standard_path)
        ] if not p]
        if missing:
            messagebox.showwarning(APP_TITLE, "Vui lòng chọn đủ 3 file:\n- " + "\n- ".join(missing))
            return None
        for p, label in [(bpmn_path, "BPMN"), (eventlog_path, "Eventlog"), (standard_path, "Standard Time")]:
            if not os.path.isfile(p):
                messagebox.showerror(APP_TITLE, f"Không tìm thấy file {label}:\n{p}")
                return None
        return bpmn_path, eventlog_path, standard_path

    def _invalidate_validation(self, _path=None):
        """Gọi khi người dùng đổi 1 trong 3 file: bắt buộc kiểm tra dữ liệu
        lại từ đầu trước khi được tính hiệu suất tiếp."""
        self._validated_paths = None
        self._validated_inputs = None
        self.calc_btn.config(state="disabled")
        self.notebook.tab(self.missing_tab, state="disabled")
        self.export_missing_btn.config(state="disabled")

    def on_calculate(self):
        paths = self._gather_paths()
        if paths is None:
            return

        if paths != self._validated_paths or self._validated_inputs is None:
            messagebox.showwarning(
                APP_TITLE,
                "Bạn cần bấm '① Kiểm tra dữ liệu' trước và đảm bảo không còn lỗi/cảnh báo, "
                "rồi mới bấm '② Tính hiệu suất' được.",
            )
            return

        self.calc_btn.config(state="disabled")
        self.validate_btn.config(state="disabled")
        self.progress.start(12)
        self.set_status("Đang tính hiệu suất...")

        thread = threading.Thread(
            target=self._run_pipeline_cached, args=(self._validated_inputs,), daemon=True
        )
        thread.start()

    def _run_pipeline_cached(self, inputs):
        bpmn, wide_eventlog, standard_table, _n_raw = inputs
        try:
            detail = compute_performance(wide_eventlog, standard_table, bpmn)
            summary = compute_employee_summary(detail)
            self.after(0, self._on_success, detail, summary, wide_eventlog)
        except Exception as e:  # noqa: BLE001
            self.after(0, self._on_error, str(e))

    def on_validate(self):
        paths = self._gather_paths()
        if paths is None:
            return

        self.calc_btn.config(state="disabled")
        self.validate_btn.config(state="disabled")
        self.progress.start(12)
        self.set_status("Đang kiểm tra dữ liệu...")

        thread = threading.Thread(target=self._run_validation, args=paths, daemon=True)
        thread.start()

    def _load_inputs(self, bpmn_path, eventlog_path, standard_path):
        """Đọc + tự nhận diện/ánh xạ cột cho cả 3 file. Dùng chung cho cả
        'Tính hiệu suất' và 'Kiểm tra dữ liệu'. Raises UserCancelled nếu người
        dùng hủy hộp thoại ánh xạ thủ công.
        Trả về (bpmn, wide_eventlog, standard_table, n_raw_events).
        """
        bpmn = parse_bpmn(bpmn_path)

        event_df_raw = read_csv_flexible(eventlog_path)
        event_mapping = detect_eventlog_columns(event_df_raw)
        has_wide = event_mapping.get("start") and event_mapping.get("end")
        has_long = event_mapping.get("timestamp") and event_mapping.get("transition")
        needs_mapping = not (event_mapping.get("case") and event_mapping.get("activity")
                              and event_mapping.get("resource") and (has_wide or has_long))
        if needs_mapping:
            event_mapping = self._ask_mapping_on_ui_thread(
                ask_eventlog_mapping, event_df_raw.columns.tolist(), event_mapping
            )
            if event_mapping is None:
                raise UserCancelled()

        wide_eventlog = build_wide_eventlog(event_df_raw, event_mapping)

        std_df_raw = read_csv_flexible(standard_path)
        std_mapping = detect_standard_time_columns(std_df_raw)
        needs_std_mapping = not (std_mapping.get("task") and std_mapping.get("standard_time"))
        if needs_std_mapping:
            std_mapping = self._ask_mapping_on_ui_thread(
                ask_standard_time_mapping, std_df_raw.columns.tolist(), std_mapping
            )
            if std_mapping is None:
                raise UserCancelled()
            default_unit = std_mapping.pop("default_unit", "minutes")
        else:
            default_unit = "minutes"

        standard_table = build_standard_time_table(std_df_raw, std_mapping, default_unit=default_unit)
        return bpmn, wide_eventlog, standard_table, len(event_df_raw)

    def _run_validation(self, bpmn_path, eventlog_path, standard_path):
        try:
            bpmn, wide_eventlog, standard_table, n_raw = self._load_inputs(
                bpmn_path, eventlog_path, standard_path
            )
            report = validate_consistency(bpmn, wide_eventlog, standard_table, n_raw_events=n_raw)
            missing = detect_missing_tasks(bpmn, wide_eventlog)
            paths = (bpmn_path, eventlog_path, standard_path)
            inputs = (bpmn, wide_eventlog, standard_table, n_raw)
            self.after(0, self._on_validation_done, report, paths, inputs, missing)
        except UserCancelled:
            self._finish(cancelled=True)
        except ColumnDetectionError as e:
            self.after(0, self._on_error, f"{e}\n\nCác cột hiện có: {', '.join(e.columns)}")
        except Exception as e:  # noqa: BLE001
            self.after(0, self._on_error, str(e))

    def _ask_mapping_on_ui_thread(self, fn, columns, detected):
        result_holder = {}
        done = threading.Event()

        def show():
            result_holder["value"] = fn(self, columns, detected)
            done.set()

        self.after(0, show)
        done.wait()
        return result_holder["value"]

    def _finish(self, cancelled=False):
        def _u():
            self.progress.stop()
            self.calc_btn.config(state="normal" if self._validated_inputs is not None else "disabled")
            self.validate_btn.config(state="normal")
            if cancelled:
                self.set_status("Đã hủy.")
        self.after(0, _u)

    def _on_success(self, detail: pd.DataFrame, summary: pd.DataFrame, wide_eventlog: pd.DataFrame):
        self.detail_df = detail
        self.summary_df = summary
        self.detail_table.set_dataframe(detail)
        self.summary_table.set_dataframe(summary)
        self.network_view.set_eventlog(wide_eventlog)
        self.export_csv_btn.config(state="normal" if not detail.empty else "disabled")
        self.export_xlsx_btn.config(state="normal" if not detail.empty else "disabled")
        self.progress.stop()
        self.calc_btn.config(state="normal" if self._validated_inputs is not None else "disabled")
        self.validate_btn.config(state="normal")
        self.set_status(f"Hoàn tất. {len(detail)} dòng (Nhân viên x Task). Ô tô đậm = tỷ lệ trễ hạn >= 30%.")

    def _on_error(self, message: str):
        self.progress.stop()
        self.calc_btn.config(state="normal" if self._validated_inputs is not None else "disabled")
        self.validate_btn.config(state="normal")
        self.set_status("Có lỗi xảy ra.")
        messagebox.showerror(APP_TITLE, message)

    def _on_validation_done(self, report: dict, paths: tuple, inputs: tuple, missing: dict):
        self.progress.stop()
        self.validate_btn.config(state="normal")

        self.missing_by_employee_table.set_dataframe(missing["by_employee"])
        self.missing_detail_table.set_dataframe(missing["detail"])
        n_missing = len(missing["detail"])
        self.export_missing_btn.config(state="normal" if n_missing else "disabled")
        self.notebook.tab(self.missing_tab, state="normal" if n_missing else "disabled")

        # Chỉ "Lỗi" mới chắc chắn ảnh hưởng tới kết quả tính toán nên mới chặn
        # nút tính hiệu suất. "Cảnh báo" (vd. 1 task BPMN thuộc nhánh rẽ tùy
        # chọn/loại trừ chưa từng xuất hiện trong lô dữ liệu này) chỉ là điều
        # cần lưu ý, không có nghĩa là dữ liệu sai — vẫn tính hiệu suất được
        # như chính báo cáo đã ghi rõ ("Không có lỗi nghiêm trọng — vẫn tính
        # được hiệu suất").
        can_calculate = not report["issues"]
        if can_calculate:
            self._validated_paths = paths
            self._validated_inputs = inputs
            self.calc_btn.config(state="normal")
        else:
            self._validated_paths = None
            self._validated_inputs = None
            self.calc_btn.config(state="disabled")

        n_issue, n_warn, n_info = len(report["issues"]), len(report["warnings"]), len(report["infos"])
        if can_calculate and n_warn == 0:
            status = f"Đã kiểm tra dữ liệu: OK ({n_info} thông tin). Có thể bấm '② Tính hiệu suất'."
        elif can_calculate:
            status = (
                f"Đã kiểm tra dữ liệu: {n_warn} cảnh báo cần lưu ý (không chặn). "
                "Có thể bấm '② Tính hiệu suất'."
            )
        else:
            status = (
                f"Đã kiểm tra dữ liệu: {n_issue} lỗi, {n_warn} cảnh báo — cần sửa dữ liệu rồi "
                "kiểm tra lại trước khi tính hiệu suất."
            )
        if n_missing:
            status += f" ⚠ Phát hiện {n_missing} trường hợp nghi bỏ sót task — xem tab 'Task bị bỏ sót'."
        self.set_status(status)
        self._show_validation_report(report, missing)

    def _show_validation_report(self, report: dict, missing: dict | None = None):
        win = tk.Toplevel(self)
        win.title("Kết quả kiểm tra dữ liệu")
        win.geometry("680x520")
        win.configure(bg=BG_MAIN)
        win.transient(self)

        stats = ttk.Frame(win, padding=(14, 12, 14, 4))
        stats.pack(fill="x")
        ttk.Label(
            stats,
            text=(
                f"BPMN: {report['n_bpmn_tasks']} task   •   "
                f"Eventlog: {report['n_events']} sự kiện, {report['n_cases']} case, "
                f"{report['n_resources']} nhân viên   •   "
                f"Standard Time: {report['n_standard_rows']} dòng"
            ),
            wraplength=650, justify="left", font=("", 9),
        ).pack(anchor="w")

        text_frame = ttk.Frame(win, padding=(14, 6, 14, 6))
        text_frame.pack(fill="both", expand=True)
        text = tk.Text(
            text_frame, wrap="word", bg=BG_CARD, fg=FG_TEXT, relief="solid",
            borderwidth=1, padx=10, pady=10,
        )
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=vsb.set)
        text.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        text.tag_configure("ok", foreground="#1e8449", font=("", 11, "bold"))
        text.tag_configure("bad", foreground="#c0392b", font=("", 11, "bold"))
        text.tag_configure("section_issue", foreground="#c0392b", font=("", 10, "bold"))
        text.tag_configure("section_warn", foreground="#b8860b", font=("", 10, "bold"))
        text.tag_configure("section_info", foreground="#2f6fed", font=("", 10, "bold"))
        text.tag_configure("section_missing", foreground="#9c27b0", font=("", 10, "bold"))
        text.tag_configure("item", lmargin1=14, lmargin2=28)

        issues, warns, infos = report["issues"], report["warnings"], report["infos"]
        missing_detail = missing["detail"] if missing else pd.DataFrame()

        if not missing_detail.empty:
            text.insert(
                "end",
                f"⚠ NGHI NGỜ BỎ SÓT TASK ({len(missing_detail)} trường hợp) — theo BPMN\n",
                "section_missing",
            )
            for _, row in missing_detail.iterrows():
                pred = row["Task liền trước đã hoàn thành"]
                when = row["Hoàn thành task liền trước lúc"]
                when_txt = f", lúc {when}" if pd.notna(when) else ""
                text.insert(
                    "end",
                    f"• Case {row['Case']}: thiếu \"{row['Task bị thiếu']}\" — nghi do "
                    f"{row['Nhân viên nghi ngờ bỏ sót']} chưa chuyển tiếp sau khi hoàn thành "
                    f"\"{pred}\"{when_txt}.\n\n",
                    "item",
                )
            text.insert("end", "(Xem đầy đủ ở tab 'Task bị bỏ sót' sau khi đóng cửa sổ này.)\n\n")

        if not issues and not warns and not infos and missing_detail.empty:
            text.insert("end", "✔ Không phát hiện vấn đề gì.\n", "ok")
            text.insert("end", "3 file khớp nhau và có thể tính hiệu suất bình thường.\n")
        elif not issues and not warns and not infos:
            pass
        else:
            if issues:
                text.insert("end", "✘ Có lỗi có thể ảnh hưởng tới kết quả tính toán.\n\n", "bad")
            else:
                text.insert("end", "✔ Không có lỗi nghiêm trọng — vẫn tính được hiệu suất.\n\n", "ok")

            if issues:
                text.insert("end", f"LỖI ({len(issues)})\n", "section_issue")
                for msg in issues:
                    text.insert("end", f"• {msg}\n\n", "item")
            if warns:
                text.insert("end", f"CẢNH BÁO ({len(warns)})\n", "section_warn")
                for msg in warns:
                    text.insert("end", f"• {msg}\n\n", "item")
            if infos:
                text.insert("end", f"THÔNG TIN ({len(infos)})\n", "section_info")
                for msg in infos:
                    text.insert("end", f"• {msg}\n\n", "item")

        text.configure(state="disabled")

        ttk.Button(win, text="Đóng", command=win.destroy).pack(pady=(0, 12))
        win.update_idletasks()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
        win.grab_set()

    def on_export(self, kind: str):
        if self.detail_df.empty:
            return
        ext = "csv" if kind == "csv" else "xlsx"
        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            filetypes=[(f"{ext.upper()} files", f"*.{ext}")],
            initialfile=f"hieu_suat_nhan_vien.{ext}",
        )
        if not path:
            return
        try:
            if kind == "csv":
                self.detail_df.to_csv(path, index=False, encoding="utf-8-sig")
                summary_path = os.path.splitext(path)[0] + "_tong_hop.csv"
                self.summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
                messagebox.showinfo(APP_TITLE, f"Đã lưu:\n{path}\n{summary_path}")
            else:
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    self.detail_df.to_excel(writer, sheet_name="Chi tiet", index=False)
                    self.summary_df.to_excel(writer, sheet_name="Tong hop", index=False)
                messagebox.showinfo(APP_TITLE, f"Đã lưu:\n{path}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Không thể lưu file:\n{e}")

    def on_export_missing(self):
        detail = self.missing_detail_table.df
        if detail.empty:
            return
        addendum = build_eventlog_addendum(detail)
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="eventlog_bo_sung.csv",
        )
        if not path:
            return
        try:
            addendum.to_csv(path, index=False, encoding="utf-8-sig")
            messagebox.showinfo(
                APP_TITLE,
                f"Đã lưu {len(addendum)} dòng gợi ý bổ sung:\n{path}\n\n"
                "Các cột khớp với eventlog.csv (caseId, taskId, activity, startTime, "
                "endTime, finishTime, personName) kèm cột ghi_chu. Hãy xác nhận lại "
                "người thực hiện và điền endTime/finishTime thực tế trước khi dán vào eventlog.csv.",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_TITLE, f"Không thể lưu file:\n{e}")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
