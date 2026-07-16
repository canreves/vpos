"""Summarize persisted parallel run evidence files."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from paynkolay_pos.reporting import evidence_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize sanitized parallel run evidence JSON files.",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(os.getenv("PAYNKOLAY_PARALLEL_EVIDENCE_DIR", "reports/parallel-runs")),
        help="Directory containing persisted parallel run evidence JSON files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of recent runs to include.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Print one run evidence document instead of the summary list.",
    )
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be greater than zero.")

    if args.run_id is not None:
        print(evidence_json(_read_run_detail(args.evidence_dir, args.run_id)))
        return

    print(evidence_json(_summary(args.evidence_dir, limit=args.limit)))


def _summary(evidence_dir: Path, *, limit: int) -> dict[str, object]:
    runs = []
    for path in sorted(evidence_dir.glob("*.json"), key=_path_mtime, reverse=True):
        payload = _read_evidence_file(path)
        if payload is None:
            continue
        run = payload.get("run")
        if not isinstance(run, dict):
            continue
        runs.append(_run_summary(run, path=path))
        if len(runs) >= limit:
            break

    return {
        "event": "parallel_evidence_summary",
        "evidence_dir": str(evidence_dir),
        "available": bool(runs),
        "run_count": len(runs),
        "runs": runs,
    }


def _read_run_detail(evidence_dir: Path, run_id: str) -> dict[str, object]:
    if not _valid_run_id(run_id):
        raise SystemExit("run id may only contain letters, numbers, dash, or underscore.")
    path = evidence_dir / f"{run_id}.json"
    payload = _read_evidence_file(path)
    if payload is None:
        raise SystemExit(f"parallel run evidence was not found: {run_id}")
    run = payload.get("run")
    if not isinstance(run, dict) or run.get("run_id") != run_id:
        raise SystemExit(f"parallel run evidence was not found: {run_id}")
    return {
        "event": "parallel_evidence_detail",
        "evidence_path": str(path),
        "evidence": payload,
    }


def _run_summary(run: dict[str, Any], *, path: Path) -> dict[str, object]:
    items = run.get("items")
    classifications: Counter[str] = Counter()
    if isinstance(items, list):
        classifications.update(
            str(item.get("classification") or "unknown")
            for item in items
            if isinstance(item, dict)
        )
    return {
        "run_id": str(run.get("run_id") or ""),
        "status": str(run.get("status") or ""),
        "total": _int_value(run.get("total")),
        "completed": _int_value(run.get("completed")),
        "failed": _int_value(run.get("failed")),
        "finished_at": run.get("finished_at"),
        "evidence_path": str(path),
        "classifications": dict(classifications),
    }


def _read_evidence_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _valid_run_id(run_id: str) -> bool:
    return bool(run_id) and all(
        character.isalnum() or character in {"-", "_"} for character in run_id
    )


if __name__ == "__main__":
    main()
