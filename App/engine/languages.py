# 支持的语言列表：(界面显示名, 提示词中使用的英文名, 文件名中使用的短代码)
LANGUAGES = [
    ("简体中文", "Simplified Chinese", "zh-CN"),
    ("繁体中文", "Traditional Chinese", "zh-TW"),
    ("英语", "English", "en"),
    ("日语", "Japanese", "ja"),
    ("韩语", "Korean", "ko"),
    ("法语", "French", "fr"),
    ("德语", "German", "de"),
    ("西班牙语", "Spanish", "es"),
    ("俄语", "Russian", "ru"),
]

DEFAULT_SOURCE = "英语"
DEFAULT_TARGET = "简体中文"


def display_names():
    return [item[0] for item in LANGUAGES]


def to_prompt_name(display_name: str) -> str:
    for zh, en, _ in LANGUAGES:
        if zh == display_name:
            return en
    return display_name


def to_code(display_name: str) -> str:
    for zh, en, code in LANGUAGES:
        if zh == display_name:
            return code
    return "xx"
