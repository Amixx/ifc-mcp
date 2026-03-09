"""CLI-friendly progress reporting helpers."""

from __future__ import annotations

from pathlib import Path
import sys
import time
from typing import Any, TextIO

import click


class CliProgressReporter:
    """Emit parser/pipeline progress events to stderr."""

    def __init__(self, enabled: bool = True, verbose: bool = False, stream: TextIO | None = None) -> None:
        self.enabled = bool(enabled or verbose)
        self.verbose = verbose
        self.stream = stream or sys.stderr
        self._started_at = time.monotonic()

    def begin(self, file_path: str, label: str | None = None) -> None:
        """Emit initial file context."""
        if not self.enabled:
            return

        file_size = _format_size(Path(file_path).stat().st_size)
        prefix = f"{label}: " if label else ""
        line = f"[ifc-mcp] {prefix}loading {file_path} ({file_size})"
        if self.verbose:
            line = f"{line} | rss={_rss_mb_str()}"
        click.echo(line, err=True, file=self.stream)

    def event(self, event: dict[str, Any]) -> None:
        """Handle one pipeline/parser progress event."""
        if not self.enabled:
            return

        stage = str(event.get("stage", "unknown"))
        scope = event.get("scope")
        stage_label = f"{scope}.{stage}" if scope else stage
        message = str(event.get("message", stage))
        processed = event.get("processed")
        total = event.get("total")
        elapsed = _fmt_seconds(_as_float(event.get("elapsed_seconds")))
        eta = _fmt_seconds(_as_float(event.get("eta_seconds")))
        file_path = event.get("file_path")
        file_size = event.get("file_size_bytes")

        details: list[str] = []
        if processed is not None and total:
            pct = (float(processed) / float(total)) * 100.0 if float(total) > 0 else 0.0
            details.append(f"{int(processed)}/{int(total)} ({pct:.0f}%)")
        if self.verbose:
            if elapsed:
                details.append(f"elapsed={elapsed}")
            if eta:
                details.append(f"eta={eta}")
            rss = _rss_mb_str()
            if rss:
                details.append(f"rss={rss}")
            if file_path:
                details.append(f"file={file_path}")
            if file_size is not None:
                try:
                    details.append(f"size={_format_size(int(file_size))}")
                except (TypeError, ValueError):
                    pass

        suffix = f" | {' | '.join(details)}" if details else ""
        click.echo(f"[ifc-mcp] {stage_label}: {message}{suffix}", err=True, file=self.stream)

    def done(self, label: str | None = None) -> None:
        """Emit final completion line."""
        if not self.enabled:
            return
        elapsed = _fmt_seconds(time.monotonic() - self._started_at) or "0s"
        prefix = f"{label}: " if label else ""
        click.echo(f"[ifc-mcp] {prefix}complete | elapsed={elapsed}", err=True, file=self.stream)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_seconds(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = seconds - (minutes * 60)
    return f"{minutes}m{remainder:04.1f}s"


def _format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def _rss_mb_str() -> str | None:
    try:
        import resource  # pylint: disable=import-outside-toplevel

        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = float(usage.ru_maxrss)
        if sys.platform == "darwin":
            rss_mb = rss / (1024 * 1024)
        else:
            rss_mb = rss / 1024
        return f"{rss_mb:.1f}MB"
    except Exception:  # pragma: no cover - platform dependent
        return None
