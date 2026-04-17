import os
import re
import time
import threading
import sys
from datetime import date, timedelta
from typing import TextIO


def _get_time() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _get_date() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


class Logger:
    def __init__(self, name: str, pipe: TextIO = None, log_root: str = None, max_logging_date: int = 14, debug: bool = False):
        if log_root is None:
            # ~/.local/share/logs/{name}/
            log_root = os.path.expanduser("~/.local/share/logs")

        if pipe is None:
            pipe: TextIO = sys.stderr

        if not re.match(r'^[a-zA-Z0-9_\-]+$', name):
            raise ValueError(f"Invalid logger name: {name!r}")

        self.name = name
        self.log_dir = os.path.join(log_root, self.name)
        self.max_logging_date = max_logging_date
        self._lock = threading.Lock()
        self._last_cleanup_date: str | None = None
        self.file: TextIO = pipe

        if not debug:
            self.debug = lambda msg: None

        os.makedirs(self.log_dir, exist_ok=True)

    def _write(self, msg: str):
        with self._lock:
            today = _get_date()  # lock 안으로 이동
            log_path = os.path.join(self.log_dir, f"{today}.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
            if self._last_cleanup_date != today:
                self._cleanup()
                self._last_cleanup_date = today

    def _cleanup(self):
        log_dir = self.log_dir
        if not os.path.exists(log_dir):
            return
        for filename in os.listdir(log_dir):
            if not filename.endswith(".log"):
                continue
            filepath = os.path.join(log_dir, filename)
            try:
                date_str = filename[:-4]  # ".log" 제거
                cutoff = date.today() - timedelta(days=self.max_logging_date)
                file_date = date.fromisoformat(date_str)
                if file_date < cutoff:
                    os.remove(filepath)
            except Exception:
                pass

    def _log(self, level: str, msg: str):
        line = f"[{level}] {_get_time()} {msg}"
        print(line, file=self.file)
        self._write(line)

    def info(self, msg: str):    self._log("INFO", msg)
    def error(self, msg: str):   self._log("ERROR", msg)
    def debug(self, msg: str):   self._log("DEBUG", msg)
    def warning(self, msg: str): self._log("WARNING", msg)
