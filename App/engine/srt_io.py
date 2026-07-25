"""SRT 字幕文件的解析与生成。"""

import re

_BLOCK_SPLIT = re.compile(r"\n\s*\n")


class SrtEntry:
    """一条字幕条目：序号 + 时间轴 + 多行文本。"""

    __slots__ = ("index", "time_line", "text_lines")

    def __init__(self, index: str, time_line: str, text_lines):
        self.index = index
        self.time_line = time_line
        self.text_lines = text_lines

    @property
    def text(self) -> str:
        return "\n".join(self.text_lines)


def parse_srt(content: str):
    """将 SRT 文本解析为字幕条目列表，无法识别的片段会被跳过。"""
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip("﻿")
    entries = []
    for block in _BLOCK_SPLIT.split(content.strip()):
        lines = block.split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        entries.append(SrtEntry(lines[0].strip(), lines[1].strip(), lines[2:]))
    return entries


def format_srt(entries, texts=None) -> str:
    """将字幕条目重新组装为 SRT 文本。

    texts: 可选的替换文本列表（与 entries 一一对应，每项可包含多行），
    省略时使用条目原文。
    """
    parts = []
    for i, entry in enumerate(entries):
        text = texts[i] if texts is not None else entry.text
        parts.append(f"{entry.index}\n{entry.time_line}\n{text}")
    return "\n\n".join(parts) + "\n"
