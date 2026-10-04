# Instructions for AI agents using this toolkit

Use these tools to take a KiCad design from schematic to a routed, DRC-clean, manufacturer-ready board. Work in
stages, write a new file at every stage, and report each stage to the user. Never present a partial board as final.

## Setup (once)

1. Check `python3 -c "import pcbnew; print(pcbnew.Version())"` and `kicad-cli --version`.
2. Run `pip install -r requirements.txt` (add `--break-system-packages` on a managed Python), then `make`.
3. Run `examples/demo/run_demo.sh` and `tests/smoke.sh`. Both must succeed before you touch the user's board.

## Pipeline

1. **Schematic.** Generate it from Python (`schematic/`, see `examples/demo_sch/make_sch.py`) or take the user's.
   Loop `kicad-cli sch erc` until 0, then `kicad-cli sch export netlist` and `python3 schematic/netcheck.py`.
2. **Placement** with the pcbnew API:
   - Place outline and holes first, then keepouts for escape corridors, then parts block by block.
   - Each buck goes as a unit: input cap within 1 mm of VIN/GND, SW pin facing the inductor.
   - Point edge connectors' mating side out of the board.
   - Check courtyards with DRC.
3. **Fan-out and planes.**
   - BGA dog-bone vias and plane zones.
   - `plane_via.py` for pads of plane nets.
   - Lock fan-outs (`SetLocked(True)`).
4. **Route.** Copy `kat/cfg_template.py` to `cfg_<board>.py` and set layers, clearances (match the `.kicad_dru`),
   widths, pairs and plane nets.
   - Run `ncroute.py cfg IN OUT`.
   - Route in stages with `NETRX` (memory, then pairs, then the rest).
   - Read `failed` and `dropped` at the end of the log.
5. **Repair loop.** `drc.sh OUT`, then fix in this order: shorts > clearance > unconnected > items_not_allowed >
   dangling.
   - Local problem: delete that copper and re-run `ncroute.py` with `NETRX` on those nets. It only adds missing
     links.
   - Single connection in a dense spot: use `astar1.py`. If it finds no path, open a channel with `movevia.py` or
     move a part with `place_free.py`.
   - Lost BGA escape: use `restore_net.py` from an earlier board.
   - Stranded plane island: use `cluster_link.py`.
   - Dangling copper: use `dangle2.py` with the DRC JSON, 2-3 rounds.
6. **Length and skew.** `pair_skew.py` for HDMI / USB / Ethernet. For DDR: `ddr_rubber.py`, then `ddr_tune.py`,
   then `ddrsum.py`, after adapting `ddr_profile.py`. Report residual mismatch in mm and ps (~6-7 ps/mm).
7. **Finish.**
   - `gnd_pour.py` for outer GND pours and stitching.
   - `silk_refs.py` for references.
   - `copy_fields.py` after adding MPN / LCSC fields.
   - `drc.sh OUT dir --parity` until 0 errors, 0 unconnected, parity 0.
8. **Review before calling it done.** Clean DRC is not enough.
   - Check every footprint pad has the intended net (pads with none = symbol/footprint mismatch).
   - Check SoC power and special pins against the vendor reference schematic.
   - Check connector orientation (look at the Fab layer and the bottom render).
   - Check power-path widths, buck input-cap distance, exposed-pad vias, and part voltage ratings against the
     input range.
   - Verify each review finding yourself before changing anything.
9. **Hand-off.**
   - `make_viewer.py` gives the user an interactive page per stage.
   - Release Gerber X2 / Excellon / positions / BOM with `kicad-cli`, with the project's `.kicad_pro`, `.kicad_dru`
     and schematic in one folder.
   - `examples/h3_sbc/release_v5.sh` shows a complete release script.

## Rules

- Copy the board's `.kicad_pro` and `.kicad_dru` next to every intermediate `.kicad_pcb` (same base name) before
  loading, filling zones or running DRC.
- Never trust zone results in DRC without a refill. `drc.sh` refills a copy.
- Do not compare pcbnew objects with `is` / `in`. Collect, then remove at the end. Use separate processes for edit
  and analysis.
- Long jobs: `setsid nohup bash job.sh &` plus a `.done` marker. Never kill `ncroute.py` mid-run.
- Look at the board, not only at numbers: `layerplot.py` / `netplot.py` PNGs of the region you change.
- When a change cannot be undone or alters the architecture, ask the user first.
