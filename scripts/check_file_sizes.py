from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

PY_SOURCE_LIMIT = 500
TEST_LIMIT = 600
FRONTEND_LIMIT = 500

FRONTEND_PATTERNS = ["*.svelte", "*.ts", "*.js", "*.css"]

EPILOG = f"""\
Limits: source files (src/, scripts/, infra/, .amp/, .agents/) max
{PY_SOURCE_LIMIT} lines, test files (tests/, frontend/e2e/) max {TEST_LIMIT},
frontend files (frontend/src/) max {FRONTEND_LIMIT}. Large files are a token tax on AI
agents: a 1,500-line file costs roughly 15K tokens per full read.

Files already over their limit when the gate was introduced are frozen in
scripts/file_size_allowlist.json at their then-current line counts. The
allowlist is a ratchet: a frozen file may shrink but never grow, and the
check fails when it exceeds its recorded count. --fix rewrites the
allowlist downward (lower counts to the current size, drop entries that
fell to or under their limit or whose file is gone); it never raises a
count. New files never get added to the allowlist: split them instead.
"""


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def collect(root: Path) -> dict[str, tuple[int, int]]:
    groups: list[tuple[Path, list[str], int]] = [
        (root / "src", ["*.py"], PY_SOURCE_LIMIT),
        (root / "scripts", ["*.py", "*.sh"], PY_SOURCE_LIMIT),
        (root / "infra", ["*.py", "*.sh"], PY_SOURCE_LIMIT),
        (root / ".amp", ["*.ts", "*.js"], PY_SOURCE_LIMIT),
        (root / ".agents", ["*.py", "*.sh", "*.ts"], PY_SOURCE_LIMIT),
        (root / "tests", ["*.py"], TEST_LIMIT),
        (root / "frontend" / "src", FRONTEND_PATTERNS, FRONTEND_LIMIT),
        (root / "frontend" / "e2e", FRONTEND_PATTERNS, TEST_LIMIT),
    ]
    found: dict[str, tuple[int, int]] = {}
    for base, patterns, limit in groups:
        if not base.is_dir():
            continue
        for pattern in patterns:
            for path in sorted(base.rglob(pattern)):
                rel = path.relative_to(root).as_posix()
                found[rel] = (line_count(path), limit)
    return found


def load_allowlist(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when a source file exceeds its line limit.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--allowlist", type=Path, default=None)
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    allowlist_path = args.allowlist or root / "scripts" / "file_size_allowlist.json"
    allowlist = load_allowlist(allowlist_path)
    files = collect(root)

    failures: list[str] = []
    updated = dict(allowlist)
    for rel, (lines, limit) in files.items():
        frozen = allowlist.get(rel)
        if frozen is not None:
            if lines > frozen:
                failures.append(
                    f"{rel}: {lines} lines, allowlisted at {frozen} "
                    f"(limit {limit}) - shrink or split it, never grow it"
                )
            elif lines <= limit:
                del updated[rel]
            elif lines < frozen:
                updated[rel] = lines
        elif lines > limit:
            failures.append(f"{rel}: {lines} lines exceeds the {limit}-line limit - split it")
    for rel in allowlist:
        if rel not in files:
            del updated[rel]

    if args.fix and not failures and updated != allowlist:
        allowlist_path.write_text(
            json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    for failure in failures:
        print(failure)
    if failures:
        print(
            f"{len(failures)} file(s) over their line limit. "
            "Split by pure moves behind a re-export so import paths survive."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
