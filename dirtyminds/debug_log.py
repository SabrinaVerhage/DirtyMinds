"""Bounded local diagnostics for the operator."""
from datetime import datetime
from logging import LogRecord, INFO
from logging.handlers import RotatingFileHandler


class DebugLog:
    def __init__(self, path):
        self.path = path
        self.handler = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=2, encoding="utf-8")
        except OSError:
            pass

    def write(self, message):
        if self.handler:
            line = f"{datetime.now().astimezone().isoformat(timespec='milliseconds')}  {message}"
            self.handler.handle(LogRecord("dirtyminds", INFO, "", 0, line, (), None))

    def close(self):
        if self.handler:
            self.handler.close()
