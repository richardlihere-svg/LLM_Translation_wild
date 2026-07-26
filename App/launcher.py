"""启动器：检查依赖、按需启动 Ollama，然后打开 GUI。"""

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
OLLAMA_URL = "http://127.0.0.1:11434"


def ensure_requirements():
    try:
        import docx  # noqa: F401
        import pypdf  # noqa: F401
        import tkinterdnd2  # noqa: F401

        return
    except ImportError:
        pass
    print("[初始化] 正在安装/更新依赖库（python-docx, pypdf, tkinterdnd2）...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(APP_DIR / "requirements.txt")]
    )
    if result.returncode != 0:
        print("[错误] 依赖安装失败，请检查网络连接后重新运行本脚本。")
        input("按回车键退出...")
        sys.exit(1)


def ensure_ollama():
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        print("[提示] 未检测到 Ollama，翻译功能需要本地 Ollama 提供模型支持。")
        print("       请前往 https://ollama.com/download 下载安装，安装后重新运行本脚本。")
        return

    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=1)
        return  # 已在运行
    except Exception:
        pass

    print("[提示] 正在后台启动 Ollama 服务...")
    subprocess.Popen(
        [ollama_path, "serve"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    ensure_requirements()
    ensure_ollama()

    sys.path.insert(0, str(APP_DIR / "engine"))
    import gui

    sys.argv = [sys.argv[0]] + sys.argv[1:]
    gui.main()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        input("按回车键退出...")
        sys.exit(1)
