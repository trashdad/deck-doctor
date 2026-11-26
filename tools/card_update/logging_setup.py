"""Per-run logger: stdout (-> journal) + a per-run file, ISO-8601 UTC timestamps,
run id on every line, stage name as a prefix. No module-level handlers are installed.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, MutableMapping


class UtcFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"


def make_run_logger(run_id: str, log_file: Path | None, stream: IO[str] | None = None,
                    level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(f"card_update.run.{run_id}")
    logger.setLevel(level)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    fmt = UtcFormatter(f"%(asctime)s %(levelname)-7s run={run_id} | %(message)s")
    sh = logging.StreamHandler(stream or sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if log_file is not None:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def close_logger(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


class StageLogger(logging.LoggerAdapter):
    """Prefixes every message with ``[stage]``."""

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        return f"[{self.extra['stage']}] {msg}", kwargs


def stage_logger(logger: logging.Logger | logging.LoggerAdapter, stage: str) -> StageLogger:
    base = logger.logger if isinstance(logger, logging.LoggerAdapter) else logger
    return StageLogger(base, {"stage": stage})
