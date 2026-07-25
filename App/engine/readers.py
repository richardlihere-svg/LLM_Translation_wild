"""文档读取模块：将不同格式的文档解析为可翻译的文本块列表。"""

import re
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf", ".srt"}


class Block:
    """一个待处理的文本块。

    kind:
      - "text": 自然语言段落，需要翻译。
      - "raw":  原样保留的内容（如 markdown 代码块），不送入模型翻译。
    """

    __slots__ = ("kind", "content")

    def __init__(self, kind: str, content: str):
        self.kind = kind
        self.content = content

    def __repr__(self):
        preview = self.content[:30].replace("\n", "\\n")
        return f"Block({self.kind!r}, {preview!r}...)"


def split_paragraphs(text: str):
    """按空行将文本切分为段落列表，去除首尾空白。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def read_txt(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return [Block("text", p) for p in split_paragraphs(text)]


def read_md(path: Path):
    """读取 markdown 文件，跳过 ```代码块``` 不参与翻译，其余按段落切分。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    blocks = []
    lines = text.split("\n")
    buffer = []
    in_code = False
    code_buffer = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                if buffer:
                    blocks.extend(Block("text", p) for p in split_paragraphs("\n".join(buffer)))
                    buffer = []
                in_code = True
                code_buffer = [line]
            else:
                code_buffer.append(line)
                blocks.append(Block("raw", "\n".join(code_buffer)))
                code_buffer = []
                in_code = False
        else:
            if in_code:
                code_buffer.append(line)
            else:
                buffer.append(line)

    if buffer:
        blocks.extend(Block("text", p) for p in split_paragraphs("\n".join(buffer)))
    if code_buffer:  # 未闭合的代码块，原样保留
        blocks.append(Block("raw", "\n".join(code_buffer)))

    return blocks


def read_docx(path: Path):
    from docx import Document

    doc = Document(str(path))
    blocks = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append(Block("text", text))
    return blocks


def read_pdf(path: Path):
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks = []
    for page in reader.pages:
        text = page.extract_text() or ""
        blocks.extend(Block("text", p) for p in split_paragraphs(text))
    return blocks


def read_file(path: Path):
    ext = path.suffix.lower()
    if ext == ".txt":
        return read_txt(path)
    if ext == ".md":
        return read_md(path)
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pdf":
        return read_pdf(path)
    raise ValueError(f"不支持的文件格式: {ext}")
