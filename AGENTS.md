# Instructions for AI agents (any model, any tool)

This repository helps you design a KiCad board end to end: schematic, placement, routing, checks, hand-off.
You do not need Claude Code to use it. Everything runs as plain Python / shell commands.

## Where to start

| Task | Read | Run |
|---|---|---|
| Generate a KiCad schematic from Python | `skills/kicad-schematic-generator/SKILL.md` | `skills/kicad-schematic-generator/gen/kigen.py`, `netcheck.py`; example in `examples/minimal-board/build.py` |
| Place, route, repair and release a PCB | `toolkit/AGENTS.md` (full procedure), then `skills/kicad-pcb-autorouter-workflow/SKILL.md` (rationale and pitfalls) | tools in `toolkit/kat/` (`ncroute.py`, `astar1.py`, `drc.sh`, ...) |
| Understand a tool's arguments | `toolkit/README.md` (tool reference table) | `python3 toolkit/kat/<tool>.py` |

`SKILL.md` files are written as Claude Code skills (front matter plus instructions), but they are ordinary Markdown:
read them as procedures and checklists.

## Setup check (do this first, and tell the user what you find)

1. `python3 -c "import pcbnew; print(pcbnew.Version())"` and `kicad-cli --version`. If `pcbnew` is missing, find the
   Python that ships with KiCad. The toolkit targets **KiCad 8-10**; the schematic generator targets KiCad 9/10.
2. `cd toolkit && pip install -r requirements.txt && make`.
3. `toolkit/examples/demo/run_demo.sh` and `toolkit/tests/smoke.sh` should succeed before you touch a user's board.

## Honest status

The code was imported into this repository without being executed (the import environment only had KiCad 7). If a
tool fails on first run, report the exact error to the user instead of working around it silently, and say which
KiCad version you used.

## Rules that apply everywhere

- Never invent pinouts. Take pin numbers from a datasheet, a reference schematic or the stock KiCad library.
- Write a new file at each stage; never edit the user's board in place. Report every stage.
- Copy the board's `.kicad_pro` and `.kicad_dru` next to every intermediate `.kicad_pcb` before loading, filling
  zones or running DRC.
- Do not call a board finished because DRC/ERC/parity are clean. Verify connector orientation, power pins against
  the vendor reference, footprint pads without nets, and list what still needs a physical check.
- Verify every automated review finding yourself before changing anything; ask the user before changes that alter
  the architecture or cannot be undone.
