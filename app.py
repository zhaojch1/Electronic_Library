"""一键式界面入口（用户主路径）。

界面极简：唯一的交互控件是「生成大纲」按钮。
用户点击后，程序在后台黑箱中自动完成「出题 → 并发写作 → 评审择优」，
最终只把**择优后的 1 份大纲**呈现出来。
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import config
import pipeline


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self.running = False

        root.title("电子图书馆 · AI 大纲生成")
        root.geometry("760x620")
        root.minsize(560, 460)

        # 顶部：唯一按钮
        top = ttk.Frame(root, padding=(16, 16, 16, 8))
        top.pack(fill="x")
        self.button = ttk.Button(top, text="生成大纲", command=self.on_click)
        self.button.pack(fill="x", ipady=10)

        # 进度条（非交互控件）
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", padx=16)

        # 状态文本
        self.status = tk.StringVar(value="点击上方按钮，开始自动创作一本新书的大纲。")
        ttk.Label(root, textvariable=self.status, anchor="w",
                  foreground="#555").pack(fill="x", padx=16, pady=(6, 4))

        # 结果展示区（只读）
        self.result = scrolledtext.ScrolledText(root, wrap="word", state="disabled",
                                                font=("Microsoft YaHei UI", 11))
        self.result.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        root.after(150, self._poll)

    # ------------------------------------------------------------------ #
    def on_click(self) -> None:
        if self.running:
            return
        self.running = True
        self.button.config(state="disabled", text="正在生成…")
        self.progress.start(12)
        self._set_status("正在启动创作流程…")
        self._set_result("")

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            result = pipeline.run_pipeline(progress=self._emit)
            self.queue.put(("done", result))
        except Exception as e:  # noqa: BLE001
            self.queue.put(("error", str(e)))

    def _emit(self, _stage: str, message: str) -> None:
        self.queue.put(("status", message))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "status":
                    self._set_status(payload)
                elif kind == "done":
                    self._on_done(payload)
                elif kind == "error":
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    # ------------------------------------------------------------------ #
    def _on_done(self, result: dict) -> None:
        self._finish()
        topic = result["topic"]
        header = (
            f"《{topic['title']}》\n"
            f"题材：{topic['genre']} ｜ 目标读者：{topic['target_audience']} ｜ "
            f"风格：{result['winner_persona']}\n"
            + "─" * 60 + "\n\n"
        )
        self._set_result(header + result["winner_outline"])
        tok = result["usage"].get("total_tokens", 0)
        self._set_status(
            f"完成：已择优生成 1 份大纲（{result['winner_persona']}）。"
            f"本次消耗 {tok} tokens，产物目录：output/{result['book_id']}"
        )

    def _on_error(self, message: str) -> None:
        self._finish()
        self._set_status("生成失败。")
        messagebox.showerror("生成失败", message)

    def _finish(self) -> None:
        self.running = False
        self.progress.stop()
        self.button.config(state="normal", text="生成大纲")

    def _set_status(self, text: str) -> None:
        self.status.set(text)

    def _set_result(self, text: str) -> None:
        self.result.config(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text)
        self.result.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
