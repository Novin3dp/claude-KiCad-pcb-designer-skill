# PCB + autorouter workflow guide

Skill: [`skills/kicad-pcb-autorouter-workflow/SKILL.md`](../skills/kicad-pcb-autorouter-workflow/SKILL.md)

The skill is a methodology. Claude writes the per-board scripts (placement, fan-out, router, repair, viewer export); this guide explains the ideas so you can review and steer them.

## When to use it

- You want a custom PCB designed and routed in KiCad, not just a schematic.
- The board is too complex for the built-in tools (BGAs, HDI stacks, split planes, differential pairs, tight escapes).
- You want to review progress visually, per layer, with vias shown, across incremental stages.
- You want a final manufacturer-ready design: go stage by stage, report every stage, never present a pre-design as final.

## Negotiated-congestion routing in short

Every net (or diff pair) is a routing object. A static legality field is built from all existing copper. Nets are routed even where they conflict, then ripped up and rerouted while a *present-congestion* term and an accumulating *history* term raise the cost of contested cells, until conflicts reach 0 or plateau. At the end, any net still touching a conflicting cell is removed completely, because a DRC-clean board with N missing nets beats one with shorts. `failed` and `dropped` nets are logged separately.

Operational tips from the skill:

- Route in stages by net group (plane stubs, DDR, then the rest) with a net-name regex, saving state between stages.
- Prefer a "fat pair" centreline split into P/N with exact geometric validation; fall back to two single nets; never leave a half-drawn illegal pair.
- `STAG` counts iterations since the last best score, not total iterations, so a run that improves late runs long (about 40 minutes for 10 nets near a dense connector in the reference project). Budget for it.
- The router only routes what is missing, so a local ECO is: delete the local copper and rerun with `NETRX` on those nets.
- Run long jobs in the background with `.done` markers and a lock file. Never SIGTERM a router mid-negotiation.

## DRC repair order

shorts, clearance, unconnected, tracks_crossing, items_not_allowed, diff_pair_*, dangling. Run DRC on a refilled copy of the board (a small wrapper that copies the project and rules, refills zones, runs DRC and summarises works well). Delete only the offending copper and reroute that net with the net filter.

## Stuck nets

Run a single-net isolated route and label connected components of the legality grid (`scipy.ndimage.label`). If source and target land in different components, the fix is a placement change (move the part out of the dense field), not a router tweak.

## Length and skew

- Check intra-pair skew for every pair (DQS, CK), not just lane matching.
- Rubber-band old meanders first, then tune each DDR byte lane to its own DQS length (not to the longest DQ). Match pairs (DQS, CK) first, growing the lagging leg first, then address/command to CK. Modify the existing segment instead of calling `Remove()`.
- Trim uncoupled pairs (HDMI, USB, ETH) with accordion meanders on the shorter line.
- Compute Zdiff at the real gaps with a 2-D field solver; if within spec (for example HDMI 100 ohm +-15%), relax the `diff_pair_gap` DRU rule and comment why.
- Report DDR mismatch in mm and ps (about 6-7 ps/mm) with a safe starting DRAM clock.

## Single connections in dense areas

Small exact tools beat re-running the big router for one stubborn net:

| Tool | Purpose |
|---|---|
| `astar1.py NET a b LAYERS WIN W CL` | Grid A* (0.025 mm) with exact clearance checks, via-checked layer changes, footprint keepouts and line-of-sight simplification. Use the BGA clearance only inside the ball field and the net-class clearance outside; split a route at the BGA exit. |
| `movevia.py x,y dx,dy` | Nudge one unlocked via and its tracks' ends 0.05-0.3 mm to open a channel. |
| `restore_net.py REF IN OUT NET CL AREA` | Copy a lost BGA fan-out back from an older board. |
| `place_free.py REF X Y R SIDE ROTS CL` | Nearest legal spot for a new or moved part. Prefilter obstacles to a window or it is slow. |
| `plane_via.py IN OUT NET[,NET] [R]` | Drop a checked via inside a filled zone for an orphan plane pad. |

These names come from the skill; the scripts are written per project and are not shipped in this repository.

## Placement details worth checking

- Place each buck converter as a unit: input capacitor across VIN/GND within 1 mm, SW pin facing the inductor, SW node short on the outer layer.
- **Edge connectors: check the mating direction, not just the position.** A socket with its contacts at the edge but its slot facing inward passes DRC and is unusable.
- QFN exposed pads get a via array; filter paste-only sub-pads out of the obstacle list first.

## Full design review

Run before any order and whenever a full review is requested.

1. Four independent read-only review passes in parallel: **power**, **SoC / DDR**, **peripherals**, **PCB physical / fab**. If one dies, relaunch it with the same prompt.
2. **Verify every finding yourself**: locate the pin in the reference PDF (`pdftotext -bbox`), crop and look at it (`pdftoppm -r 300-400 -x -y -W -H`). Classify as blocker / major / minor / false alarm and report the verified list before fixing.
3. Check each board for defects that survive clean DRC/ERC/parity:
   - footprint pads with no net because the symbol has fewer pins (for example a microSD socket with two detect contacts needing `Micro_SD_Card_Det2`);
   - SoC special balls wired "logically" instead of as the vendor does;
   - a DNP 0R as the only local fallback of a remote-sense feedback;
   - a pull-up diode drawn backwards, a rail whose worst case exceeds a pin's absolute maximum, current limits that sum above the source, a fuse/TVS without a DC rating for the input range, a high-Vf OR diode on a 5 V output;
   - buck input caps more than 5 mm from VIN, SW routed on the far layer, one tiny via per GND pin;
   - hand-fitted modules that still have paste, no fiducials, a BOM without supplier part numbers, references printed on pads.
4. Fix within the existing architecture; ask before anything that changes it.

## ECO on a routed board

- Change the generator, never hand-edit the schematic. **References must not shift**: removed parts keep their reference reserved, new parts take explicit free references.
- Diff old and new netlists (values, footprints, pin to net) before touching the board; then swap changed footprints in place, add new ones off-board, set every pad net and delete copper of vanished nets.
- A 2-pin part whose pin nets swap: rotate the footprint 180 degrees in place.
- Moving or rotating a part: delete copper on its old pads and on every foreign item its new pads (+0.13 mm) or keepouts hit, rip whole small nets that change topology, reroute.
- Widening a power feed in a pour layer: grow toward the side nothing depends on, and check `unconnected` after every zone outline edit.
- A wide feed into fine-pitch connector pads (USB-C VBUS): a small top-layer zone instead of a wide track.

## Planes and pours

See the "Planes, pours and connectivity repair" section of the skill: a DRU rule for web flow inside the BGA rule area, cluster linking of stranded islands, vias for orphan plane pads, exact-match dangling cleanup (net + layer + length + reported end point, since a hit-test cleaner deletes long through-tracks), and GND pours with stitching.

## Tooling pitfalls

- Copy `.kicad_pro` and `.kicad_dru` next to **every** intermediate board before `LoadBoard` + `ZONE_FILLER`; `kicad-cli pcb drc` checks the saved fills, so refill a copy first.
- One bad DRU rule drops all custom rules silently (symptom: clearance errors jump to hundreds while diff-pair warnings vanish).
- Never compare pcbnew objects with `is` or `in` (SWIG makes a new proxy per call); compare pad numbers, positions or indices. After `Remove()` wrappers go stale: read everything first and mutate at the end.
- Pad sizes from `GetSize()` are pre-rotation; use `GetBoundingBox()`.
- Footprints carry their own rule areas (`f.Zones()`); every custom tool must load them or DRC later reports `items_not_allowed`.
- The shell tool has a roughly 2-minute limit per call: start long jobs with `setsid nohup bash job.sh &`, write a `.done` marker and poll.
- Adding symbol fields (MPN, LCSC) makes parity report `footprint_symbol_field_mismatch`; copy the netlist fields to the footprints as a release step.
- Rip scripts remove every unlocked item of a net, including unlocked fan-out vias.
- Re-add tracks at the exact endpoints of removed copper, or length graphs break.
- Never `pkill -f` with a pattern that also matches your own shell.

## Release checklist

1. Merge the board `.kicad_pro` with the schematic project's ERC section; name board, pro and dru after the schematic project.
2. `kicad-cli pcb drc --schematic-parity` to 0 errors, 0 unconnected, parity 0.
3. Real stackup in the board and an impedance table from the field solver.
4. **BOM with supplier numbers**: map every BOM line to MPN + LCSC number, checking stock, Basic/Extended, package and voltage on the JLC parts API into `lcsc_map.csv`; inject `MPN` / `LCSC` fields from it. Export the grouped BOM, `bom_jlcpcb.csv` (Comment, Designator, Footprint, LCSC Part #) and the CPL; exclude hand-fitted modules, test pads, holes and fiducials.
5. Fiducials: 3 per side, `Fiducial_1mm_Mask2mm`, board-only, excluded from BOM and position files, placed away from connector bodies.
6. Silkscreen: re-place each reference so none sits on a pad, outline, other text or the edge; hide what does not fit (it stays on Fab).
7. Gerber X2 (explicit layer list), Excellon PTH/NPTH + maps, positions, CPL, schematic PDF, ERC/DRC reports and renders. Look at the bottom render: mirrored view, connector slots at the edge.
8. **Optional second-opinion review** with the external `eda_toolkit` from `sabas0ba/kicad_skills` (Apache-2.0): vendor `src/` into `tools/kicad_skills` and run `pcb review` / `sch review`. Verify every finding and record them in `fab/review/WAIVERS.md` as real / by design / false alarm. The skill lists known false alarms on dense boards (`route.stub`, `layout.pad_collision` on rotated 1210s, `board.edge_clearance` on small pads, `no_decoupling` on sense balls, `emc.parallel_run` on diff pairs, and others) and real findings worth acting on (`track.thin_power`, solid-flooded THT pads, silk text under 0.8 mm, tracks under standoff heads). This is third-party code: read it before running it.
9. Package `kicad/`, `fab/` (+ `review/`), `docs/`, `tools/` and a README whose top section is "what changed in this version" and "checked and found correct"; zip it.
10. Fab notes: impedance control, ENIG, epoxy-filled and capped vias for via-in-pad, min track/space/via, double-sided assembly, rotation check in the assembler DFM preview (the CPL has KiCad rotations), low-stock parts, THT parts in the CPL costing THT assembly, panel rails only on edges without overhanging connectors.

## Reporting

Report each stage in the user's language. Give the exact breakdown of anything not ideal: unrouted vs. dropped vs. lingering DRC, length mismatch in mm and ps, and what was traded off. A clean DRC/ERC/parity board can still have a slot facing inward or a SoC pin on the wrong rail, so separate cosmetic leftovers from real risks and list what still needs a physical check (detect-switch polarity, module pad handedness against a 1:1 print).
