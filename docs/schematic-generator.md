# Schematic generator guide

Skill: [`skills/kicad-schematic-generator/SKILL.md`](../skills/kicad-schematic-generator/SKILL.md)

## Project layout the skill creates

```
<project>/
  gen/kigen.py        generator library
  gen/netcheck.py     generic netlist checker
  gen/symbols.py      custom symbols (make_ic) + pin data files (json) with their sources
  gen/build.py        the design: one section per sheet
  gen/verify.py       design-specific assertions on the netlist
  gen/gen_fp.py       custom footprints (e.g. BGA) if the library lacks them
  kicad/              generated KiCad project, custom symbol library, library tables
  <name>_schematic.pdf, <name>_bom.csv, <name>.net, README.md
```

## Workflow

1. Clarify requirements only if expensive to redo (interfaces, counts, voltages, output form, KiCad version).
2. Collect pin data and reference schematics; save pin tables as JSON next to the code.
3. Write `symbols.py`, then `build.py` sheet by sheet (power input, rails, SoC units, memory, storage, radios, connectors, IO). Put design equations and assumptions on the sheet as `fl.section` notes.
4. Build and verify (ERC, netlist export, `netcheck.py`, `verify.py`, PDF, BOM).
5. In `verify.py` assert what ERC cannot see: SoC pin to net mapping against the reference design, connector pinouts, memory byte lanes and address fan-out, power balls on the right rail, and regulator output voltages computed from the actual divider values (`Vref * (1 + Rtop / Rbot)`) and current-limit resistor values.
6. Render each PDF page (`pdftoppm -r 55`) and look at it; zoom into crops at 150-200 dpi to check overlaps and readability.
7. Deliver the zipped project and PDF with a README that states what was verified, with which KiCad version, plus an honest "before fabrication" list.

## `kigen` cheat sheet

```python
from kigen import *
P = Project('myboard')
P.refcount['U'] = 1                    # reserve U1 for a multi-unit IC with a fixed reference
R_ = load_lib('Device', 'R')
sh = P.add_sheet(Sheet('Power', 'power.kicad_sch', '12V -> 5V'))
fl = Flow(sh, 20, 25, 385)             # sheet, x0, y0, width
fl.section('5V BUCK', 'Vout = 0.8 x (1 + 52.3k/10k) = 4.98 V')
fl.add(R_, P.ref('R'), '10k', {'1': 'FB', '2': 'GND'}, rot=90,
       footprint='Resistor_SMD:R_0402_1005Metric')
P.write('../kicad')
```

- `conns` must list **every** pin as a net name or `'NC'`; missing or unknown pins raise an error.
- Pins named `~` must be connected by number.
- Place passives with `rot=90` (pin 1 left, pin 2 right) for readable horizontal R/C/L.
- Use one `PWR_FLAG` per power rail and GND.
- A runnable, library-free example is in [`examples/minimal-board`](../examples/minimal-board/build.py).

## Pitfalls

- ERC does not reliably catch a reference used twice on different sheets; `netcheck` and the BOM do. Reserve fixed references.
- Pin number vs. pin name collisions (DDR3 ball `A7` vs. address pin `A7`): map such parts by number only.
- Parallel `power_out` pins (multi-LX regulators) or a `PWR_FLAG` on a net already driven by `power_out` cause `pin_to_pin` errors: make LX pins `passive` and drop the flag.
- Nets with only `power_in` pins need a `PWR_FLAG`.
- Strings must escape newlines; keep text lines 2.54 mm apart (grid snapping merges closer lines).
- Stacked hidden pins share one label; hidden NC pins may be left out.
- Local nets appear in the netlist as `/Sheet Name/NET`; compare on the last path component.
- Library pin types sometimes differ from reality (TPS3808 CT, TPD4E05U06 NC pass-through pins): inspect `load_lib(...).pins` first.
- Library pin numbers change between KiCad versions (KiCad 10: USB_A shield `5` becomes `SH`). Connect by pin name where possible and regenerate and rerun `netcheck` after any KiCad upgrade.
- KiCad 10 pretty-prints the netlist; `netcheck.load` collapses whitespace before parsing.
- A site that curl/WebFetch cannot reach can often still be listed through a `site:` web search.
- Read third-party skills fully before trusting them; one "PCB pipeline" skill faked DRC and "manufacturing ready" reports when KiCad was absent.
