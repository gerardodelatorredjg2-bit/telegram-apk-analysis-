#!/usr/bin/env python3
"""Extract a focused, evidence-based index from an Il2CppDumper dump."""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

TARGETS = [
    r"MobileTouchControls",
    r"BuildGameplayControls",
    r"MakeActionButton",
    r"MakeButton",
    r"UpdateActionButtons",
    r"UpdateExtraButtons",
    r"BuildTerminalControls",
    r"IsLookingAtPlaceableShipObject",
    r"PlayerController",
    r"PlayerControllerB",
    r"Spectate",
    r"Spectator",
    r"Camera",
    r"Fog",
    r"LensDistortion",
    r"HUDManager",
    r"Terminal",
    r"PlayerVoice",
    r"Audio",
    r"NetworkManager",
    r"StartOfRound",
    r"PlaceableShipObject",
    r"GrabbableObject",
]
LINE_RE = re.compile("|".join(TARGETS), re.IGNORECASE)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dump", type=Path, required=True)
    ap.add_argument("--strings", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args=ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report={"dump_exists":args.dump.is_file(),"strings_exists":args.strings.is_file(),"target_lines":[],"method_summary":{},"metadata_literals":[]}
    if args.dump.is_file():
        lines=args.dump.read_text(errors="replace").splitlines()
        for i,line in enumerate(lines):
            if LINE_RE.search(line):
                start=max(0,i-3); end=min(len(lines),i+5)
                report["target_lines"].append({"line":i+1,"context":"\n".join(lines[start:end])})
        report["line_count"]=len(lines)
        report["target_match_count"]=len(report["target_lines"])
    if args.strings.is_file():
        try:
            raw=json.loads(args.strings.read_text(errors="replace"))
            text=json.dumps(raw,ensure_ascii=False)
            for term in ["BuildGameplayControls","MakeActionButton","MakeButton","BuildTerminalControls","IsLookingAtPlaceableShipObject","MobileTouchControls","Spectator","Spectate","LensDistortion","LocalVolumetricFog","GlassCondensation"]:
                if term.lower() in text.lower():
                    report["metadata_literals"].append(term)
            (args.out/"stringliteral-matches.txt").write_text("\n".join(report["metadata_literals"])+"\n")
        except Exception as exc:
            report["strings_parse_error"]=str(exc)
    (args.out/"focused-methods.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    with (args.out/"focused-methods.txt").open("w") as f:
        f.write("# Focused IL2CPP method/type matches\n\n")
        f.write(f"Dump exists: {report['dump_exists']}\n")
        f.write(f"Dump lines: {report.get('line_count',0)}\n")
        f.write(f"Target matches: {report.get('target_match_count',0)}\n")
        f.write(f"String literal hits: {', '.join(report['metadata_literals'])}\n\n")
        for item in report["target_lines"]:
            f.write(f"--- dump.cs line {item['line']} ---\n{item['context']}\n\n")
if __name__=="__main__":
    main()
