#!/usr/bin/env python3
"""Prepare a read-only bug triage report for extracted game assets.

Preparatory diagnostic only. Inventories file sizes, zero-byte files and duplicate
hashes. It never edits/deletes assets and does not build the APK.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only asset bug triage")
    parser.add_argument("root", type=Path, help="Extracted game asset directory")
    parser.add_argument("--output", type=Path, default=Path("bug_triage_report.json"))
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"directory not found: {args.root}")
    records, zero_files, duplicate_map, ext_counts = [], [], {}, {}
    total_bytes = 0
    for path in args.root.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            ext = path.suffix.lower() or "<no extension>"
            total_bytes += size
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            rel = str(path.relative_to(args.root))
            record = {"path": rel, "bytes": size, "extension": ext}
            records.append(record)
            if size == 0:
                zero_files.append(record)
            if size:
                duplicate_map.setdefault(digest(path), []).append(rel)
        except OSError as exc:
            records.append({"path": str(path.relative_to(args.root)), "error": str(exc)})
    duplicates = [group for group in duplicate_map.values() if len(group) > 1]
    report = {
        "purpose": "generic bug triage preparation", "read_only": True,
        "assets_modified": 0, "files_deleted": 0, "build_performed": False,
        "total_files": len(records), "total_bytes": total_bytes,
        "zero_byte_files": zero_files, "duplicate_groups_identified_not_removed": duplicates,
        "extension_counts": ext_counts,
        "review_notes": [
            "Zero-byte and duplicate files are diagnostic candidates, not automatically bugs.",
            "Do not delete duplicate candidates: Unity may reference distinct asset IDs.",
            "Review game logs, crash traces, and reproduction steps before making fixes.",
            "Keep originals and validate proposed changes in a separate copy."
        ],
        "files": records
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Read-only triage report written: {args.output}")
    print(f"Files scanned: {len(records)}; zero-byte files: {len(zero_files)}; duplicate groups: {len(duplicates)}")
    print("No assets were changed, removed, or rebuilt.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
