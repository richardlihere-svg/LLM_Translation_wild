import json
from pathlib import Path

# 目录结构：
#   <root>/App/engine/config.py  (本文件)
#   <root>/Data/...
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "Data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
LOGS_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_DIR = DATA_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "ollama_host": "http://127.0.0.1:11434",
    "last_model": "",
    "last_source_lang": "英语",
    "last_target_lang": "简体中文",
    "last_style": "通顺",
    "bilingual_output": True,
    "chunk_max_chars": 1500,
    "request_timeout": 180,
}


def ensure_dirs():
    for d in (INPUT_DIR, OUTPUT_DIR, LOGS_DIR, CACHE_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(settings: dict):
    ensure_dirs()
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
