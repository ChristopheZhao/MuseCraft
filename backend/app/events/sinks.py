import json
import logging
import os

from .models import Event


class FileEpisodicSink:
    """
    简单的轨迹落盘：将事件写为 JSONL，便于后续分析。非阻塞，失败时记录 warning。
    """

    def __init__(self, path: str):
        self.path = path
        self.logger = logging.getLogger(self.__class__.__name__.lower())
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def __call__(self, event: Event) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:
            self.logger.warning("Failed to write episodic event: %s", exc)
