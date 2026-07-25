"""日志模块：每次翻译任务生成一个日志文件，写入 Data/logs/。"""

from datetime import datetime

import config


class TaskLogger:
    def __init__(self, task_name: str = "translate"):
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = config.LOGS_DIR / f"{task_name}_{timestamp}.log"
        self._fh = open(self.path, "a", encoding="utf-8")

    def write(self, level: str, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [{level.upper()}] {message}"
        self._fh.write(line + "\n")
        self._fh.flush()
        return line

    def close(self):
        self._fh.close()
