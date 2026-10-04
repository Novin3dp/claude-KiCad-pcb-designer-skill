---
name: "kicad-pcb-autorouter-workflow"
description: "Use when designing or routing a custom PCB in KiCad end-to-end: multi-stage placement, a negotiated-congestion autorouter, plane/DRC repair, length and pair-skew tuning, an interactive HTML layer viewer, and a manufacturer-ready release package."
---

# KiCad PCB design + autorouting + interactive viewer workflow

A repeatable process for taking a KiCad schematic to a routed, DRC-clean, manufacturer-ready PCB with a custom
negotiated-congestion (PathFinder-style) router, then packaging it as a real KiCad project, fab outputs and an
interactive HTML viewer the user can review without opening KiCad. Proven on a 6-layer Allwinner H3 + DDR3 SBC
(85 x 56 mm, TFBGA-347 at 0.65 mm, HDMI Type A, 275 parts, DRC 0 / ERC 0 / parity 0), taken through ECO releases
v2 -> v5.1 including a full independent design review.

## When to use

- The user wants a custom PCB designed/routed (not just a schematic) in KiCad.
- The board is too complex for KiCad's built-in tools (BGAs, HDI stacks, split planes, diff pairs, tight escapes).
- The user wants to review progress visually (per layer, with vias shown) across incremental stages.
- The user asks for a final, manufacturer-ready design, or a full review "from 0 to 100" of an existing one: go
  stage by stage, report every stage, never present a pre-design as final.

## Overall pipeline

1. **Schematic first.** Run `kicad-cli sch erc` until 0 violations, then `kicad-cli sch export netlist`.
2. **Placement** (`stage1.py` with the `pcbnew` API): outline, holes, keepouts, per-block placement, courtyard checks;
   iterate until a placement-overlap checker reports clean.
   - In a centroid placer give power/GND nets weight 0 for parts that have any signal net, otherwise GND pulls parts
     tens of mm away. Anchor power-only parts (decaps) to their IC's pins on the same sheet.
   - Reserve escape corridors as keepouts BEFORE placing small parts (BGA side bands, the HDMI corridor, the DDR
     channel, connector via fields).
   - Check signal ORDER along each chain before routing (SoC balls -> ESD / flow-through part -> connector pins).
   - Place each buck as a unit: input cap across VIN/GND within 1 mm, SW pin facing the inductor, SW node short on
     the outer layer. Rotate the SOT-23-6 so SW faces the inductor (pin 2 sits between VIN and GND).
   - **Edge connectors: check the mating direction, not just the position.** Draw the Fab outline: the card / plug
     side (e.g. the microSD card outline, local +y on Hirose DM3AT) must point OUT of the board. A socket placed
     with its contacts at the edge and its slot facing inward passes DRC and is unusable. Keep shield/front pads
     inside the copper-to-edge rule.
3. **Fan-out / planes / decaps** (`stage2.py`): BGA dog-bone vias, split power-plane zones with wide necks out of the
   ball field (no router vias on the necks), decaps with a via in or at every pad, keepouts protecting escape
   corridors and buck switch-node islands. Lock every fan-out via and stub you want to keep (rip scripts remove all
   unlocked copper of a net). Fine-pitch connector rear rows that cannot escape get via-in-pad (IPC-4761 VII).
   QFN exposed pads get a via array (3 x 3, 0.31/0.15) - filter the footprint's paste-only sub-pads (net '') out
   of the obstacle list first or no via fits.
4. **Autoroute with a negotiated-congestion router** (`ncroute.py`): one routing object per net or diff pair, a
   static legality field from ALL existing copper (including rule areas inside footprints), PathFinder rip-up
   (present x history pressure) until conflicts reach 0 or plateau. Knobs live in a per-board `cfg_*.py`: layers,
   grid origin/resolution, net-class clearances, per-net width and layer cost, pair handling, via cost, keepouts,
   plane nets. Variant configs are cheap (`from cfg_x import *`, override one function).
   - Route in stages by net group with a net-name regex env var (`NETRX`), saving state between stages.
   - The router only routes what is missing: partly ripped nets reconnect their remaining islands, so a local
     ECO = delete the local copper + `NETRX` on those nets.
   - Pairs: prefer a 'fat pair' centreline split into P/N with exact geometric validation, falling back to two
     single nets; never leave a partially drawn illegal pair.
   - At the end, drop (fully un-write) any net still touching a conflicting cell; log `failed` (never routed) and
     `dropped` (removed for conflicts) separately. A dropped net is then routed alone (step 6 tools).
   - `STAG` counts iterations since the last best score, not total iterations: a run that improves late runs long
     (10 nets near a dense connector took ~40 min). Budget for it.
5. **DRC loop.** `kicad-cli pcb drc --format json --severity-all` on a refilled copy after every significant change
   (a `drc5.sh BOARD TAG` wrapper: copy pro/dru, refill, DRC, summarise). Fix in order: shorts > clearance >
   unconnected > tracks_crossing > items_not_allowed > diff_pair_* > dangling.
6. **Single connections in dense areas** (BGA, connector rows) - small exact tools beat re-running the big router:
   - `astar1.py NET a b LAYERS WIN W CL`: grid A* (0.025 mm) over chosen layers with exact shapely clearance,
     layer changes via checked vias, footprint keepouts honoured, then greedy line-of-sight simplification with the
     exact check. Use the BGA clearance (0.10) only inside the ball field and the net class clearance (e.g. PWR
     0.12) outside it: split a long route at the BGA exit into two runs, or you get clearance errors at the vias.
   - `movevia.py x,y dx,dy`: nudge one unlocked via (and its own tracks' ends) 0.05-0.3 mm to open a channel
     (0.60 -> 0.65 mm via spacing lets a 0.1 mm track pass at 0.10 clearance).
   - `restore_net.py REF IN OUT NET CL AREA`: copy a lost BGA fan-out (stub + via) back from an older board when a
     cleanup removed it; the router cannot re-escape a ball by itself.
   - `place_free.py REF X Y R SIDE ROTS CL`: nearest legal spot for a new / moved part (pads vs foreign copper with
     an STRtree, courtyard vs courtyards, edge margin). Prefilter obstacles to a window or it takes minutes.
   - Topologically stuck nets: check connected components of the legality grid; source and target in different
     components = a placement fix, not a router tweak.
7. **Length and skew.**
   - Rubber-band old meanders first, then tune each DDR byte lane to its own DQS length (not to the longest DQ),
     pairs (DQS, CK) matched first with the lagging leg grown first, address/command to CK. Windowed accordions
     that check the net's own copper too. Modify the existing segment instead of Remove() (SWIG staleness).
   - Compute Zdiff of loosely coupled pairs with a 2-D field solver; relax the DRU gap rule with a comment instead
     of shipping unexplained warnings.
   - Report remaining DDR mismatch in mm and ps (~6-7 ps/mm) with a safe starting DRAM clock (528 MHz on H3).
8. **Interactive HTML viewer.** Per-stage JSON (footprints, pads, tracks, vias, zone fills, nets) in one
   self-contained page: per-layer toggles, via toggle, net/part search, stage picker, stackup tab, notes per stage
   (in the user's language). Ratsnest from DRC `unconnected_items`. Derive each version's viewer script from the
   previous one (`mk_viewer_vN.py` patches stages + notes) and re-publish to the same Artifact URL.
9. **Deliver the real project, not just images** (release checklist below), zipped.

## Full design review (do this before any order, and whenever the user asks for one)

1. Run 4 independent read-only review agents in parallel, each with the netlist dump, the board path and the
   reference schematics: **power** (rails, set points vs abs-max, input protection ratings, current budget, OR-ing),
   **SoC / DDR** (every power / special ball against the vendor reference: efuse, RTC, CPUS domain, sense balls,
   ADC / test pins), **peripherals** (connector pinouts, detect switches, ESD, pull-ups, diode directions),
   **PCB physical / fab** (footprint-vs-symbol pin maps, connector orientation, standoff clearance, hot loops,
   EP vias, current paths, RF feed, BOM / CPL / gerber completeness, silk, fiducials). If an agent dies (rate
   limit), relaunch it with the same prompt.
2. **Verify every finding yourself** before changing anything: `pdftotext -bbox` to locate a pin in the reference
   PDF, then `pdftoppm -r 300-400 -x -y -W -H` to crop and LOOK at that part of the schematic. Agents both invent
   problems (DDC level shift, WAKE pin) and find real ones (the slot facing inward). Classify: blocker / major /
   minor / false alarm, and report the verified list to the user before fixing.
3. Defects found this way on a board that was already DRC/ERC/parity clean - check for each on every board:
   - footprint pads with NO net because the symbol has fewer pins (Micro_SD_Card_Det1 on a DM3AT with two
     detect contacts -> use `Micro_SD_Card_Det2`, pad 10 to GND);
   - SoC special balls wired "logically" but not as the vendor does (H3: VDD_EFUSEBP gets only 4.7 uF to GND;
     VDD_CPUS is fed from RTC_VIO, not VDD_SYS);
   - a DNP 0R as the only local fallback of a remote-sense feedback (an open sense ball runs the rail away) ->
     fit ~10 ohm;
   - a pull-up diode drawn backwards (blocks the pull-up); a rail set point whose worst case exceeds a pin's
     abs max; current-limit settings whose sum exceeds the source; a fuse / TVS without a DC rating for the
     input range; a high-Vf OR diode on a 5 V output (HDMI 5 V fell to ~4.55 V);
   - buck input caps > 5 mm from VIN, SW routed on the far layer through vias, one tiny via per GND pin;
   - a hand-fitted module that still has paste on its pads; no fiducials; BOM without supplier part numbers;
     references printed on pads.
4. Fix within the existing architecture (the user's "keep the design" constraint); ask before anything that
   changes it.

## ECO on a routed board (schematic change -> board)

- Change the generator, never hand-edit the schematic. **References must not shift**: removed parts consume their
  reference (`cx.ref('C')`), new parts take an explicit free reference (`C132`) or are appended at the end.
- Diff old vs new netlist (values, footprints, pin -> net) before touching the board, then apply with an ECO
  script: swap changed footprints in place, add new ones off-board, set every pad net, delete copper of vanished
  nets. Place new parts with `place_free.py`, connect them with `astar1.py` / the router.
- A 2-pin part whose pin nets swap (diode flipped in the schematic): rotate the footprint 180 deg in place - the
  existing tracks then land on the right pads.
- Moving / rotating a part: delete copper on its old pads AND every foreign item its new pads (+0.13 mm) or its
  keepouts hit, rip whole small nets that change topology (SW, BST, the bus to a turned connector), re-route.
- Widening a power feed in a pour layer: grow the zone toward the side whose loss nothing depends on. Growing a
  VCC_5V strip upward closed the only L4 link of the 3.3 V area around the BGA (one unconnected item, found by
  DRC); moving it down instead widened both. Check `unconnected` after every zone outline edit.
- A wide feed into fine-pitch connector pads (USB-C VBUS): a small top-layer zone (priority above GND, full pad
  connection, own clearance) instead of a wide track the router cannot fit between the pins.

## Planes, pours and connectivity repair

- After every change count fill pieces per zone and which pieces hold vias or pads. Slow signals on a power layer
  slice it into strips; a 0.65 mm fan-out via lattice blocks the fill when pitch - via - 2 x clearance is below the
  zone's min width.
- Fix order: (1) a DRU rule giving that plane 0.10 mm clearance inside the BGA rule area plus min thickness 0.10;
  (2) bridge leftover islands with a cluster linker (union-find over connectivity, grid Dijkstra between
  clusters); (3) only then reroute the cutting nets with a high plane-layer cost.
- Orphan plane pads: `plane_via.py IN OUT NET[,NET] [R]` drops a checked via inside a filled zone of that net. A pad
  that still has a stub attached is skipped - clean dangling copper first.
- **Dangling cleanup must match exactly**: net + layer + length + the reported end point (`dangle2.py`). A
  hit-test cleaner deletes long through-tracks that merely pass the reported point and breaks nets. Iterate DRC ->
  clean 2-3 times, then re-check unconnected.
- Outer GND pours: 0.25 mm clearance, 0.5 mm keep-away around RF, islands removed, stitching only where both pours
  exist, hole-to-hole check against every drill.

## Tooling pitfalls

- **Copy `.kicad_pro` + `.kicad_dru` next to EVERY intermediate board** before `LoadBoard` + `ZONE_FILLER`;
  `kicad-cli pcb drc` checks the SAVED fills - refill a copy first or trust no zone result.
- **One bad DRU rule drops ALL custom rules silently.** `min_resolved_spokes` takes a bare number.
- SWIG proxies: never compare with `is` / `in` on pcbnew objects (a new proxy each call); compare pad numbers,
  positions or indices. After `Remove()` wrappers go stale: read everything first, mutate at the end.
- Pad sizes from `GetSize()` are pre-rotation; use `GetBoundingBox()` for geometry.
- Footprints carry their own rule areas (`f.Zones()`, e.g. no tracks/vias under a card socket): every custom
  tool must load them, or DRC reports `items_not_allowed` later.
- Rip scripts remove every unlocked item of a net, including fan-out vias never locked; after a rip confirm each
  BGA ball / connector pin still has its escape.
- The shell tool has a ~2 min limit per call: start long jobs with `setsid nohup bash job.sh &`, write a `.done`
  marker, poll with `sleep`; never SIGTERM a router mid-negotiation.
- Never `pkill -f` with a pattern that also matches your own shell.
- Adding symbol fields (MPN, LCSC) makes parity report `footprint_symbol_field_mismatch` for every part: copy the
  netlist fields to the footprints (hidden, Fab layer) as a release step.

## Release checklist (manufacturer-ready)

1. Merge the board `.kicad_pro` (net classes, rules) with the schematic project's ERC section; name board, pro and
   dru after the schematic project.
2. `kicad-cli pcb drc --schematic-parity` until 0 errors, 0 unconnected, parity 0 (fields copied, DNP flags).
3. Real stackup in the board and an impedance table from the field solver.
4. **BOM with supplier numbers**: one agent maps every BOM line to MPN + LCSC number, checking each on the JLC parts
   API (stock, Basic/Extended, package, voltage) into `lcsc_map.csv`; the generator injects `MPN` / `LCSC` symbol
   fields from it. Export the grouped BOM plus `bom_jlcpcb.csv` (Comment, Designator, Footprint, LCSC Part #) and
   the CPL; exclude hand-fitted modules, test pads, holes and fiducials (FP_EXCLUDE_FROM_POS_FILES / BOM).
5. Fiducials: 3 per side, `Fiducial_1mm_Mask2mm`, attributes board-only + exclude from BOM + exclude from pos,
   placed with `place_free.py` at CL 0.6, away from connector bodies.
6. Silk: re-place each reference (current spot, then around the part at 0.8/0.7/0.6 mm, both angles) so none sits
   on a pad, part outline, other text or edge; hide what does not fit (it stays on Fab). Check with the silk DRC
   severities temporarily set to warning.
7. Gerber X2 (explicit layer list), Excellon PTH/NPTH + maps, positions, CPL, schematic PDF, ERC/DRC reports,
   renders. Look at the bottom render: mirrored view, connector slots at the edge.
8. **Second-opinion review in the release script**: the kicad_skills `eda_toolkit` (Apache-2.0, github
   sabas0ba/kicad_skills) runs natively without Docker - vendor `src/` into `tools/kicad_skills` and run
   `PYTHONPATH=tools/kicad_skills/src python3 -m eda_toolkit.cli pcb review BOARD --no-cli --collapse 6 --text`
   (+ `-o review.json --map map.png`) and `... sch review SCH --text` (~3 min each). Verify every finding and
   write `fab/review/WAIVERS.md` (real / by design / false alarm). Known false alarms on dense boards:
   `route.stub` (track end inside the pad but off its centre), `layout.pad_collision` on rotated 1210s,
   `board.edge_clearance` on small pads, `no_decoupling` on sense balls, `no_dc_path` on EPHY centre taps,
   `emc.parallel_run` on diff pairs, `unprotected_power_input` on 5 V outputs. Real ones worth acting on:
   power feeds left at signal width (`track.thin_power`), THT pads flooded solid in inner planes (hand-solder
   warning), silk text < 0.8 mm, tracks under standoff heads (`mechanical.fastener_copper`).
   `eda diff OLD NEW -o dir` gives a net / component / board-image change list between releases.
9. Package `kicad/`, `fab/` (+ `review/`), `docs/` (viewer, renders, length data), `tools/` and a README whose top
   section is "what changed in this version" (table: area / problem / fix) and "checked and found correct"; zip.
10. Fab notes: impedance control, ENIG, epoxy filled + capped vias for via-in-pad, min track/space and via,
    double-sided assembly, rotation check in the assembler DFM preview (the CPL has KiCad rotations), low-stock
    parts, THT parts in the CPL cost THT assembly, panel rails only on edges without overhanging connectors.

## Reporting

Report every stage as it completes, in the user's language. Give a precise breakdown of anything not ideal:
unrouted vs. dropped vs. lingering DRC, length mismatch in mm and ps, what was traded. Do not call a board done
because DRC is clean: a board can be DRC/ERC/parity clean and still have a card slot facing inward or a SoC pin on
the wrong rail. Separate cosmetic leftovers from real risks, and list what still needs a physical check (detect
switch polarity, module pad handedness against a 1:1 print).