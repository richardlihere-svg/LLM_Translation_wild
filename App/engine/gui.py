"""本地 LLM 文档翻译器 - 简单 GUI 入口。"""

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import config
import languages
import llm_client
import logger as logger_mod
import readers
import translator

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    HAS_DND = True
except ImportError:
    HAS_DND = False

STYLES = ["通顺", "直译", "wild"]

STATUS_PENDING = "待处理"
STATUS_RUNNING = "翻译中"
STATUS_DONE = "完成"
STATUS_DONE_PARTIAL = "完成(部分失败)"
STATUS_FAILED = "失败"
STATUS_CANCELLED = "已取消"


class TranslatorApp:
    def __init__(self, root: tk.Tk, initial_path: str = ""):
        self.root = root
        self.root.title("本地 LLM 文档翻译器")
        self.root.geometry("900x680")
        self.root.minsize(760, 560)

        self.settings = config.load_settings()
        self.msg_queue: "queue.Queue" = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.queue_items: dict[str, Path] = {}  # iid -> 文件路径

        self._build_ui()
        self._load_initial_values()
        self._refresh_models(initial=True)
        if initial_path:
            self._add_queue_item(Path(initial_path))

        self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # ---- 翻译设置 ----
        settings_frame = ttk.LabelFrame(self.root, text="翻译设置（应用于队列中的所有文件）")
        settings_frame.pack(fill="x", padx=10, pady=(10, 5))
        for col in range(4):
            settings_frame.columnconfigure(col, weight=1)

        ttk.Label(settings_frame, text="源语言:").grid(row=0, column=0, sticky="w", **pad)
        self.source_var = tk.StringVar()
        ttk.Combobox(
            settings_frame, textvariable=self.source_var, values=languages.display_names(), state="readonly"
        ).grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(settings_frame, text="目标语言:").grid(row=0, column=2, sticky="w", **pad)
        self.target_var = tk.StringVar()
        ttk.Combobox(
            settings_frame, textvariable=self.target_var, values=languages.display_names(), state="readonly"
        ).grid(row=0, column=3, sticky="ew", **pad)

        ttk.Label(settings_frame, text="模型:").grid(row=1, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(settings_frame, textvariable=self.model_var, values=[], state="readonly")
        self.model_combo.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Button(settings_frame, text="刷新模型", command=lambda: self._refresh_models(initial=False)).grid(
            row=1, column=3, sticky="e", **pad
        )

        ttk.Label(settings_frame, text="翻译风格:").grid(row=2, column=0, sticky="w", **pad)
        self.style_var = tk.StringVar()
        ttk.Combobox(settings_frame, textvariable=self.style_var, values=STYLES, state="readonly").grid(
            row=2, column=1, sticky="ew", **pad
        )

        self.bilingual_var = tk.BooleanVar()
        ttk.Checkbutton(settings_frame, text="同时输出双语对照", variable=self.bilingual_var).grid(
            row=2, column=2, columnspan=2, sticky="w", **pad
        )

        # ---- 文件队列 ----
        queue_label = "文件队列（按顺序依次翻译，可将文件/文件夹拖拽到下方列表）" if HAS_DND else "文件队列（按顺序依次翻译）"
        queue_frame = ttk.LabelFrame(self.root, text=queue_label)
        queue_frame.pack(fill="both", expand=False, padx=10, pady=5)

        tree_container = ttk.Frame(queue_frame)
        tree_container.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        self.queue_tree = ttk.Treeview(
            tree_container, columns=("status",), show="tree headings", height=6, selectmode="extended"
        )
        self.queue_tree.heading("#0", text="文件")
        self.queue_tree.heading("status", text="状态")
        self.queue_tree.column("#0", width=560)
        self.queue_tree.column("status", width=120, anchor="center")
        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=tree_scroll.set)
        self.queue_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        if HAS_DND:
            self.queue_tree.drop_target_register(DND_FILES)
            self.queue_tree.dnd_bind("<<Drop>>", self._on_drop_files)
            tree_container.drop_target_register(DND_FILES)
            tree_container.dnd_bind("<<Drop>>", self._on_drop_files)

        queue_btn_frame = ttk.Frame(queue_frame)
        queue_btn_frame.pack(fill="x", padx=6, pady=6)
        self.add_files_btn = ttk.Button(queue_btn_frame, text="添加文件...", command=self._add_files)
        self.add_files_btn.pack(side="left", padx=4)
        self.add_folder_btn = ttk.Button(queue_btn_frame, text="添加文件夹...", command=self._add_folder)
        self.add_folder_btn.pack(side="left", padx=4)
        self.remove_btn = ttk.Button(queue_btn_frame, text="移除选中", command=self._remove_selected)
        self.remove_btn.pack(side="left", padx=4)
        self.clear_btn = ttk.Button(queue_btn_frame, text="清空队列", command=self._clear_queue)
        self.clear_btn.pack(side="left", padx=4)

        # ---- 操作按钮 ----
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=(0, 5))
        self.start_btn = ttk.Button(btn_frame, text="开始翻译", command=self._on_start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="打开输出目录", command=lambda: self._open_dir(config.OUTPUT_DIR)).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="打开日志目录", command=lambda: self._open_dir(config.LOGS_DIR)).pack(
            side="left", padx=4
        )

        # ---- 任务状态 ----
        status_frame = ttk.LabelFrame(self.root, text="任务状态")
        status_frame.pack(fill="x", padx=10, pady=5)

        self.queue_progress_var = tk.StringVar(value="队列进度：0 / 0")
        ttk.Label(status_frame, textvariable=self.queue_progress_var).pack(anchor="w", padx=8, pady=(6, 0))

        progress_row = ttk.Frame(status_frame)
        progress_row.pack(fill="x")
        self.status_var = tk.StringVar(value="待处理")
        ttk.Label(progress_row, textvariable=self.status_var).pack(side="left", padx=8, pady=6)
        self.progress_bar = ttk.Progressbar(progress_row, mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=8, pady=6)
        self.progress_label_var = tk.StringVar(value="0 / 0")
        ttk.Label(progress_row, textvariable=self.progress_label_var).pack(side="left", padx=8, pady=6)

        # ---- 日志 ----
        log_frame = ttk.LabelFrame(self.root, text="日志")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_text.tag_config("error", foreground="#c0392b")
        self.log_text.tag_config("warning", foreground="#b8860b")

    def _load_initial_values(self):
        self.source_var.set(self.settings.get("last_source_lang", languages.DEFAULT_SOURCE))
        self.target_var.set(self.settings.get("last_target_lang", languages.DEFAULT_TARGET))
        self.style_var.set(self.settings.get("last_style", "通顺"))
        self.bilingual_var.set(bool(self.settings.get("bilingual_output", True)))

    # ------------------------------------------------------------------
    # 文件队列管理
    # ------------------------------------------------------------------
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择待翻译文档（可多选）",
            initialdir=str(config.INPUT_DIR),
            filetypes=[
                ("支持的文档", "*.txt *.md *.docx *.pdf *.srt"),
                ("所有文件", "*.*"),
            ],
        )
        for p in paths:
            self._add_queue_item(Path(p))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹（将添加其中所有支持的文档）", initialdir=str(config.INPUT_DIR))
        if not folder:
            return
        folder_path = Path(folder)
        found = []
        for ext in sorted(readers.SUPPORTED_EXTENSIONS):
            found.extend(folder_path.glob(f"*{ext}"))
        for p in sorted(found):
            self._add_queue_item(p)

    def _add_queue_item(self, path: Path) -> bool:
        if not path.exists() or path.suffix.lower() not in readers.SUPPORTED_EXTENSIONS:
            return False
        iid = str(path.resolve())
        if iid in self.queue_items:
            return False
        self.queue_items[iid] = path
        self.queue_tree.insert("", "end", iid=iid, text=path.name, values=(STATUS_PENDING,))
        return True

    def _on_drop_files(self, event):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        skipped = []
        for raw in self.root.tk.splitlist(event.data):
            path = Path(raw)
            if path.is_dir():
                for ext in sorted(readers.SUPPORTED_EXTENSIONS):
                    for f in sorted(path.glob(f"*{ext}")):
                        self._add_queue_item(f)
                continue
            if not self._add_queue_item(path):
                skipped.append(path.name)
        if skipped:
            self._append_log(
                "warning",
                f"以下文件未添加（格式不支持或已在队列中）：{', '.join(skipped)}",
            )

    def _remove_selected(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        for iid in self.queue_tree.selection():
            self.queue_tree.delete(iid)
            self.queue_items.pop(iid, None)

    def _clear_queue(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self.queue_tree.delete(*self.queue_tree.get_children())
        self.queue_items.clear()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def _refresh_models(self, initial: bool):
        host = self.settings.get("ollama_host", "http://127.0.0.1:11434")
        client = llm_client.OllamaClient(host=host, timeout=5)
        try:
            models = client.list_models()
        except llm_client.OllamaError as e:
            self.model_combo["values"] = []
            if initial:
                self._append_log(
                    "warning",
                    f"未能连接本地 Ollama 服务：{e}\n"
                    "请确认已安装并启动 Ollama（任务栏图标，或运行 `ollama serve`），然后点击\"刷新模型\"。",
                )
            else:
                messagebox.showwarning("未连接到 Ollama", str(e))
            return

        if not models:
            self.model_combo["values"] = []
            self._append_log(
                "warning",
                "未检测到任何已安装的模型。请在命令行运行，例如：ollama pull qwen2.5:7b-instruct",
            )
            return

        self.model_combo["values"] = models
        last_model = self.settings.get("last_model", "")
        if last_model in models:
            self.model_var.set(last_model)
        else:
            self.model_var.set(models[0])
        if initial:
            self._append_log("info", f"检测到已安装模型：{', '.join(models)}")

    def _on_start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        iids = list(self.queue_tree.get_children())
        if not iids:
            messagebox.showerror("队列为空", "请先点击\"添加文件...\"或\"添加文件夹...\"，将待翻译的文件加入队列。")
            return

        items = []
        for iid in iids:
            p = self.queue_items[iid]
            if not p.exists():
                messagebox.showerror("文件不存在", f"找不到文件：\n{p}")
                return
            items.append((iid, p))

        model = self.model_var.get().strip()
        if not model:
            messagebox.showerror("缺少模型", "请先选择本地模型（如未安装，请先用 ollama pull 下载）。")
            return

        source_lang = self.source_var.get()
        target_lang = self.target_var.get()
        style = self.style_var.get() or "通顺"
        bilingual = bool(self.bilingual_var.get())

        # 保存设置，方便下次启动沿用
        self.settings.update(
            {
                "last_model": model,
                "last_source_lang": source_lang,
                "last_target_lang": target_lang,
                "last_style": style,
                "bilingual_output": bilingual,
            }
        )
        config.save_settings(self.settings)

        self._clear_log()
        for iid, _ in items:
            self.queue_tree.set(iid, "status", STATUS_PENDING)
        self.status_var.set("准备中")
        self.progress_bar["value"] = 0
        self.progress_label_var.set("0 / 0")
        self.queue_progress_var.set(f"队列进度：0 / {len(items)}")

        self.start_btn.config(state="disabled")
        self.add_files_btn.config(state="disabled")
        self.add_folder_btn.config(state="disabled")
        self.remove_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.stop_event.clear()

        self.worker_thread = threading.Thread(
            target=self._run_queue,
            args=(items, source_lang, target_lang, model, style, bilingual),
            daemon=True,
        )
        self.worker_thread.start()

    def _on_stop(self):
        self.stop_event.set()
        self.status_var.set("正在停止...")

    def _on_close(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if not messagebox.askyesno("任务进行中", "翻译任务仍在进行，确定要关闭程序吗？"):
                return
            self.stop_event.set()
        self.root.destroy()

    @staticmethod
    def _open_dir(path: Path):
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))  # noqa: S606 (Windows 专用)

    # ------------------------------------------------------------------
    # 工作线程：按顺序处理队列中的每个文件
    # ------------------------------------------------------------------
    def _run_queue(self, items, source_lang, target_lang, model, style, bilingual):
        total = len(items)
        summary = {"done": 0, "partial": 0, "failed": 0, "cancelled": 0}
        stopped_early = False

        for i, (iid, input_path) in enumerate(items, start=1):
            if stopped_early:
                self.msg_queue.put(("item_status", iid, STATUS_CANCELLED))
                summary["cancelled"] += 1
                continue

            self.msg_queue.put(("item_status", iid, STATUS_RUNNING))
            self.msg_queue.put(("queue_progress", i, total, input_path.name))
            self.msg_queue.put(("file_progress", 0, 0, "准备中"))

            task_logger = logger_mod.TaskLogger(task_name=input_path.stem)

            def log_cb(level, message, _name=input_path.name):
                task_logger.write(level, message)
                self.msg_queue.put(("log", level, f"[{_name}] {message}"))

            def progress_cb(done, total_chunks, status):
                self.msg_queue.put(("file_progress", done, total_chunks, status))

            def should_stop():
                return self.stop_event.is_set()

            try:
                result = translator.translate_document(
                    input_path,
                    source_lang,
                    target_lang,
                    model,
                    style,
                    bilingual,
                    self.settings,
                    log_cb,
                    progress_cb,
                    should_stop,
                )
                if result["failed_chunks"]:
                    self.msg_queue.put(("item_status", iid, STATUS_DONE_PARTIAL))
                    summary["partial"] += 1
                else:
                    self.msg_queue.put(("item_status", iid, STATUS_DONE))
                    summary["done"] += 1
            except translator.StopRequested:
                self.msg_queue.put(("item_status", iid, STATUS_CANCELLED))
                summary["cancelled"] += 1
                stopped_early = True
            except (llm_client.OllamaError, FileNotFoundError, ValueError) as e:
                log_cb("error", str(e))
                self.msg_queue.put(("item_status", iid, STATUS_FAILED))
                summary["failed"] += 1
            except Exception as e:  # noqa: BLE001 - 兜底，避免线程静默崩溃
                log_cb("error", f"未预期的错误：{e!r}")
                self.msg_queue.put(("item_status", iid, STATUS_FAILED))
                summary["failed"] += 1
            finally:
                task_logger.close()

        self.msg_queue.put(("queue_done", summary))

    # ------------------------------------------------------------------
    # 主线程：消息队列轮询
    # ------------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, level, message = item
                    self._append_log(level, message)
                elif kind == "file_progress":
                    _, done, total, status = item
                    self._update_progress(done, total, status)
                elif kind == "queue_progress":
                    _, i, total, name = item
                    self.queue_progress_var.set(f"队列进度：{i} / {total}（当前：{name}）")
                elif kind == "item_status":
                    _, iid, status = item
                    if self.queue_tree.exists(iid):
                        self.queue_tree.set(iid, "status", status)
                elif kind == "queue_done":
                    _, summary = item
                    self._on_queue_done(summary)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _update_progress(self, done, total, status):
        self.status_var.set(status)
        if total > 0:
            self.progress_bar["maximum"] = total
            self.progress_bar["value"] = done
        else:
            self.progress_bar["value"] = 0
        self.progress_label_var.set(f"{done} / {total}")

    def _on_queue_done(self, summary):
        self.start_btn.config(state="normal")
        self.add_files_btn.config(state="normal")
        self.add_folder_btn.config(state="normal")
        self.remove_btn.config(state="normal")
        self.clear_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

        if summary["cancelled"] and not (summary["done"] or summary["partial"] or summary["failed"]):
            self.status_var.set("已取消")
        else:
            self.status_var.set("队列处理完成")

        lines = [
            "队列处理完成。",
            "",
            f"成功：{summary['done']}",
            f"部分失败：{summary['partial']}",
            f"失败：{summary['failed']}",
        ]
        if summary["cancelled"]:
            lines.append(f"已取消：{summary['cancelled']}")
        lines.append("")
        lines.append(f"输出目录：{config.OUTPUT_DIR}")
        messagebox.showinfo("队列完成", "\n".join(lines))

    # ------------------------------------------------------------------
    # 日志显示
    # ------------------------------------------------------------------
    def _append_log(self, level: str, message: str):
        self.log_text.config(state="normal")
        tag = level if level in ("error", "warning") else None
        line = f"[{level.upper()}] {message}\n"
        if tag:
            self.log_text.insert("end", line, tag)
        else:
            self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")


def main():
    config.ensure_dirs()
    initial_path = sys.argv[1] if len(sys.argv) > 1 else ""
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = TranslatorApp(root, initial_path=initial_path)
    if not HAS_DND:
        app._append_log(
            "warning",
            "未安装 tkinterdnd2，暂不支持拖拽添加文件。运行 `pip install -r requirements.txt` 后重启即可启用。",
        )
    root.mainloop()


if __name__ == "__main__":
    main()
