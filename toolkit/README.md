# kicad-autoroute-toolkit (KAT)

Python tools for scripted KiCad board design. Any person or AI agent can drive them: every tool is a small CLI that
reads a `.kicad_pcb`, changes it through KiCad's own `pcbnew` Python API, and writes a new file. Nothing is edited in
place.

The toolkit was built and proven on a 6-layer Allwinner H3 + DDR3 single-board computer: 85 x 56 mm, TFBGA-347 at
0.65 mm, DDR3 x16, HDMI, USB, Ethernet, Wi-Fi, 275 parts, DRC 0 / ERC 0 / parity 0. That board is in
`examples/h3_sbc/` as a reference.

| Area | Tools |
| --- | --- |
| Schematic from Python | `schematic/kigen.py`, `schematic/common.py`, `schematic/netcheck.py` |
| Autorouting | `kat/ncroute.py` (negotiated-congestion / PathFinder router, C core) + a per-board config |
| Local fixes in dense areas | `astar1.py` (one exact connection), `movevia.py`, `place_free.py`, `restore_net.py` |
| Planes and pours | `plane_via.py`, `cluster_link.py`, `gnd_pour.py` |
| Clean-up and checks | `drc.sh` + `drcsum.py`, `dangle2.py`, `silk_refs.py` |
| Length and skew | `pair_skew.py`, `ddr_rubber.py`, `ddr_tune.py`, `ddrsum.py` (+ `tune2.py`, `tune3.py`, `ddr_report.py`) |
| ECO (schematic -> routed board) | `eco.py`, `copy_fields.py` |
| Review and hand-off | `make_viewer.py` (interactive HTML board viewer), `layerplot.py`, `netplot.py` |

## Requirements

- KiCad 8, 9 or 10 with its Python module (`python3 -c "import pcbnew"` must work) and `kicad-cli`.
  It was tested on KiCad 10.0 / Python 3.11 / Ubuntu 24.04.
- Python packages: `pip install -r requirements.txt` (numpy, scipy, shapely >= 2, matplotlib, Pillow).
- `gcc`, to build the router core: run `make` (this builds `kat/libncr.so` from `csrc/ncr.c`).
- Optional: Chromium / Playwright, if you want screenshots of the viewer.

## Quick start (2 minutes)

```bash
make                         # builds kat/libncr.so
cd examples/demo && ./run_demo.sh
# -> demo_routed.kicad_pcb (DRC 0, unconnected 0) and demo_viewer.html
../../tests/smoke.sh         # exercises every generic tool on the demo board
cd ../demo_sch && python3 make_sch.py out && kicad-cli sch erc out/demo.kicad_sch   # schematic from Python, ERC 0
```

`run_demo.sh` shows the basic loop:

```bash
python3 kat/plane_via.py  board.kicad_pcb planes.kicad_pcb GND,+3V3 2.0   # pads of plane nets -> vias into the planes
python3 kat/ncroute.py    cfg_board.py planes.kicad_pcb routed.kicad_pcb 40  # route everything else
kat/drc.sh routed.kicad_pcb                                                 # refill + DRC + readable summary
python3 kat/make_viewer.py -o view.html board.kicad_pcb=placed routed.kicad_pcb=routed
```

Keep the board's `.kicad_pro` / `.kicad_dru` next to every intermediate board file, copying them under the new name.
Design rules live there. Zone fills and DRC done without them silently use defaults.

## The router (`kat/ncroute.py`)

```
ncroute.py CFG IN.kicad_pcb OUT.kicad_pcb [MAXIT=40]
```

How it works:

- Every net with more than one copper cluster becomes a routing object. Existing copper is kept, so a partly ripped
  net only gets its missing links.
- Legality is exact: a clearance-slack field (`slack.py`) is built from all foreign copper, honouring net-class
  clearances, keepouts and footprint rule areas.
- Each object is routed with A* on a 0.05 mm multi-layer grid (`libncr.so`). Conflicts are then negotiated with
  PathFinder present/history costs until none remain or the run stagnates.
- Differential pairs are routed as one "fat" centre line split into P/N, or as coupled singles.
- At the end, a net still in conflict is removed whole and listed under `dropped`. A net that could never be
  routed is listed under `failed`.

Write the board config (`CFG`) by copying `kat/cfg_template.py` (documented knobs: layers, grid, clearances, widths,
layer costs, pairs, via cost, keepouts, plane nets). It can be passed as a module name or a file path.
`examples/h3_sbc/cfg_sbc.py` is a full 6-layer example with DDR / HDMI / USB / RF rules.

Environment variables:

| Variable | Effect |
| --- | --- |
| `NETRX='regex'` | Route only nets whose name matches. Use it to route in stages, or for a local ECO after deleting copper. |
| `STAG=N` | Stop N iterations after the last improvement. A late improvement makes the run long. |
| `LOAD=1` | Continue from `OUT_ncstate.pkl`. One continuation helps; repeated ones rip good nets. |
| `LENFIX='{"NET": 18.0}'` | Per-net length bound in mm. |
| `DBGFAIL=1` | Print why a terminal cannot be reached. |
| `ORDER_LAST='regex'` | Route these nets last. |
| `EPS`, `PRES`, `RIPALL_AFTER` | Rasterisation margin, initial present cost, iteration after which all nets are ripped. |

Never kill the router mid-negotiation: it writes its best state only at a controlled stop. Run long jobs as
`setsid nohup bash job.sh &` with a `.done` marker if your shell has a time limit.

## Tool reference (all in `kat/`)

| Tool | Usage | What it does |
| --- | --- | --- |
| `astar1.py` | `IN OUT NET x0,y0,LAYER\|via x1,y1,LAYER\|via LAYERS WIN [W CL VIA STEP]` | One connection by grid A* with exact clearance, layer changes through checked vias, keepouts honoured, then line-of-sight simplification. Use the BGA clearance only inside the ball field. Split a route at the BGA exit if the net class is wider outside. |
| `movevia.py` | `IN OUT x,y dx,dy [...]` | Nudge a via, dragging its own tracks, e.g. to open a 0.60 -> 0.65 mm channel. |
| `place_free.py` | `IN OUT REF X Y R F\|B [ROTS] [CL]` | Move a part to the nearest legal spot: pads clear of foreign copper, courtyard clear, edge margin. |
| `restore_net.py` | `REF IN OUT NETS [CL] [x0,y0,x1,y1]` | Copy a net's old copper (e.g. a lost BGA fan-out) back from an older board wherever it still fits. |
| `plane_via.py` | `IN OUT NET[,NET] [R]` | Give each orphan pad of a plane net a checked via inside a filled zone of that net. |
| `cluster_link.py` | `IN OUT NET [W] [WIN]` | Bridge stranded islands of a net (plane pieces, pads) to its main cluster. Env `SIG_LAYERS`, `BOX`. |
| `gnd_pour.py` | `IN OUT` | Outer-layer GND pours plus a stitching-via lattice (skips narrow plane necks, honours hole-to-hole). Env `RF_PREFIX`, `SPLIT_LAYERS`. |
| `drc.sh` | `BOARD [OUTDIR] [--parity]` | Refill a copy, run `kicad-cli pcb drc`, print `drcsum.py`. |
| `dangle2.py` | `IN OUT DRC.json` | Delete the dangling vias / track stubs DRC reported, with exact matching. Iterate DRC -> clean 2-3 times. |
| `silk_refs.py` | `IN OUT` | Re-place every reference designator off pads, outlines, other text and the edge (0.8 / 0.7 / 0.6 mm), or hide it on silk. |
| `pair_skew.py` | `IN OUT` | Accordion-trim intra-pair skew. Env `PAIRS='P:N:tol,...'`, `LAYERS`, `CLASS_CLR`, `PROTECT_LAYER`. |
| `ddr_rubber.py` / `ddr_tune.py` / `ddrsum.py` | `IN OUT` / `IN OUT` / `BOARD` | DDR3: straighten old meanders, tune lanes to their DQS and address to CK, report. Board specifics live in `ddr_profile.py` (env `DDR_PROFILE`, `SOC_REF`, `MEM_REFS`). |
| `eco.py` | `IN NEW.net OUT` | Apply a new netlist to a routed board: swap changed footprints in place, add new ones off-board, set pad nets, delete copper of vanished nets. Env `FP_LIBS`. |
| `copy_fields.py` | `IN NET OUT` | Copy symbol fields (MPN, LCSC, ...) to footprints so parity stays 0. Set DNP. Env `NO_POS` excludes hand-fitted parts from the CPL. |
| `make_viewer.py` | `-o out.html [--name] [--notes s1=f.html] [--group "Name=#hex=regex"] a.kicad_pcb[=Title] ...` | Self-contained interactive viewer: layers, vias, zones, ratsnest and DRC markers, net and part search, placement table, stages. |
| `layerplot.py` / `netplot.py` | see the docstrings | Matplotlib PNGs of one layer, or of selected nets on all layers. Useful for an AI to look at a region. |
| `viatool.py` | library | `Tool(board, cl)`: clearance-checked `via()`, `track()`, `vias_in(region)`, `commit()`. |

## Schematic generation (`schematic/`)

`kigen.py` writes KiCad 8/9/10 schematics from Python:

- Library symbols are copied from the stock libraries (`load_lib('Device', 'R')`). Custom multi-unit ICs are
  built from pin lists (`make_ic`).
- Every pin gets a wire stub plus a net label: a local label when the net lives on one sheet, a global label
  otherwise.
- A `Flow` lays parts out in sections on a sheet.

`common.py` adds `Ctx`: reference counters, plus R / C / CAPS / L / FBEAD / LEDR helpers with default footprints and
PWR_FLAGs. `netcheck.py` checks an exported netlist (single-pin nets, footprint pins missing, duplicate refs).
See `examples/demo_sch/make_sch.py` (ERC 0), and `examples/h3_sbc/gen/` for a 10-sheet SoC board.

Rules that keep an ECO on a routed board cheap:

- Change the generator, never the schematic.
- References must not shift: a removed part still consumes its reference (`cx.ref('C')`), and a new part takes
  an explicit free reference or goes at the end.
- Diff the old and new netlist before applying them with `eco.py`.

## Lessons that cost time (read before scripting a board)

- `kicad-cli pcb drc` checks the saved zone fills. Refill a copy first, with its pro / dru (`drc.sh`).
- One bad `.kicad_dru` rule silently drops all custom rules.
- SWIG proxies: never compare pcbnew objects with `is` / `in` (a new proxy each call). After `Remove()` wrappers go
  stale, so read everything first and mutate at the end.
- `GetSize()` of a pad is pre-rotation. Use `GetBoundingBox()` for geometry.
- Footprints carry their own rule areas (`f.Zones()`, e.g. no vias under a card socket). Every custom tool must
  honour them.
- Rip scripts remove unlocked fan-out vias too. Lock what you want to keep.
- A dangling-copper cleaner that hit-tests the reported point deletes long through-tracks. Match exactly
  (`dangle2.py`).
- Growing one plane zone can cut off another plane's only link. Check `unconnected` after every zone edit.
- DRC / ERC / parity clean is not "done". Check the mating direction of edge connectors (card slot facing out),
  footprint pads left without a net by a smaller symbol, SoC power pins against the vendor reference, buck input
  caps within 1 mm, and power feeds left at signal width.
- For a second opinion, the independent review in [kicad_skills](https://github.com/sabas0ba/kicad_skills)
  (Apache-2.0) runs natively: `PYTHONPATH=src python3 -m eda_toolkit.cli pcb review BOARD --no-cli --text`. Verify
  every finding; several are false alarms on dense boards.

## Layout

```
kat/              tools + libraries (flat: run any tool directly, they import each other)
csrc/ncr.c        router core (make -> kat/libncr.so)
schematic/        kigen schematic generator + netcheck
examples/demo/    unrouted 4-layer demo board -> routed, DRC 0 (run_demo.sh)
examples/demo_sch/ Python -> schematic demo, ERC 0
examples/h3_sbc/  the 6-layer H3 board's configs, ECO / fix scripts, generators and release script (reference only:
                  paths point at the original project)
tests/smoke.sh    runs every generic tool on the demo board
AGENTS.md         how an AI agent should use this toolkit
```

## License

MIT (see `LICENSE`). Change it if you publish under another license.
