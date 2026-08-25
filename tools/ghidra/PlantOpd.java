/* PlantOpd - give a disassembler the function table this binary does not ship.
 *
 * The EBOOT is stripped, so Ghidra's own analysis of it finds nothing: sixteen
 * seconds, no functions, no code. Everything it needs is in the `.opd`, and
 * [`ppc.py`](../ppc.py) reads that out - one line per function, an address and
 * a name where the disc can name it:
 *
 *     python tools/ppc.py plant eboot.elf api.tsv plant.tsv
 *
 * Then, with this file on the script path:
 *
 *     analyzeHeadless <project dir> <name> -import eboot.elf \
 *         -scriptPath tools/ghidra -preScript PlantOpd.java plant.tsv
 *
 * `-preScript` runs after the import and before the analysis, which is the
 * right moment: the analysers are far better at a binary that already knows
 * where its functions begin than at one they have to guess from.
 */

import java.io.BufferedReader;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class PlantOpd extends GhidraScript {

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length < 1) {
			println("PlantOpd: give me the .tsv that `ppc.py plant` wrote");
			return;
		}

		List<Address> at = new ArrayList<>();
		List<String> name = new ArrayList<>();
		try (BufferedReader in = new BufferedReader(new FileReader(args[0]))) {
			String line;
			while ((line = in.readLine()) != null) {
				String[] f = line.split("\t", -1);
				if (f[0].isEmpty()) {
					continue;
				}
				at.add(toAddr(Long.parseLong(f[0].trim(), 16)));
				name.add(f.length > 1 ? f[1].trim() : "");
			}
		}
		println("PlantOpd: " + at.size() + " function entries to plant");

		AddressSet set = new AddressSet();
		for (Address a : at) {
			set.add(a);
		}
		DisassembleCommand cmd = new DisassembleCommand(set, null, true);
		cmd.applyTo(currentProgram, monitor);
		println("PlantOpd: disassembled from every one of them");

		int made = 0, named = 0, missed = 0;
		monitor.initialize(at.size());
		for (int i = 0; i < at.size(); i++) {
			if (monitor.isCancelled()) {
				break;
			}
			monitor.incrementProgress(1);
			Address a = at.get(i);
			Function fn = getFunctionAt(a);
			if (fn == null) {
				fn = createFunction(a, null);
			}
			if (fn == null) {
				missed++;
				continue;
			}
			made++;
			if (!name.get(i).isEmpty()) {
				fn.setName(name.get(i), SourceType.USER_DEFINED);
				named++;
			}
		}
		println("PlantOpd: " + made + " functions, " + named + " named, "
				+ missed + " refused");
	}
}
