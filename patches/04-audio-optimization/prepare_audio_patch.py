#!/usr/bin/env python3
"""Prepare a safe audio-optimization inventory for the Android game.

Read-only by default. This script only inventories audio assets and estimates
candidate size savings. It does not recompress, replace, delete, or alter files.
Voice/microphone/network voice assets are flagged to be excluded from bulk changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

AUDIO_EXTS = {".ogg", ".wav", ".mp3", ".aiff", ".aif", ".flac", ".mp4"}
VOICE_TERMS = ("voice", "mic", "microphone", "dissonance", "chat", "broadcast", "speech")
MUSIC_TERMS = ("music", "ambience", "ambient", "soundtrack")


def classify(path: Path) -> str:
    name = path.as_posix().lower()
    if any(term in name for term in VOICE_TERMS):
        return "voice_or_mic_sensitive"
    if any(term in name for term in MUSIC_TERMS):
        return "music_or_ambience_candidate"
    return "sfx_candidate_manual_review"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audio inventory for safe optimization")
    parser.add_argument("root", type=Path, help="Extracted game assets directory")
    parser.add_argument("--output", type=Path, default=Path("audio_optimization_inventory.json"))
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"directory not found: {args.root}")

    entries = []
    total = 0
    for path in args.root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTS:
            continue
        size = path.stat().st_size
        total += size
        entries.append({
            "path": str(path.relative_to(args.root)),
            "bytes": size,
            "category": classify(path),
            "bulk_compression_allowed": False,
        })
    entries.sort(key=lambda x: x["bytes"], reverse=True)
    report = {
        "purpose": "audio optimization preparation",
        "read_only": True,
        "modified_assets": 0,
        "compression_performed": False,
        "build_performed": False,
        "total_audio_files": len(entries),
        "total_bytes": total,
        "voice_and_mic_protection": (
            "Voice/mic/chat candidates are excluded from any future bulk conversion; "
            "runtime voice settings and capture/broadcast paths must remain unchanged."
        ),
        "recommendation": (
            "Only convert individually verified static music/SFX files after checking "
            "Unity importer settings, references, loop points, sample rate, channels, "
            "and quality. Keep originals and compare playback before accepting changes."
        ),
        "files": entries,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Read-only audio inventory written: {args.output}")
    print(f"Audio files: {len(entries)}; total size: {total} bytes")
    print("No audio files were modified and no APK was built.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
