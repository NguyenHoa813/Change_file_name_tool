from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable


TOKEN_RE = re.compile(r"<\s*([^<>]+?)\s*>")
DATE_RE = re.compile(r"^date\s*:\s*(.+)$", re.IGNORECASE)
TIME_RE = re.compile(r"^time\s*:\s*(.+)$", re.IGNORECASE)
INC_RE = re.compile(r"^inc\s*nr\s*:\s*(\d+)$", re.IGNORECASE)


# Công thức được hiển thị trực tiếp trên giao diện. Giá trị đầu tiên là token
# sẽ được chèn vào mẫu tên, giá trị thứ hai là phần mô tả cho người dùng.
FORMULAS: dict[str, list[tuple[str, str]]] = {
    "Filename": [
        ("<name>", "Tên tệp không có phần mở rộng"),
        ("<ext>", "Phần mở rộng không có dấu chấm"),
        ("<parent>", "Tên thư mục chứa tệp"),
    ],
    "Number": [
        ("<Inc Nr:001>", "Số thứ tự tăng dần, dạng 001"),
        ("<Inc Nr:0001>", "Số thứ tự tăng dần, dạng 0001"),
        ("<Inc Nr:00001>", "Số thứ tự tăng dần, dạng 00001"),
        ("<Inc Nr:1>", "Số thứ tự tăng dần"),
        ("<Inc Alpha>", "Chữ cái tăng dần: A, B, C..."),
        ("<Inc Hex>", "Số thập lục phân tăng dần"),
        ("<Inc Roman>", "Số La Mã tăng dần"),
    ],
    "Data": [
        ("<date:yyyy-MM-dd>", "Ngày: 2026-10-27"),
        ("<date:yyyyMMdd>", "Ngày dạng số: 20261027"),
        ("<time:HH-mm-ss>", "Giờ hiện tại: 14-30-05"),
    ],
    "File info": [
        ("<size>", "Kích thước tệp theo byte"),
        ("<name>", "Tên tệp gốc không có phần mở rộng"),
        ("<ext>", "Phần mở rộng của tệp gốc"),
    ],
    "Time": [
        ("<time:HH-mm-ss>", "Giờ hiện tại"),
        ("<date:yyyy-MM-dd_HH-mm>", "Ngày và giờ hiện tại"),
    ],
}


def normalize_extensions(value: str) -> set[str]:
    """Chuẩn hóa danh sách đuôi tệp nhập cách nhau bởi dấu phẩy/chấm phẩy."""
    result: set[str] = set()
    for item in re.split(r"[,;\s]+", value.strip()):
        if not item:
            continue
        item = item.lower()
        result.add(item if item.startswith(".") else f".{item}")
    return result


def matches_extension(path: Path, extensions: set[str], all_files: bool) -> bool:
    return all_files or path.suffix.lower() in extensions


def format_date(value: str, now: datetime) -> str:
    """Hỗ trợ yyyy, MM, dd, HH, mm, ss theo cú pháp dễ nhớ."""
    translated = value
    for source, target in (
        ("yyyy", "%Y"), ("YYYY", "%Y"), ("dd", "%d"),
        ("HH", "%H"), ("mm", "%M"), ("ss", "%S"), ("MM", "%m"),
    ):
        translated = translated.replace(source, target)
    return now.strftime(translated)


def increment_alpha(number: int) -> str:
    """Đổi 1, 2, ..., 26, 27 thành A, B, ..., Z, AA."""
    result = ""
    value = max(1, number)
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def increment_roman(number: int) -> str:
    values = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
              (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
              (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    result = ""
    value = max(1, number)
    for amount, symbol in values:
        count, value = divmod(value, amount)
        result += symbol * count
    return result


def render_pattern(pattern: str, source: Path, number: int, now: datetime | None = None) -> str:
    """Render mẫu tên; giữ phần mở rộng nếu mẫu không tạo ra đuôi mới."""
    now = now or datetime.now()

    def replace(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        date_match = DATE_RE.match(token)
        time_match = TIME_RE.match(token)
        inc_match = INC_RE.match(token)
        if token.lower() in {"name", "filename"}:
            return source.stem
        if token.lower() == "ext":
            return source.suffix.lstrip(".")
        if token.lower() == "parent":
            return source.parent.name
        if token.lower() == "size":
            try:
                return str(source.stat().st_size)
            except OSError:
                return "0"
        if date_match:
            return format_date(date_match.group(1).strip(), now)
        if time_match:
            return format_date(time_match.group(1).strip(), now)
        if inc_match:
            width = len(inc_match.group(1))
            return f"{number:0{width}d}"
        if token.lower() == "inc alpha":
            return increment_alpha(number)
        if token.lower() == "inc hex":
            return format(number, "X")
        if token.lower() == "inc roman":
            return increment_roman(number)
        return match.group(0)

    name = TOKEN_RE.sub(replace, pattern).strip()
    if not name:
        raise ValueError("Mẫu tên không được để trống.")
    if not Path(name).suffix:
        name += source.suffix
    return name


class FolderRenamer:
    """Theo dõi thư mục bằng polling, chạy nền và chỉ xử lý tệp mới."""

    def __init__(self, on_error: Callable[[str], None], on_log: Callable[[str], None]) -> None:
        self.on_error = on_error
        self.on_log = on_log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Lưu định danh của file theo đường dẫn. Nếu một file mới dùng lại
        # cùng tên cũ nhưng có định danh khác, nó vẫn được xem là file mới.
        self._seen: dict[Path, tuple[int, int, int, int]] = {}
        self._processed_ids: set[tuple[int, int]] = set()
        self._starting_number = 1
        self._number = 1
        self._lock = threading.Lock()
        self._log: logging.Logger | None = None
        self.folder: Path | None = None
        self.extensions: set[str] = set()
        self.all_files = False
        self.pattern = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        folder: Path,
        extensions: set[str],
        all_files: bool,
        pattern: str,
        starting_number: int = 1,
    ) -> None:
        if self.running:
            raise RuntimeError("Đang theo dõi.")
        if not folder.is_dir():
            raise ValueError("Thư mục theo dõi không tồn tại.")
        if not pattern.strip():
            raise ValueError("Vui lòng nhập mẫu tên.")
        if starting_number < 0:
            raise ValueError("Số bắt đầu phải lớn hơn hoặc bằng 0.")
        self.folder, self.extensions, self.all_files, self.pattern = folder, extensions, all_files, pattern
        self._starting_number = starting_number
        self._seen = {
            p: identity
            for p in folder.iterdir()
            if p.is_file()
            for identity in [self._identity(p)]
            if identity is not None
        }
        self._processed_ids.clear()
        self._stop.clear()
        self._number = self._starting_number
        self._log = logging.getLogger(f"folder-renamer-{id(self)}")
        self._log.setLevel(logging.INFO)
        self._log.handlers.clear()
        handler = logging.FileHandler(folder / "rename_log.txt", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        self._log.addHandler(handler)
        self._log.propagate = False
        self._log.info("Bắt đầu theo dõi: %s", folder)
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="file-renamer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        if self._log:
            self._log.info("Dừng theo dõi")
            for handler in self._log.handlers[:]:
                handler.close()
                self._log.removeHandler(handler)
        self._thread = None
        self.reset_sequence()

    def reset_sequence(self) -> None:
        """Đặt lại bộ đếm về số bắt đầu đã chọn."""
        with self._lock:
            self._number = self._starting_number

    def _watch_loop(self) -> None:
        assert self.folder is not None
        while not self._stop.wait(0.8):
            try:
                current = {
                    p: identity
                    for p in self.folder.iterdir()
                    if p.is_file()
                    for identity in [self._identity(p)]
                    if identity is not None
                }
            except OSError as exc:
                self._report(f"Không thể đọc thư mục: {exc}")
                continue
            new_files = sorted(
                (path for path, identity in current.items()
                 if self._seen.get(path) != identity),
                key=lambda path: path.name.lower(),
            )
            self._seen.update(current)
            for path in new_files:
                if self._stop.is_set() or path.name == "rename_log.txt":
                    continue
                if matches_extension(path, self.extensions, self.all_files):
                    file_id = self._file_id(path)
                    if file_id is not None and file_id in self._processed_ids:
                        self._seen[path] = current[path]
                        continue
                    self._process(path, file_id)

    @staticmethod
    def _identity(path: Path) -> tuple[int, int, int, int] | None:
        """Định danh file gồm thiết bị, inode, kích thước và thời điểm sửa."""
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    @staticmethod
    def _file_id(path: Path) -> tuple[int, int] | None:
        """Lấy mã thiết bị/inode để nhận diện cùng một tệp sau khi đổi tên."""
        try:
            stat = path.stat()
        except OSError:
            return None
        if stat.st_ino == 0:
            return None
        return stat.st_dev, stat.st_ino

    def _process(self, source: Path, file_id: tuple[int, int] | None = None) -> None:
        if not self._wait_until_stable(source):
            return
        try:
            with self._lock:
                # Kiểm tra lại sau khi chờ ghi xong để tránh xử lý trùng.
                file_id = file_id or self._file_id(source)
                if file_id is not None and file_id in self._processed_ids:
                    return
                target_name = render_pattern(self.pattern, source, self._number)
                target = source.with_name(target_name)
                self._number += 1
                if target == source:
                    if file_id is not None:
                        self._processed_ids.add(file_id)
                    self._write_log(f"Bỏ qua (tên không đổi): {source.name}")
                    return
                if target.exists():
                    message = f"Tên đích đã tồn tại, không đổi tên: {target.name} (từ {source.name})"
                    if file_id is not None:
                        self._processed_ids.add(file_id)
                    self._write_log("LỖI | " + message)
                    self._report(message)
                    return
                source.rename(target)
                if file_id is not None:
                    self._processed_ids.add(file_id)
                # Tên đích do chính ứng dụng tạo ra không phải là một tệp mới.
                target_identity = self._identity(target)
                if target_identity is not None:
                    self._seen[target] = target_identity
                self._write_log(f"Đã đổi: {source.name} -> {target.name}")
        except (OSError, ValueError) as exc:
            self._write_log(f"LỖI | {source.name}: {exc}")
            self._report(f"Không thể đổi tên {source.name}: {exc}")

    def _wait_until_stable(self, path: Path) -> bool:
        previous: tuple[int, int] | None = None
        for _ in range(15):
            if self._stop.is_set() or not path.exists():
                return False
            try:
                stat = path.stat()
            except OSError:
                return False
            current = (stat.st_size, stat.st_mtime_ns)
            if current == previous:
                return True
            previous = current
            time.sleep(0.4)
        self._report(f"Tệp chưa ổn định, bỏ qua: {path.name}")
        return False

    def _write_log(self, message: str) -> None:
        if self._log:
            self._log.info(message)
        self.on_log(message)

    def _report(self, message: str) -> None:
        self.on_error(message)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Đổi tên tệp tự động")
        self.geometry("780x620")
        self.minsize(520, 420)
        self.folder_var = tk.StringVar()
        self.custom_ext_var = tk.StringVar()
        self.all_files_var = tk.BooleanVar()
        self.pattern_var = tk.StringVar(value="TaiLieu_<date:yyyy-MM-dd>_<Inc Nr:0001>")
        self.start_number_var = tk.StringVar(value="1")
        self.status_var = tk.StringVar(value="Chưa chạy")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.renamer = FolderRenamer(
            lambda message: self.events.put(("error", message)),
            lambda message: self.events.put(("log", message)),
        )
        self.pattern_var.trace_add("write", self._pattern_changed)
        self._build_ui()
        self.after(200, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        content = ttk.Frame(self)
        content.grid(row=0, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        canvas = tk.Canvas(content, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        main = ttk.Frame(canvas, padding=14)
        window_id = canvas.create_window((0, 0), window=main, anchor="nw")

        def update_scroll_region(_event: tk.Event[tk.Misc] | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def stretch_content(event: tk.Event[tk.Misc]) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        main.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", stretch_content)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))
        ttk.Label(main, text="Đổi tên tệp tự động", font=("Segoe UI", 16, "bold")).pack(anchor="w")

        folder_frame = ttk.LabelFrame(main, text="1. Thư mục theo dõi", padding=8)
        folder_frame.pack(fill="x", pady=(12, 8))
        ttk.Entry(folder_frame, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_frame, text="Chọn...", command=self._choose_folder).pack(side="left", padx=(8, 0))

        ext_frame = ttk.LabelFrame(main, text="2. Loại tệp", padding=8)
        ext_frame.pack(fill="x", pady=8)
        self.ext_vars: dict[str, tk.BooleanVar] = {}
        ext_options = ttk.Frame(ext_frame)
        ext_options.pack(fill="x")
        for column, ext in enumerate((".png", ".tif", ".pdf", ".docx")):
            var = tk.BooleanVar(value=ext in {".png", ".tif", ".pdf", ".docx"})
            self.ext_vars[ext] = var
            ttk.Checkbutton(ext_options, text=ext, variable=var).grid(row=0, column=column, sticky="w", padx=(0, 14))
        ttk.Checkbutton(ext_frame, text="Mọi loại tệp", variable=self.all_files_var).pack(side="left")
        custom = ttk.Frame(ext_frame)
        custom.pack(fill="x", pady=(8, 0))
        ttk.Label(custom, text="Đuôi khác (cách nhau bằng dấu phẩy):").pack(side="left")
        ttk.Entry(custom, textvariable=self.custom_ext_var).pack(side="left", fill="x", expand=True, padx=(8, 0))

        pattern_frame = ttk.LabelFrame(main, text="3. Mẫu tên", padding=8)
        pattern_frame.pack(fill="x", pady=8)
        entry_row = ttk.Frame(pattern_frame)
        entry_row.pack(fill="x")
        self.pattern_entry = ttk.Entry(entry_row, textvariable=self.pattern_var)
        self.pattern_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(entry_row, text="</>", width=4,
                   command=lambda: self._select_formula_tab("Number")).pack(side="left", padx=(6, 0))

        formula_frame = ttk.LabelFrame(main, text="Công thức (nhấp vào một dòng để chèn tại vị trí con trỏ)", padding=6)
        formula_frame.pack(fill="x", pady=(0, 8))
        number_options = ttk.Frame(formula_frame)
        number_options.pack(fill="x", pady=(0, 5))
        ttk.Label(number_options, text="Số bắt đầu đếm:").pack(side="left")
        ttk.Spinbox(number_options, from_=0, to=999999999, width=12,
                    textvariable=self.start_number_var).pack(side="left", padx=(8, 0))
        ttk.Label(number_options, text="(ví dụ 1, 100 hoặc 2026)", foreground="#555").pack(side="left", padx=(8, 0))
        self.formula_notebook = ttk.Notebook(formula_frame, height=130)
        self.formula_notebook.pack(fill="both", expand=True)
        self.formula_lists: dict[str, tk.Listbox] = {}
        for group, formulas in FORMULAS.items():
            tab = ttk.Frame(self.formula_notebook, padding=4)
            self.formula_notebook.add(tab, text=group)
            listbox = tk.Listbox(tab, height=6, activestyle="none", exportselection=False,
                                 font=("Segoe UI", 9), relief="flat", borderwidth=0)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=listbox.yview)
            listbox.configure(yscrollcommand=scrollbar.set)
            listbox.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            for token, description in formulas:
                listbox.insert("end", f"{token}  -  {description}")
            listbox.bind("<ButtonRelease-1>", lambda event, name=group: self._insert_selected_formula(name))
            self.formula_lists[group] = listbox

        ttk.Label(pattern_frame, text="Có thể nhấp công thức ở trên; công thức sẽ được chèn ngay tại vị trí con trỏ.", foreground="#555").pack(anchor="w", pady=(5, 0))

        # Footer nằm ngoài vùng nội dung để luôn giữ các nút điều khiển
        # hiển thị khi người dùng kéo ngắn chiều cao cửa sổ.
        buttons = ttk.Frame(self, padding=(14, 0, 14, 10))
        buttons.grid(row=1, column=0, sticky="ew")
        self.start_button = ttk.Button(buttons, text="Bắt đầu", command=self._start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Dừng", command=self._stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(buttons, textvariable=self.status_var).pack(side="right")

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Chọn thư mục cần theo dõi")
        if selected:
            self.folder_var.set(selected)

    def _get_extensions(self) -> set[str]:
        selected = {ext for ext, var in self.ext_vars.items() if var.get()}
        return selected | normalize_extensions(self.custom_ext_var.get())

    def _select_formula_tab(self, group: str) -> None:
        """Chuyển sang nhóm công thức được chọn từ nút </>."""
        groups = list(FORMULAS)
        if group in groups:
            self.formula_notebook.select(groups.index(group))

    def _insert_selected_formula(self, group: str) -> None:
        """Chèn token của dòng đang chọn tại vị trí con trỏ trong ô mẫu tên."""
        listbox = self.formula_lists[group]
        selection = listbox.curselection()
        if not selection:
            return
        token = FORMULAS[group][selection[0]][0]
        self.pattern_entry.focus_set()
        try:
            cursor = self.pattern_entry.index(tk.INSERT)
        except tk.TclError:
            cursor = len(self.pattern_var.get())
        self.pattern_entry.insert(cursor, token)

    def _pattern_changed(self, *_args: object) -> None:
        """Đổi mẫu tên thì bộ đếm quay về số bắt đầu, không dùng số cũ."""
        if hasattr(self, "renamer"):
            self.renamer.reset_sequence()

    def _start(self) -> None:
        try:
            starting_number = int(self.start_number_var.get().strip())
            self.renamer.start(Path(self.folder_var.get().strip()), self._get_extensions(),
                               self.all_files_var.get(), self.pattern_var.get(), starting_number)
        except (TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Không thể bắt đầu", str(exc), parent=self)
            return
        self.status_var.set("Đang theo dõi")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

    def _stop(self) -> None:
        self.renamer.stop()
        self.status_var.set("Đã dừng")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == "error":
                    messagebox.showerror("Lỗi đổi tên tệp", message, parent=self)
        except queue.Empty:
            pass
        self.after(200, self._drain_events)

    def _close(self) -> None:
        self.renamer.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
