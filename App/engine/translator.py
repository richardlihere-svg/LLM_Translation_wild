"""翻译主流程：读取 -> 切分 -> 调用本地模型逐块翻译 -> 合并 -> 写出。"""

import re
from pathlib import Path

import chunker
import languages
import llm_client
import readers
import srt_io
import writer

# 每次请求模型批量翻译的字幕条数上限
SRT_BATCH_SIZE = 20

_SRT_MARK_RE = re.compile(r"<<<(\d+)>>>")

STYLE_INSTRUCTIONS = {
    "直译": "请尽量贴近原文的句子结构和表达顺序逐句翻译，保留原文的语序与细节，不要随意增删信息。",
    "通顺": "请在准确传达原意的基础上，使用目标语言中自然、流畅、符合表达习惯的句子，可适当调整语序。",
    "wild": (
        "本次翻译内容为成人向影片字幕，目标读者是 30-50 岁的成年观众。"
        "请在不改变原文语义、信息量和情节走向的前提下，将台词改写得更加生动、口语化、有感染力，"
        "语气词、感叹词、呻吟声等可结合目标语言的字幕组习惯进行本地化处理，使整体表达更'攒劲'、更有临场感，"
        "避免生硬直译或过于书面化、医学化的措辞；如原文出现拟声词，可用目标语言中更自然的对应拟声词替代。"
    ),
}


class StopRequested(Exception):
    """用户主动取消任务时抛出。"""


def build_system_prompt(source_lang_prompt: str, target_lang_prompt: str, style: str, is_markdown: bool) -> str:
    style_instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["通顺"])
    lines = [
        "You are a professional document translator.",
        f"将用户输入的文本从 {source_lang_prompt} 翻译为 {target_lang_prompt}。",
        style_instruction,
    ]
    if is_markdown:
        lines.append("保留所有 Markdown 标记符号（如 #、*、-、>、链接、行内代码等），仅翻译其中的自然语言文字内容。")
    lines.append(
        "只输出翻译结果本身，不要添加任何解释、说明、引号或前后缀。"
        "专有名词、代码、数字、符号等按惯例保留原文形式。"
    )
    return "\n".join(lines)


def translate_document(
    input_path: Path,
    source_lang: str,
    target_lang: str,
    model: str,
    style: str,
    bilingual: bool,
    settings: dict,
    log,
    progress,
    should_stop,
):
    """执行一次完整的文档翻译任务。

    log(level, message): 输出日志，level 取值 "info"/"warning"/"error"。
    progress(done, total, status): 汇报当前进度与状态文案。
    should_stop() -> bool: 是否需要中止任务。

    返回 dict，包含输出路径与失败块数统计。
    """
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件：{input_path}")
    if input_path.suffix.lower() not in readers.SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文件格式：{input_path.suffix}（支持 .txt / .md / .docx / .pdf / .srt）")

    if input_path.suffix.lower() == ".srt":
        return translate_srt(
            input_path, source_lang, target_lang, model, style, bilingual, settings, log, progress, should_stop
        )

    client = llm_client.OllamaClient(
        host=settings.get("ollama_host", "http://127.0.0.1:11434"),
        timeout=settings.get("request_timeout", 180),
    )

    progress(0, 0, "检查本地模型")
    if not client.is_available():
        raise llm_client.OllamaError(
            "无法连接本地 Ollama 服务，请确认 Ollama 已启动（系统托盘图标，或在命令行运行 `ollama serve`）。"
        )
    available_models = client.list_models()
    if model not in available_models:
        installed = "、".join(available_models) if available_models else "（无）"
        raise llm_client.OllamaError(
            f"模型 \"{model}\" 未安装。请先在命令行运行：ollama pull {model}\n"
            f"当前已安装模型：{installed}"
        )

    progress(0, 0, "读取中")
    log("info", f"开始处理文件：{input_path}")
    blocks = readers.read_file(input_path)
    if not blocks:
        raise ValueError("文档内容为空或无法提取到文本")

    progress(0, 0, "切分中")
    chunks = chunker.make_chunks(blocks, max_chars=settings.get("chunk_max_chars", 1500))
    total = len(chunks)
    log("info", f"共切分为 {total} 个文本块")

    is_markdown = input_path.suffix.lower() == ".md"
    system_prompt = build_system_prompt(
        languages.to_prompt_name(source_lang),
        languages.to_prompt_name(target_lang),
        style,
        is_markdown,
    )

    results = []
    failed = 0
    progress(0, total, "翻译中")
    for i, chunk in enumerate(chunks, start=1):
        if should_stop():
            log("warning", "用户已取消任务")
            raise StopRequested()

        if chunk.kind == "raw":
            results.append(("raw", chunk.content, None))
            progress(i, total, "翻译中")
            continue

        try:
            translated = client.generate(
                model=model,
                prompt=chunk.content,
                system=system_prompt,
                options={"temperature": 0.2},
            ).strip()
            if not translated:
                raise llm_client.OllamaError("模型返回结果为空")
            results.append(("text", chunk.content, translated))
            log("info", f"[{i}/{total}] 翻译完成（{len(chunk.content)} 字符）")
        except llm_client.OllamaError as e:
            failed += 1
            results.append(("text", chunk.content, None))
            log("error", f"[{i}/{total}] 翻译失败，已保留原文：{e}")

        progress(i, total, "翻译中")

    progress(total, total, "写出中")
    mono_path, bilingual_path = writer.build_output_paths(input_path, source_lang, target_lang, bilingual)
    writer.write_mono(results, mono_path)
    log("info", f"已写出译文：{mono_path}")
    if bilingual_path:
        writer.write_bilingual(results, bilingual_path, source_lang, target_lang)
        log("info", f"已写出双语对照：{bilingual_path}")

    progress(total, total, "完成" if failed == 0 else "完成（部分文本块翻译失败，详见日志）")
    return {
        "mono_path": mono_path,
        "bilingual_path": bilingual_path,
        "failed_chunks": failed,
        "total_chunks": total,
    }


def build_srt_system_prompt(source_lang_prompt: str, target_lang_prompt: str, style: str) -> str:
    style_instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["通顺"])
    lines = [
        "You are a professional subtitle translator.",
        f"将用户输入的字幕文本从 {source_lang_prompt} 翻译为 {target_lang_prompt}。",
        style_instruction,
        "输入由若干条字幕组成，每条字幕以 <<<编号>>> 单独一行开头标记，后面是该条字幕的原文（可能有多行）。",
        "请按相同的编号和顺序逐条翻译并输出，格式为：<<<编号>>> 后换行，紧跟译文内容，每条之间用一个空行分隔。",
        "条目数量和编号必须与输入完全一致，不要合并、拆分、增加或删除条目，不要翻译或修改 <<<编号>>> 标记本身。",
        "只输出翻译结果本身，不要添加任何解释、说明或前后缀。专有名词、数字、符号按惯例保留原文形式。",
    ]
    return "\n".join(lines)


def _make_srt_batches(entries, max_chars: int, batch_size: int):
    """将字幕条目分组为若干批次，每批不超过 batch_size 条，且字符数不超过 max_chars。"""
    batches = []
    current = []
    current_chars = 0
    for idx, entry in enumerate(entries):
        text_len = len(entry.text)
        if current and (len(current) >= batch_size or current_chars + text_len > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(idx)
        current_chars += text_len
    if current:
        batches.append(current)
    return batches


def _parse_srt_batch_response(response: str, expected: int):
    """解析模型返回的 <<<编号>>> 格式批量翻译结果，数量或编号不匹配时抛出 ValueError。"""
    pieces = _SRT_MARK_RE.split(response)
    result = {}
    for j in range(1, len(pieces) - 1, 2):
        result[int(pieces[j])] = pieces[j + 1].strip()
    if sorted(result.keys()) != list(range(1, expected + 1)):
        raise ValueError("批量翻译结果的条目数量或编号与输入不匹配")
    return [result[i] for i in range(1, expected + 1)]


def _translate_srt_batch(client, model, system_prompt, texts):
    prompt = "\n\n".join(f"<<<{i}>>>\n{t}" for i, t in enumerate(texts, start=1))
    response = client.generate(model=model, prompt=prompt, system=system_prompt, options={"temperature": 0.2})
    return _parse_srt_batch_response(response, len(texts))


def translate_srt(
    input_path: Path,
    source_lang: str,
    target_lang: str,
    model: str,
    style: str,
    bilingual: bool,
    settings: dict,
    log,
    progress,
    should_stop,
):
    """SRT 字幕翻译：按时间轴条目分批送入模型翻译，保留序号与时间轴不变。"""
    client = llm_client.OllamaClient(
        host=settings.get("ollama_host", "http://127.0.0.1:11434"),
        timeout=settings.get("request_timeout", 180),
    )

    progress(0, 0, "检查本地模型")
    if not client.is_available():
        raise llm_client.OllamaError(
            "无法连接本地 Ollama 服务，请确认 Ollama 已启动（系统托盘图标，或在命令行运行 `ollama serve`）。"
        )
    available_models = client.list_models()
    if model not in available_models:
        installed = "、".join(available_models) if available_models else "（无）"
        raise llm_client.OllamaError(
            f"模型 \"{model}\" 未安装。请先在命令行运行：ollama pull {model}\n"
            f"当前已安装模型：{installed}"
        )

    progress(0, 0, "读取中")
    log("info", f"开始处理文件：{input_path}")
    content = input_path.read_text(encoding="utf-8-sig", errors="replace")
    entries = srt_io.parse_srt(content)
    if not entries:
        raise ValueError("字幕内容为空或不是标准 SRT 格式")

    max_chars = settings.get("chunk_max_chars", 1500)
    batches = _make_srt_batches(entries, max_chars, SRT_BATCH_SIZE)
    total = len(batches)
    log("info", f"共 {len(entries)} 条字幕，分为 {total} 批翻译")

    system_prompt = build_srt_system_prompt(
        languages.to_prompt_name(source_lang),
        languages.to_prompt_name(target_lang),
        style,
    )

    translations = [None] * len(entries)
    failed = 0
    progress(0, total, "翻译中")
    for batch_no, indices in enumerate(batches, start=1):
        if should_stop():
            log("warning", "用户已取消任务")
            raise StopRequested()

        texts = [entries[idx].text for idx in indices]
        try:
            translated_texts = _translate_srt_batch(client, model, system_prompt, texts)
        except (llm_client.OllamaError, ValueError) as e:
            log("warning", f"[{batch_no}/{total}] 批量翻译失败（{e}），改为逐条翻译")
            translated_texts = []
            for i, text in enumerate(texts):
                try:
                    t = client.generate(
                        model=model, prompt=text, system=system_prompt, options={"temperature": 0.2}
                    ).strip()
                    if not t:
                        raise llm_client.OllamaError("模型返回结果为空")
                    translated_texts.append(t)
                except llm_client.OllamaError as e2:
                    translated_texts.append(None)
                    failed += 1
                    log("error", f"字幕 {entries[indices[i]].index} 翻译失败，已保留原文：{e2}")

        for idx, t in zip(indices, translated_texts):
            translations[idx] = t

        log("info", f"[{batch_no}/{total}] 翻译完成（{len(indices)} 条字幕）")
        progress(batch_no, total, "翻译中")

    progress(total, total, "写出中")
    mono_path, bilingual_path = writer.build_output_paths(input_path, source_lang, target_lang, bilingual)
    mono_texts = [t if t is not None else e.text for t, e in zip(translations, entries)]
    writer.write_srt_mono(entries, mono_texts, mono_path)
    log("info", f"已写出译文：{mono_path}")
    if bilingual_path:
        bilingual_texts = [t if t is not None else "（翻译失败，见日志）" for t in translations]
        writer.write_srt_bilingual(entries, bilingual_texts, bilingual_path)
        log("info", f"已写出双语对照：{bilingual_path}")

    progress(total, total, "完成" if failed == 0 else "完成（部分字幕翻译失败，详见日志）")
    return {
        "mono_path": mono_path,
        "bilingual_path": bilingual_path,
        "failed_chunks": failed,
        "total_chunks": len(entries),
    }
