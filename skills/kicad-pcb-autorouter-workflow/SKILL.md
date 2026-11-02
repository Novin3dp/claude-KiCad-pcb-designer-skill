---
name: "kicad-pcb-autorouter-workflow"
description: "Use for end-to-end KiCad PCB placement, negotiated-congestion routing, plane/DRC repair, length/skew tuning, design review, interactive visualization, and fabrication release."
---

# KiCad PCB design + autorouting workflow

A staged workflow for taking a KiCad schematic to a routed, reviewed, manufacturer-ready PCB. It combines the custom PathFinder-style autorouter, exact local routing/repair tools, plane recovery, length/skew tuning, and an interactive HTML viewer.

Validated project examples include a 6-layer Allwinner H3 + DDR3 SBC (85 x 56 mm, TFBGA-347, HDMI Type A, 275 parts; DRC/ERC/parity clean through ECO v5.1) and a dense 4-layer MSLA resin-printer controller (STM32F407 + Spartan-6 + 2x SSD2828) using KAT v4.4.

## KAT toolkit v4.4

If the project includes KAT (`kat/`, `tools/`, `AGENTS.md`, `CHANGELOG.md`), read its `AGENTS.md` and newest changelog first, run `tests/smoke.sh`, and use its tools rather than rewriting them. Key tools include:

- Router and finish loop: `ncroute_msla.py`, `close.sh`
- Plane repair: `plane_repair.py`, `plane_via.py`, `gnd_islands.py`, `prune_islands.py`
- Plane-layer escalation and slot bridging: `escalate.sh`, `esc_layer.py`, `cfg_escalate.py`, `slot_bridge.py`
- Placement: `cluster_place.py`, `cluster_flow.sh`
- Review/reporting: `oracle.py`, `gate.py`

When improving a toolkit tool, update CHANGELOG (new/fixed/results/lessons), README, AGENTS.md and smoke tests, then provide the zipped toolkit.

## When to use

- User requests PCB design/routing, not only schematic generation.
- Board complexity includes BGAs, dense connectors, split planes, differential pairs or tight escapes.
- User needs incremental visual review or a manufacturer-ready release.
- For full reviews, proceed stage by stage and never present a pre-design as final.

## Workflow

1. **Schematic validation:** run `kicad-cli sch erc` until clean, then export the netlist.
2. **Placement:** use `stage1.py`/pcbnew for outline, holes, keepouts, block placement and courtyard checks. Reserve escape corridors before placing small parts. Check signal order along chains and connector mating direction, not just footprint position. Place buck converters as functional units with close input caps, short SW nodes and correct orientation.
3. **Fan-out and planes:** use `stage2.py` for BGA dog-bones, power-plane necks, decoupling vias and keepouts. Lock fan-out vias/stubs that must survive rip-up. Use via-in-pad where fine-pitch connector rows cannot escape. Filter paste-only QFN sub-pads from obstacle geometry.
4. **Negotiated-congestion routing:** use one routing object per net or differential pair, legality derived from all existing copper and footprint rule areas, and PathFinder rip-up/history pressure until conflicts reach zero or plateau. Configure layers, grid, clearances, widths, layer/via costs, keepouts and plane nets per board. Route in net groups using `NETRX`; save between stages. Report failed and dropped nets separately. Budget for late improvements; `STAG` counts iterations since the last best score.
5. **DRC loop:** refill a copy with the correct `.kicad_pro` and `.kicad_dru`, then run `kicad-cli pcb drc --format json --severity-all`. Fix shorts, clearance, unconnected, crossing, forbidden items, diff-pair and dangling issues in that order.
6. **Local exact routing/repair:** for dense single connections use `astar1.py`; nudge vias with `movevia.py`; restore lost fan-outs with `restore_net.py`; place/move parts with `place_free.py`. If source and target lie in disconnected legality-grid components, fix placement rather than router parameters.
7. **Length/skew:** remove old meanders before tuning. Match each DDR byte lane to its DQS, match DQS/CK pairs first, grow the lagging pair leg first, and tune address/command to CK. Use windowed accordions that account for the net's own copper. Report mismatch in mm and ps; compute differential impedance with a field solver.
8. **Interactive HTML viewer:** publish per-stage footprints, pads, tracks, vias, zone fills and nets in a self-contained viewer with layer/via toggles, net/part search, stage picker, stackup and localized notes. Derive the next viewer version from the prior one and keep the published artifact URL stable.
9. **Deliver the actual KiCad project**, not only renders, together with fabrication outputs and review records.

## Full design review

Before ordering, and whenever requested, run four independent read-only reviews: power; SoC/DDR; peripherals; and physical/fabrication. Give reviewers the netlist, board and reference schematics. Verify every finding against source documents and actual schematic crops before changing anything. Classify findings as blocker/major/minor/false alarm and report verified findings before fixes.

Check especially: un-netted footprint pads; SoC special balls against vendor references; remote-sense fallback paths; reversed diodes; worst-case rail voltage vs absolute maximum; current limits; fuse/TVS ratings; buck input-cap placement and SW routing; GND via density; hand-fitted modules with paste; fiducials; BOM supplier numbers; silk on pads; and clocks crossing plane slots. Preserve the user's architecture and ask before structural changes.

## Cluster placement

`cluster_place.py` groups small parts using signal nets only (exclude GND and rails), moves groups rigidly and preserves channels. It uses exact KiCad geometry and legality checks, removes stale copper for moved parts, and re-places plane vias afterward. It can help in dense small-part areas but may not improve space around large ICs or buses; compare before adopting.

## ECO on a routed board

- Change the schematic generator, never hand-edit the schematic. Preserve references; removed references remain consumed and new parts use explicit free references.
- Verify generator determinism for symbol UUIDs/references. Diff old/new netlists (values, footprints, pin-to-net) before applying an ECO.
- Apply changes in place, add new parts off-board, assign pad nets, remove copper for vanished nets, place with `place_free.py`, and connect with `astar1.py` or the router.
- For a flipped 2-pin part, rotate the footprint 180° in place. For moved parts, remove affected old-pad copper and foreign items/keepouts at the new location, rip topology-changing nets, then reroute.
- For connector swaps, scan candidate positions with hard courtyard/edge/pad checks, minimize affected foreign nets, preserve MCU escape stubs, reroute only the remainder, and verify parity.
- After zone-outline edits, re-check unconnected items; a wider feed can sever an inner-plane link.

## 4-layer plane escalation

Use only after normal-layer routing leaves a small number of open nets.

1. Route with normal signal layers and keep the GND plane forbidden.
2. Rip only remaining open signal nets and append the plane layer as the final layer index, with a high cost (about 6x). Keep a shield around high-speed copper on adjacent layers; inherit named rule areas except explicitly allowed crossing corridors; deny power, MIPI, USB, clocks and crystal nets from plane routing.
3. Re-route with the plane available and refill zones.
4. Bridge each reference-plane slot with GND vias on both sides and a short outer-layer GND connection, first at crossings/bus ends and then at roughly 5 mm intervals; reuse existing GND vias.
5. Re-tie plane pieces, prune pad-less islands and report plane-layer track length, slot crossings, bus runs and fill-piece counts. Run DRC.

Use `slot_bridge.py` on hand-routed boards too. If re-routing a hand-finished net, rip only that net and try the escalation configuration with `NETRX`; preserve the original route if the tool cannot improve it. Always check that power-plane connectivity was not cut by new copper.

## Planes, pours and connectivity repair

- Identify plane nets from inner-layer zones; other rails are routed signals and must be restored like signals after rip-up.
- Count zone-fill pieces and which contain pads/vias after every change.
- Fix plane connectivity in order: appropriate DRU clearance/min-thickness rules; bridge islands with a connectivity-cluster linker/plane repair; then reroute cutting nets with high plane-layer cost.
- `plane_via.py` adds checked vias to filled zones for orphan plane pads. Clean dangling copper first.
- Test via/bridge placement against the filled zone grown by about 0.25 mm, not the eroded fill.
- Every copper-adding tool must honor custom DRU area rules. Parse rules individually; do not use a regex spanning multiple rules.
- Dangling cleanup must match net, layer, length and reported endpoint exactly. Re-run DRC and connectivity after cleanup.
- For outer GND pours, use suitable RF keep-away, remove islands, stitch only where both pours exist, and check hole-to-hole clearance.

## Tooling pitfalls

- Copy `.kicad_pro` and `.kicad_dru` next to every intermediate board before zone refill/DRC; DRC evaluates saved fills.
- One malformed DRU rule can silently drop all custom rules.
- Do not compare pcbnew SWIG proxies with `is` or `in`; compare stable identifiers/positions. Read objects before mutation; wrappers may become stale after `Remove()`.
- A second `LoadBoard` in one process may produce broken SWIG objects; transfer copper via JSON between processes.
- `GetSize()` is pre-rotation; use `GetBoundingBox()` for geometry.
- Load footprint-owned rule areas in every custom tool.
- Rip-up can remove unlocked fan-out vias; verify every BGA/connector escape after ripping.
- Run long jobs in the background with logs and a completion marker; never kill a router mid-negotiation. Run one router at a time; full-board grids need several GB. Shove is best late, with few conflicts.
- Copy symbol MPN/LCSC fields to footprints (hidden/Fab) before parity checking.
- Deliver each intermediate board as a complete KiCad project folder with schematic sheets, libraries/lib tables and project/rule files.

## Manufacturer-ready release checklist

1. Merge board project rules with schematic ERC settings; use consistent project names.
2. Run `kicad-cli pcb drc --schematic-parity` to 0 errors, 0 unconnected and parity 0.
3. Include the real stackup and field-solver impedance table.
4. Generate grouped BOM, supplier-number BOM and CPL; verify MPN/LCSC, stock, package and voltage. Exclude hand-fitted modules, test pads, holes and fiducials.
5. Add three fiducials per side with correct board-only/BOM/position attributes.
6. Place silk references away from pads, outlines, text and edges; hide those that cannot fit and inspect silk DRC.
7. Export Gerber X2, Excellon PTH/NPTH and maps, positions/CPL, schematic PDF, ERC/DRC reports and renders. Inspect the mirrored bottom view.
8. Run a second-opinion PCB/schematic review (e.g. `eda_toolkit`), verify findings and record waivers in `fab/review/WAIVERS.md`.
9. Package `kicad/`, `fab/` (including review), `docs/` (viewer/renders/length data), `tools/` and a README with changes and verification notes; zip the release.
10. Include fab notes for impedance, finish, via-in-pad filling/capping, min track/space/via, assembly sides, rotation/DFM, low-stock parts, THT assembly and panel rails.

## Reporting

Report each stage in the user's language. Distinguish unrouted, dropped and DRC issues; state length mismatch in mm/ps and trade-offs such as plane-layer signal length or unbridged slots. DRC-clean does not prove a board is electrically or mechanically correct. Separate cosmetic leftovers from real risks and list physical checks still required (connector/detect polarity, module pad handedness against a 1:1 print).
