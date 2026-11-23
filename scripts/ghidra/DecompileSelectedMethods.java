// DecompileSelectedMethods.java
// @category LethalOffline
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.listing.Function;
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
    private static final Pattern RVA_PATTERN =
        Pattern.compile("RVA:\\s*(0x[0-9A-Fa-f]+)");
    private static final Pattern METHOD_FILTER =
        Pattern.compile("(BuildGameplayControls|BuildCanvas|MakeActionButton|MakeButton|MakeImage|" +
            "BuildTerminalControls|MakeTerminalButton|UpdateTerminalButtons|UpdateActionButtons|" +
            "UpdateExtraButtons|IsLookingAtPlaceableShipObject|LayoutActionButtons|" +
            "BuildPersistentInputAnchors|Spectat|KillPlayer|SetPlayerDead|OnPlayerDeath|" +
            "Camera|LateUpdate|UpdateCamera|SwitchCamera|Fog|Atmosphere|LensDistortion|" +
            "Voice|Audio|Microphone|Dissonance|OnDisable|OnDestroy|Update|Awake|Start)",
            Pattern.CASE_INSENSITIVE);

    private static class Target {
        long rva;
        String type;
        String assembly;
        String signature;
        int sourceLine;
        Target(long r, String t, String a, String s, int l) {
            rva=r; type=t; assembly=a; signature=s; sourceLine=l;
        }
    }

    private boolean isWanted(String type, String signature) {
        if (type.startsWith("MobileTouch") || type.contains("MobileAtmosphere")) return true;
        if (type.equals("PlayerControllerB") || type.equals("HUDManager") ||
            type.equals("StartOfRound") || type.equals("DissonanceComms") ||
            type.contains("Spectat") || type.contains("Voice") || type.contains("Audio")) {
            return METHOD_FILTER.matcher(signature).find();
        }
        return false;
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

                Matcher rva = RVA_PATTERN.matcher(line);
                if (rva.find()) {
                    pendingRva = Long.parseLong(rva.group(1).substring(2), 16);
                    pendingLine = lineNumber;
                    continue;
                }
                if (pendingRva >= 0) {
                    String signature = line.trim();
                    if (pendingRva != 0 && isWanted(currentType, signature) && seen.add(pendingRva)) {
                        targets.add(new Target(pendingRva, currentType, currentAssembly, signature, pendingLine));
                    }
                    pendingRva = -1;
                }
            }
        } finally {
            reader.close();
        }

        // Prioritize the mobile controls and atmosphere runtime, then gameplay camera/death/audio.
        targets.sort((a,b) -> {
            int pa = a.type.startsWith("MobileTouch") ? 0 :
                (a.type.contains("MobileAtmosphere") ? 1 : 2);
            int pb = b.type.startsWith("MobileTouch") ? 0 :
                (b.type.contains("MobileAtmosphere") ? 1 : 2);
            if (pa != pb) return Integer.compare(pa,pb);
            if (!a.type.equals(b.type)) return a.type.compareTo(b.type);
            return Long.compare(a.rva,b.rva);
        });
        int limit = Math.min(40, targets.size());
        long imageBase = currentProgram.getImageBase().getOffset();
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
            Address address = space.getAddress(imageBase + target.rva);
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
            output.append(String.format("RVA=0x%X VA=0x%X (dump.cs line %d)%n", target.rva, imageBase + target.rva, target.sourceLine));
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
