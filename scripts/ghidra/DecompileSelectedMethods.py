#@category LethalOffline
#@runtime Jython
"""Decompile selected IL2CPP native methods using the RVA map in dump.cs."""
import os
import re
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

def read_text(path):
    f = open(path, "r")
    try:
        return f.read().splitlines()
    finally:
        f.close()

def write_text(path, text):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    f = open(path, "w")
    try:
        f.write(text)
    finally:
        f.close()

def main():
    args = getScriptArgs()
    if len(args) < 2:
        printerr("Usage: DecompileSelectedMethods.py <dump.cs> <output-dir>")
        return
    dump_path = args[0]
    out_dir = args[1]
    if not os.path.isfile(dump_path):
        printerr("dump.cs not found: " + dump_path)
        return
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    lines = read_text(dump_path)
    type_name = ""
    assembly_name = ""
    pending_rva = None
    pending_line = 0
    targets = []
    wanted_methods = re.compile(
        r"(BuildGameplayControls|BuildCanvas|MakeActionButton|MakeButton|MakeImage|"
        r"BuildTerminalControls|MakeTerminalButton|UpdateTerminalButtons|"
        r"UpdateActionButtons|UpdateExtraButtons|IsLookingAtPlaceableShipObject|"
        r"LayoutActionButtons|BuildPersistentInputAnchors|"
        r"Spectat|KillPlayer|SetPlayerDead|OnPlayerDeath|"
        r"Camera|LateUpdate|UpdateCamera|SwitchCamera|"
        r"Fog|Atmosphere|LensDistortion|"
        r"Voice|Audio|Microphone|Dissonance|"
        r"OnDisable|OnDestroy|Update|Awake|Start)",
        re.IGNORECASE
    )
    target_types = set([
        "MobileTouchControls", "MobileTouchStick", "MobileTouchLook",
        "MobileTouchActionButton", "MobileTouchContextButton",
        "MobileTouchInventory", "MobileTouchInventorySlot",
        "MobileTouchMousePosition", "MobileAtmosphere",
        "MobileAtmosphereController", "MobileAtmosphereRuntime",
        "PlayerControllerB", "HUDManager", "StartOfRound",
        "SpectateCamera", "DissonanceComms"
    ])

    type_re = re.compile(r"\b(?:class|struct|enum|interface)\s+([A-Za-z0-9_+<>]+)")
    rva_re = re.compile(r"RVA:\s*(0x[0-9A-Fa-f]+)")
    for idx, line in enumerate(lines):
        if "Assembly:" in line and "// TypeDefIndex:" in line:
            m = re.search(r"Assembly:\s*([^|]+)", line)
            if m:
                assembly_name = m.group(1).strip()
        if "// TypeDefIndex:" in line:
            assembly_name = ""
        tm = type_re.search(line)
        if tm:
            type_name = tm.group(1).strip()
        rm = rva_re.search(line)
        if rm:
            pending_rva = int(rm.group(1), 16)
            pending_line = idx + 1
            continue
        if pending_rva is not None:
            signature = line.strip()
            is_mobile_type = type_name.startswith("MobileTouch") or "MobileAtmosphere" in type_name
            is_key_type = type_name in target_types
            is_key_method = bool(wanted_methods.search(signature))
            if pending_rva != 0 and (is_mobile_type or (is_key_type and is_key_method)):
                targets.append({
                    "rva": pending_rva,
                    "type": type_name,
                    "assembly": assembly_name,
                    "signature": signature,
                    "source_line": pending_line
                })
            pending_rva = None

    # De-duplicate by native RVA and prioritize controls before general camera/audio methods.
    by_rva = {}
    for item in targets:
        if item["rva"] not in by_rva:
            by_rva[item["rva"]] = item
    targets = list(by_rva.values())
    targets.sort(key=lambda x: (
        0 if x["type"].startswith("MobileTouch") else
        1 if "MobileAtmosphere" in x["type"] else 2,
        x["type"], x["rva"]
    ))
    # A focused first pass keeps the headless job bounded but includes the full mobile-control types.
    limit = 180
    selected = targets[:limit]

    base = currentProgram.getImageBase().getOffset()
    address_space = currentProgram.getAddressFactory().getDefaultAddressSpace()
    decomp = DecompInterface()
    decomp.openProgram(currentProgram)
    monitor = ConsoleTaskMonitor()
    out = []
    out.append("IL2CPP target decompilation")
    out.append("Program: " + currentProgram.getName())
    out.append("Image base: 0x%X" % base)
    out.append("Targets found: %d; selected: %d" % (len(targets), len(selected)))
    out.append("")

    successes = 0
    failures = 0
    for n, item in enumerate(selected):
        addr = address_space.getAddress(base + item["rva"])
        fn = currentProgram.getFunctionManager().getFunctionAt(addr)
        if fn is None:
            try:
                fn = createFunction(addr, item["type"] + "_" + str(item["rva"]))
            except Exception:
                fn = currentProgram.getFunctionManager().getFunctionAt(addr)
        out.append("=" * 100)
        out.append("[%d/%d] %s" % (n + 1, len(selected), item["type"]))
        out.append("RVA=0x%X VA=0x%X assembly=%s" % (item["rva"], base + item["rva"], item["assembly"]))
        out.append(item["signature"])
        out.append("dump.cs line %d" % item["source_line"])
        if fn is None:
            out.append("[NO FUNCTION AT ADDRESS]")
            failures += 1
            continue
        try:
            result = decomp.decompileFunction(fn, 90, monitor)
            if result is None or not result.decompileCompleted() or result.getDecompiledFunction() is None:
                out.append("[DECOMPILATION FAILED] " + (result.getErrorMessage() if result else "no result"))
                failures += 1
            else:
                out.append(result.getDecompiledFunction().getC())
                successes += 1
        except Exception as exc:
            out.append("[EXCEPTION] " + str(exc))
            failures += 1
        out.append("")

    out.append("SUMMARY: %d decompiled, %d failed" % (successes, failures))
    write_text(os.path.join(out_dir, "selected-methods.c.txt"), "\n".join(out))
    index = []
    for item in selected:
        index.append("0x%X\t%s\t%s\t%s" % (
            item["rva"], item["type"], item["assembly"], item["signature"]
        ))
    write_text(os.path.join(out_dir, "selected-methods.tsv"), "\n".join(index) + "\n")
    decomp.dispose()
    print("Decompiled %d methods; failed %d; selected %d" % (successes, failures, len(selected)))

main()
