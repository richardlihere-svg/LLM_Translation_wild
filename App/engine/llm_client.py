"""本地 LLM 调用模块：通过 Ollama 的 HTTP API 进行翻译请求。

只使用标准库（urllib），避免引入额外依赖。
"""

import json
import urllib.error
import urllib.request


class OllamaError(Exception):
    """与 Ollama 通信时发生的错误（连接失败、超时、模型不存在等）。"""


class OllamaClient:
    def __init__(self, host: str = "http://127.0.0.1:11434", timeout: int = 180):
        self.host = host.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            self.list_models()
            return True
        except OllamaError:
            return False

    def list_models(self):
        url = f"{self.host}/api/tags"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OllamaError(f"无法连接本地 Ollama 服务 ({self.host})：{e}") from e
        except (json.JSONDecodeError, TimeoutError) as e:
            raise OllamaError(f"解析 Ollama 返回结果失败：{e}") from e
        return [m["name"] for m in data.get("models", [])]

    def generate(self, model: str, prompt: str, system: str = "", options: dict | None = None) -> str:
        url = f"{self.host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
        }
        if options:
            payload["options"] = options

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST", headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise OllamaError(f"模型调用失败 (HTTP {e.code})：{detail}") from e
        except urllib.error.URLError as e:
            raise OllamaError(f"无法连接本地 Ollama 服务 ({self.host})：{e}") from e
        except TimeoutError as e:
            raise OllamaError(f"模型响应超时（超过 {self.timeout} 秒）") from e

        if "error" in data:
            raise OllamaError(str(data["error"]))
        return data.get("response", "")
