/* Query - ask the analysed EBOOT a question and get the answer on stdout.
 *
 * The project is built once, by [`PlantOpd.java`](PlantOpd.java) and the
 * analysis behind it. After that every question this repository asks of the
 * binary is one of four, and none of them wants a window:
 *
 *     analyzeHeadless <project dir> <name> -process <file> -noanalysis \
 *         -scriptPath tools/ghidra -postScript Query.java <verb> <argument>
 *
 *     decomp  <function>   the decompiler's C for it
 *     xrefs   <address>    who reaches this address, and from which function
 *     callers <function>   who calls it
 *     info    <address>    which function contains it
 *
 * A `<function>` is a name - `cfGetDamage`, or one of the 274 the disc's own
 * script vocabulary planted - or an address as `0x009d4870`. An `<address>`
 * is always the latter. `-noanalysis` is what makes this cheap: the analysis
 * is in the project already.
 */

import java.util.ArrayList;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Query extends GhidraScript {

	private Function resolve(String what) {
		if (what.startsWith("0x") || what.startsWith("0X")) {
			Address a = toAddr(Long.parseLong(what.substring(2), 16));
			Function fn = getFunctionAt(a);
			return fn != null ? fn : getFunctionContaining(a);
		}
		List<Function> hits = getGlobalFunctions(what);
		return hits.isEmpty() ? null : hits.get(0);
	}

	private String where(Address a) {
		Function fn = getFunctionContaining(a);
		return fn == null ? "-" : fn.getName() + "+" +
				(a.getOffset() - fn.getEntryPoint().getOffset());
	}

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length < 2) {
			println("Query: verb and argument, please");
			return;
		}
		String verb = args[0], what = args[1];

		if (verb.equals("decomp")) {
			Function fn = resolve(what);
			if (fn == null) {
				println("Query: no function called " + what);
				return;
			}
			DecompInterface dec = new DecompInterface();
			dec.openProgram(currentProgram);
			DecompileResults res = dec.decompileFunction(fn, 180, monitor);
			if (!res.decompileCompleted()) {
				println("Query: the decompiler refused " + fn.getName() + ": "
						+ res.getErrorMessage());
				return;
			}
			println("/* " + fn.getName() + " at " + fn.getEntryPoint() + ", "
					+ fn.getBody().getNumAddresses() + " bytes */");
			println(res.getDecompiledFunction().getC());
			dec.dispose();
			return;
		}

		if (verb.equals("xrefs")) {
			Address a = toAddr(Long.parseLong(what.replaceFirst("^0[xX]", ""), 16));
			ReferenceIterator it = currentProgram.getReferenceManager()
					.getReferencesTo(a);
			int n = 0;
			while (it.hasNext()) {
				Reference r = it.next();
				println(r.getFromAddress() + "  " + r.getReferenceType()
						+ "  in " + where(r.getFromAddress()));
				n++;
			}
			println("Query: " + n + " references to " + a);
			return;
		}

		if (verb.equals("callers")) {
			Function fn = resolve(what);
			if (fn == null) {
				println("Query: no function called " + what);
				return;
			}
			List<String> seen = new ArrayList<>();
			ReferenceIterator it = currentProgram.getReferenceManager()
					.getReferencesTo(fn.getEntryPoint());
			while (it.hasNext()) {
				Reference r = it.next();
				String w = where(r.getFromAddress());
				if (!seen.contains(w)) {
					seen.add(w);
					println(r.getFromAddress() + "  " + w);
				}
			}
			println("Query: " + seen.size() + " callers of " + fn.getName()
					+ " at " + fn.getEntryPoint());
			return;
		}

		if (verb.equals("info")) {
			Address a = toAddr(Long.parseLong(what.replaceFirst("^0[xX]", ""), 16));
			Function fn = getFunctionContaining(a);
			println(a + "  " + (fn == null ? "in no function"
					: fn.getName() + " at " + fn.getEntryPoint() + ", "
							+ fn.getBody().getNumAddresses() + " bytes"));
			return;
		}

		println("Query: I do not know the verb " + verb);
	}
}
