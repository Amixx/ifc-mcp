import io
import subprocess
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = "·∙⋅・"


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [name for name in out.split("\0") if name]


def _is_user_visible(rel: str) -> bool:
    if rel.startswith(("src/", "scripts/")):
        return rel.endswith((".py", ".sh", ".json"))
    return rel == "README.md" or (rel.startswith("docs/") and rel.endswith(".md"))


def _lines(rel: str) -> list[tuple[int, str]]:
    text = (ROOT / rel).read_text(encoding="utf-8")
    if not rel.endswith(".py"):
        return list(enumerate(text.splitlines(), 1))
    lines: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type != tokenize.COMMENT:
            lines.extend((tok.start[0] + i, s) for i, s in enumerate(tok.string.splitlines()))
    return lines


def test_user_visible_text_has_no_middle_dots():
    hits = [
        f"{rel}:{lineno}: {line.strip()}"
        for rel in _tracked_files()
        if _is_user_visible(rel)
        for lineno, line in _lines(rel)
        if any(ch in line for ch in FORBIDDEN)
    ]
    assert not hits, "middle dot in user-visible text:\n" + "\n".join(hits)
