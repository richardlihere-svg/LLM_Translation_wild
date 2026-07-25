"""输出模块：将翻译结果写入 Data/output 目录。"""

from pathlib import Path

import config
import languages
import srt_io

# 输出文件统一使用的扩展名（docx/pdf 输入在 MVP 阶段输出为 txt）
_OUTPUT_EXT = {
    ".txt": ".txt",
    ".md": ".md",
    ".docx": ".txt",
    ".pdf": ".txt",
    ".srt": ".srt",
}


def output_extension(input_ext: str) -> str:
    return _OUTPUT_EXT.get(input_ext.lower(), ".txt")


def build_output_paths(input_path: Path, source_lang: str, target_lang: str, bilingual: bool):
    ext = output_extension(input_path.suffix)
    src_code = languages.to_code(source_lang)
    tgt_code = languages.to_code(target_lang)
    stem = input_path.stem
    pair = f"{src_code}-to-{tgt_code}"

    mono_path = config.OUTPUT_DIR / f"{stem}.{pair}.translated{ext}"
    bilingual_path = None
    if bilingual:
        bilingual_path = config.OUTPUT_DIR / f"{stem}.{pair}.bilingual{ext}"
    return mono_path, bilingual_path


def write_mono(results, output_path: Path):
    """results: List[(kind, original_text, translated_text)]"""
    parts = []
    for kind, original, translated in results:
        if kind == "raw":
            parts.append(original)
        else:
            parts.append(translated if translated is not None else original)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def write_srt_mono(entries, texts, output_path: Path):
    """entries: List[srt_io.SrtEntry]，texts: 与 entries 一一对应的译文列表。"""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(srt_io.format_srt(entries, texts), encoding="utf-8")


def write_srt_bilingual(entries, texts, output_path: Path):
    """在每条字幕的时间轴下，先输出原文再输出译文。"""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    combined = [f"{entry.text}\n{text}" for entry, text in zip(entries, texts)]
    output_path.write_text(srt_io.format_srt(entries, combined), encoding="utf-8")


def write_bilingual(results, output_path: Path, source_lang: str, target_lang: str):
    """results: List[(kind, original_text, translated_text)]"""
    sections = []
    for kind, original, translated in results:
        if kind == "raw":
            sections.append(original)
            continue
        block = (
            f"[{source_lang}]\n{original}\n\n"
            f"[{target_lang}]\n{translated if translated is not None else '（翻译失败，见日志）'}"
        )
        sections.append(block)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    separator = "\n\n" + ("-" * 40) + "\n\n"
    output_path.write_text(separator.join(sections) + "\n", encoding="utf-8")
