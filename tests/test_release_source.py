from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infra" / "scripts" / "resolve_release_source.py"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repository: Path, name: str) -> str:
    (repository / "release.txt").write_text(name, encoding="utf-8")
    _git(repository, "add", "release.txt")
    _git(repository, "commit", "-m", name)
    return _git(repository, "rev-parse", "HEAD")


def _repository(tmp_path: Path) -> tuple[Path, str, str, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Release Test")
    _git(repository, "config", "user.email", "release-test@example.invalid")
    previous = _commit(repository, "previous")
    current = _commit(repository, "current")
    _git(repository, "switch", "-c", "unreviewed", previous)
    unrelated = _commit(repository, "unreviewed")
    _git(repository, "switch", "main")
    return repository, previous, current, unrelated


def _run(repository: Path, current: str, requested: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--repository",
            str(repository),
            "--current",
            current,
            "--requested",
            requested,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_blank_source_resolves_to_current_main_commit(tmp_path: Path) -> None:
    repository, _, current, _ = _repository(tmp_path)

    result = _run(repository, current)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == current


def test_reviewed_main_ancestor_is_accepted_for_rollback(tmp_path: Path) -> None:
    repository, previous, current, _ = _repository(tmp_path)

    result = _run(repository, current, previous)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == previous


def test_short_or_unknown_source_is_rejected(tmp_path: Path) -> None:
    repository, previous, current, _ = _repository(tmp_path)

    short = _run(repository, current, previous[:12])
    unknown = _run(repository, current, "f" * 40)

    assert short.returncode == 2
    assert "full 40-character lowercase" in short.stderr
    assert unknown.returncode == 2
    assert "does not identify a commit" in unknown.stderr


def test_commit_outside_current_main_history_is_rejected(tmp_path: Path) -> None:
    repository, _, current, unrelated = _repository(tmp_path)

    result = _run(repository, current, unrelated)

    assert result.returncode == 2
    assert "reachable from the current main commit" in result.stderr
