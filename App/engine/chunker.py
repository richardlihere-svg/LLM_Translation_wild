"""分块模块：把读取到的文本块整理为大小可控、可逐一翻译的任务单元。"""

import re

from readers import Block

# 句子结尾标点（中/日/英常见），用于在超长段落内部寻找切分点
_SENTENCE_END = re.compile(r"(?<=[。！？!?.\n])\s*")


def split_long_text(text: str, max_chars: int):
    """将一段过长的文本按句子边界切分为多个不超过 max_chars 的片段。"""
    sentences = _SENTENCE_END.split(text)
    parts = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if current and len(current) + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current += sentence
    if current:
        parts.append(current)

    # 极端情况：单句本身就超过 max_chars，做硬切分
    final = []
    for part in parts:
        if len(part) > max_chars:
            for i in range(0, len(part), max_chars):
                final.append(part[i:i + max_chars])
        else:
            final.append(part)
    return final or [text]


class Chunk:
    """一个翻译任务单元：对应一个段落，或一个超长段落切分出的片段。"""

    __slots__ = ("kind", "content")

    def __init__(self, kind: str, content: str):
        self.kind = kind  # "text" 或 "raw"
        self.content = content


def make_chunks(blocks, max_chars: int = 1500):
    chunks = []
    for block in blocks:
        if block.kind == "raw":
            chunks.append(Chunk("raw", block.content))
            continue
        if len(block.content) <= max_chars:
            chunks.append(Chunk("text", block.content))
        else:
            for part in split_long_text(block.content, max_chars):
                chunks.append(Chunk("text", part))
    return chunks
