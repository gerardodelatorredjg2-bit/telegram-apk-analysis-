// DecompileSelectedMethods.java
// @category LethalOffline
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import ghidra.util.task.TaskMonitor;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DecompileSelectedMethods extends GhidraScript {
    private static final Pattern TYPE_PATTERN =
        Pattern.compile("\\b(?:class|struct|enum|interface)\\s+([A-Za-z0-9_+<>]+)");
    private static final Pattern ADDRESS_PATTERN =
        Pattern.compile("RVA:\\s*(0x[0-9A-Fa-f]+).*?VA:\\s*(0x[0-9A-Fa-f]+)");
    private static final Pattern METHOD_FILTER =
        Pattern.compile("(CreateForAndroid|BuildGameplayControls|BuildCanvas|ApplyAspectCamera|RestoreAspectCamera|MakeActionButton|MakeButton|MakeImage|" +
            "BuildTerminalControls|MakeTerminalButton|UpdateTerminalButtons|UpdateActionButtons|" +
            "UpdateExtraButtons|IsLookingAtPlaceableShipObject|LayoutActionButtons|" +
            "BuildPersistentInputAnchors|DefaultVisible|CornerPosition|IsTerminalControl|CanHide|Find|GetOrAdd|IsVisible|Spectat|KillPlayer|SetPlayerDead|OnPlayerDeath|" +
            "Camera|LateUpdate|UpdateCamera|SwitchCamera|Fog|Atmosphere|LensDistortion|" +
            "Voice|Audio|Microphone|Dissonance|OnDisable|OnDestroy|Update|Awake|Start)",
            Pattern.CASE_INSENSITIVE);

    private static class Target {
        long rva;
        long va;
        String type;
        String assembly;
        String signature;
        int sourceLine;
        Target(long r, long v, String t, String a, String s, int l) {
            rva=r; va=v; type=t; assembly=a; signature=s; sourceLine=l;
        }
    }

    private boolean isWanted(String type, String signature) {
        if (type.equals("MobileControlsLayout") || type.equals("MobileControlsLayoutData") ||
            type.equals("MobileControlsLayoutEntry")) return METHOD_FILTER.matcher(signature).find();
        if (type.equals("MobileTouchControls") || type.equals("MobileGameViewFit")) return METHOD_FILTER.matcher(signature).find();
        if (type.equals("MobileTouchStick") || type.equals("MobileTouchAxis") ||
            type.equals("MobileTouchActionButton") || type.equals("MobileTouchContextButton") ||
            type.equals("MobileTouchLook")) {
            return METHOD_FILTER.matcher(signature).find();
        }
        if (type.equals("PlayerControllerB") || type.equals("HUDManager") ||
            type.equals("StartOfRound") || type.equals("DissonanceComms") ||
            type.equals("OfflineFullGameBootstrap") || type.contains("Spectat") || type.contains("Voice") || type.contains("Audio")) {
            return METHOD_FILTER.matcher(signature).find();
        }
        return false;
    }

    private int priority(String type) {
        if (type.equals("MobileControlsLayout") || type.equals("MobileControlsLayoutData")) return 0;
        if (type.equals("MobileTouchControls") || type.equals("MobileGameViewFit")) return 1;
        if (type.equals("MobileTouchStick")) return 2;
        if (type.equals("MobileTouchActionButton")) return 3;
        if (type.equals("MobileTouchContextButton")) return 4;
        if (type.equals("MobileTouchAxis")) return 5;
        if (type.equals("PlayerControllerB")) return 6;
        if (type.equals("HUDManager")) return 7;
        if (type.equals("DissonanceComms")) return 8;
        return 8;
    }

    private String safe(String value) {
        return value.replaceAll("[^A-Za-z0-9_]+", "_");
    }

    private void write(String path, String text) throws Exception {
        File out = new File(path);
        File parent = out.getParentFile();
        if (parent != null) parent.mkdirs();
        BufferedWriter writer = new BufferedWriter(new FileWriter(out));
        try { writer.write(text); } finally { writer.close(); }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            printerr("Usage: DecompileSelectedMethods.java <dump.cs> <output-dir>");
            return;
        }
        File dumpFile = new File(args[0]);
        File outDir = new File(args[1]);
        if (!dumpFile.isFile()) throw new IllegalArgumentException("dump.cs not found: " + dumpFile);
        outDir.mkdirs();

        List<Target> targets = new ArrayList<>();
        Set<Long> seen = new HashSet<>();
        String currentType = "";
        String currentAssembly = "";
        long pendingRva = -1;
        long pendingVa = -1;
        int pendingLine = 0;
        BufferedReader reader = new BufferedReader(new FileReader(dumpFile));
        try {
            String line;
            int lineNumber = 0;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                if (line.contains("// TypeDefIndex:")) {
                    currentAssembly = "";
                    Matcher assembly = Pattern.compile("Assembly:\\s*([^|]+)").matcher(line);
                    if (assembly.find()) currentAssembly = assembly.group(1).trim();
                }
                Matcher type = TYPE_PATTERN.matcher(line);
                if (type.find()) currentType = type.group(1).trim();

                Matcher addressMatch = ADDRESS_PATTERN.matcher(line);
                if (addressMatch.find()) {
                    pendingRva = Long.parseLong(addressMatch.group(1).substring(2), 16);
                    pendingVa = Long.parseLong(addressMatch.group(2).substring(2), 16);
                    pendingLine = lineNumber;
                    continue;
                }
                if (pendingRva >= 0) {
                    String signature = line.trim();
                    if (pendingRva != 0 && pendingVa != 0 && isWanted(currentType, signature) && seen.add(pendingRva)) {
                        targets.add(new Target(pendingRva, pendingVa, currentType, currentAssembly, signature, pendingLine));
                    }
                    pendingRva = -1;
                    pendingVa = -1;
                }
            }
        } finally {
            reader.close();
        }

        long imageBase = currentProgram.getImageBase().getOffset();
        // Add names for nearby IL2CPP methods so native calls in the pseudocode
        // resolve to managed method names instead of anonymous func_0x... symbols.
        // Only create labels (not functions) here to keep the focused decompilation fast.
        List<Target> allMethods = new ArrayList<>();
        String mapType = "";
        String mapAssembly = "";
        long mapRva = -1;
        long mapVa = -1;
        int mapLine = 0;
        BufferedReader mapReader = new BufferedReader(new FileReader(dumpFile));
        try {
            String line;
            int lineNumber = 0;
            while ((line = mapReader.readLine()) != null) {
                lineNumber++;
                if (line.contains("// TypeDefIndex:")) {
                    mapAssembly = "";
                    Matcher assembly = Pattern.compile("Assembly:\\s*([^|]+)").matcher(line);
                    if (assembly.find()) mapAssembly = assembly.group(1).trim();
                }
                Matcher type = TYPE_PATTERN.matcher(line);
                if (type.find()) mapType = type.group(1).trim();
                Matcher addressMatch = ADDRESS_PATTERN.matcher(line);
                if (addressMatch.find()) {
                    mapRva = Long.parseLong(addressMatch.group(1).substring(2), 16);
                    mapVa = Long.parseLong(addressMatch.group(2).substring(2), 16);
                    mapLine = lineNumber;
                    continue;
                }
                if (mapRva >= 0) {
                    String signature = line.trim();
                    boolean relevantAssembly =
                        mapAssembly.equals("LethalOffline.MobileControls.Runtime.dll") ||
                        mapAssembly.equals("LethalRecovered.Gameplay.dll") ||
                        mapAssembly.equals("UnityEngine.CoreModule.dll") ||
                        mapAssembly.equals("UnityEngine.UI.dll") ||
                        mapAssembly.equals("Unity.InputSystem.dll") ||
                        mapAssembly.equals("Unity.InputSystem.UI.dll") ||
                        mapAssembly.equals("Unity.InputSystem.OnScreen.dll");
                    if (mapRva != 0 && mapVa != 0 && relevantAssembly) {
                        allMethods.add(new Target(mapRva, mapVa, mapType, mapAssembly, signature, mapLine));
                    }
                    mapRva = -1;
                    mapVa = -1;
                }
            }
        } finally {
            mapReader.close();
        }

        AddressSpace labelSpace = currentProgram.getAddressFactory().getDefaultAddressSpace();
        Set<Long> labelled = new HashSet<>();
        int labelsCreated = 0;
        for (Target method : allMethods) {
            if (!labelled.add(method.va)) continue;
            Address methodAddress = labelSpace.getAddress(imageBase + method.va);
            try {
                String label = safe(method.type + "_" + method.signature);
                if (label.length() > 100) label = label.substring(0, 100);
                currentProgram.getSymbolTable().createLabel(
                    methodAddress, label, SourceType.USER_DEFINED
                );
                labelsCreated++;
            } catch (Exception ignored) {
                // A shared generic RVA or existing loader symbol may already own the address.
            }
        }

        // Prioritize the mobile controls and atmosphere runtime, then gameplay camera/death/audio.
        targets.sort((a,b) -> {
            int pa = priority(a.type);
            int pb = priority(b.type);
            if (pa != pb) return Integer.compare(pa,pb);
            if (!a.type.equals(b.type)) return a.type.compareTo(b.type);
            return Long.compare(a.rva,b.rva);
        });
        int limit = Math.min(100, targets.size());
        AddressSpace space = currentProgram.getAddressFactory().getDefaultAddressSpace();

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        StringBuilder output = new StringBuilder();
        StringBuilder index = new StringBuilder();
        output.append("Program: ").append(currentProgram.getName()).append("\n");
        output.append(String.format("Image base: 0x%X%n", imageBase));
        output.append("Candidates: ").append(targets.size()).append("; Selected: ").append(limit).append("\n");
        output.append("Only selected functions are decompiled; dump.cs contains the metadata signatures.\n");

        int successes=0, failures=0;
        for (int i=0; i<limit; i++) {
            monitor.checkCancelled();
            Target target = targets.get(i);
            // Use the explicit ELF virtual address from dump.cs (VA), not RVA.
            // This APK's ARM64 libil2cpp.so has VA-RVA == 0x40000 for this module.
            Address address = space.getAddress(imageBase + target.va);
            Function function = currentProgram.getFunctionManager().getFunctionAt(address);
            if (function == null) {
                try {
                    // With -noanalysis, explicitly disassemble just this IL2CPP method,
                    // then create the function so the decompiler can recover its CFG.
                    disassemble(address);
                    function = createFunction(address, safe(target.type + "_" + target.signature) + "_0x" + Long.toHexString(target.rva));
                } catch (Exception ignored) {
                    function = currentProgram.getFunctionManager().getFunctionAt(address);
                }
            }
            output.append("\n").append("=".repeat(90)).append("\n");
            output.append("[").append(i+1).append("/").append(limit).append("] ")
                .append(target.type).append(" | ").append(target.assembly).append("\n");
            output.append(String.format("RVA=0x%X ELF_VA=0x%X Ghidra=0x%X (dump.cs line %d)%n", target.rva, target.va, imageBase + target.va, target.sourceLine));
            output.append(target.signature).append("\n");
            index.append(String.format("0x%X\t%s\t%s\t%s%n", target.rva, target.type, target.assembly, target.signature));

            if (function == null) {
                output.append("[NO FUNCTION AT ADDRESS]\n");
                failures++;
                continue;
            }
            try {
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result != null && result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.append(result.getDecompiledFunction().getC()).append("\n");
                    successes++;
                } else {
                    output.append("[DECOMPILATION FAILED] ")
                        .append(result == null ? "no result" : result.getErrorMessage()).append("\n");
                    failures++;
                }
            } catch (Exception exception) {
                output.append("[EXCEPTION] ").append(exception.toString()).append("\n");
                failures++;
            }
        }
        decompiler.dispose();
        output.append("\nSUMMARY: ").append(successes).append(" decompiled, ").append(failures).append(" failed.\n");
        write(new File(outDir, "selected-methods.c.txt").getAbsolutePath(), output.toString());
        write(new File(outDir, "selected-methods.tsv").getAbsolutePath(), index.toString());
        println("Decompiled " + successes + " methods; failed " + failures + "; selected " + limit);
    }
}
