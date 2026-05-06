"""Konfiguracja logging + filter maskujący JWT w wiadomościach."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]+){1,2}")


def mask_jwt(token: str | None) -> str | None:
    if token is None:
        return None
    if len(token) < 16:
        return "***"
    return f"{token[:8]}...{token[-8:]}"


class JwtMaskingFilter(logging.Filter):
    """Zamienia każdy JWT-looking ciąg w `record.msg`/argumentach na maskowany."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        masked = JWT_PATTERN.sub(lambda m: mask_jwt(m.group(0)) or "***", message)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def setup_logging(*, verbose: bool = False, log_file: Path | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    console.addFilter(JwtMaskingFilter())
    root.addHandler(console)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fileh = logging.FileHandler(log_file, encoding="utf-8")
        fileh.setLevel(logging.DEBUG)
        fileh.setFormatter(fmt)
        fileh.addFilter(JwtMaskingFilter())
        root.addHandler(fileh)
