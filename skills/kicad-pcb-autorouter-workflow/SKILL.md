---
name: "kicad-pcb-autorouter-workflow"
description: "Use when designing or routing a custom PCB in KiCad end-to-end: multi-stage placement, a negotiated-congestion autorouter, plane/DRC repair, length and pair-skew tuning, an interactive HTML layer viewer, and a manufacturer-ready release package."
---

# KiCad PCB design + autorouting + interactive viewer workflow

A repeatable process for taking a KiCad schematic to a routed, DRC-clean, manufacturer-ready PCB with a custom
negotiated-congestion (PathFinder-style) router, then packaging it as a real KiCad project, fab outputs and an
interactive HTML viewer the user can review without opening KiCad. Proven on a 6-layer Allwinner H3 + DDR3 SBC
(85 x 56 mm, TFBGA-347 at 0.65 mm, micro-HDMI at 0.4 mm, 281 parts, DRC 0 / ERC 0 / parity 0).

## When to use

- The user wants a custom PCB designed/routed (not just a schematic) in KiCad.
- The board is too complex for KiCad's built-in tools (BGAs, HDI stacks, split planes, diff pairs, tight escapes).
- The user wants to review progress visually (per layer, with vias shown) across incremental stages.
- The user asks for a final, manufacturer-ready design: go stage by stage, report every stage, never present a
  pre-design as final.

## Overall pipeline

1. **Schematic first.** Run `kicad-cli sch erc` until 0 violations, then `kicad-cli sch export netlist`.
2. **Placement** (`stage1.py` with the `pcbnew` API): outline, holes, keepouts, per-block placement, courtyard checks;
   iterate until a placement-overlap checker reports clean.
   - In a centroid placer give power/GND nets weight 0 for parts that have any signal net, otherwise GND pulls parts
     tens of mm away. Anchor power-only parts (decaps) to their IC's pins on the same sheet.
   - Reserve escape corridors as keepouts BEFORE placing small parts (BGA side bands, the HDMI corridor, the DDR
     channel, connector via fields).
   - Check signal ORDER along each chain before routing (SoC balls -> ESD / flow-through part -> connector pins).
     A flow-through ESD array rotated the wrong way forces every pair to cross; rotating it 180 deg made an
     H3 -> ESD -> micro-HDMI path planar and cut lengths from 13-18 mm to 9-12 mm.
   - Check RF chain pad order and that power-trace widths fit the part's pin pitch.
3. **Fan-out / planes / decaps** (`stage2.py`): BGA dog-bone vias, split power-plane zones with wide necks out of the
   ball field (no router vias on the necks), decaps with a via in or at every pad, keepouts protecting escape
   corridors and buck switch-node islands. Lock every fan-out via and stub you want to keep (rip scripts remove all
   unlocked copper of a net). Fine-pitch connector rear rows that cannot escape get via-in-pad (IPC-4761 VII).
4. **Autoroute with a negotiated-congestion router** (`ncroute.py`): one routing object per net or diff pair, a
   static legality field (`slack.Field`) from ALL existing copper, PathFinder rip-up (present x history pressure)
   until conflicts reach 0 or plateau. Knobs live in a per-board `cfg_*.py`: layers, grid origin/resolution,
   net-class clearances, per-net width and layer cost, pair handling, via cost, keepouts, plane nets. Variant configs
   are cheap (`from cfg_x import *`, override one function: e.g. a high cost on the power layer for some nets, or a
   final pass that routes only plane nets).
   - Route in stages by net group (plane stubs, DDR, then everything else) with a net-name regex env var, saving
     `_ncstate.pkl` between stages.
   - Pairs: prefer a 'fat pair' centreline split into P/N with exact geometric validation, falling back to two
     single nets; never leave a partially drawn illegal pair. If coupled routing keeps conflicting in a tight
     corridor, route uncoupled and trim skew afterwards (step 7).
   - At the end, drop (fully un-write) any net still touching a conflicting cell; a DRC-clean board with N missing
     nets beats one with shorts. Log `failed` (never routed) and `dropped` (removed for conflicts) separately.
   - Run long jobs in restart-safe chunks (LOAD state, `.done` markers, a lock file): containers restart.
5. **DRC loop.** `kicad-cli pcb drc --format json --severity-all` after every significant change. Fix in order:
   shorts > clearance > unconnected > tracks_crossing > diff_pair_* > dangling. For a local problem, delete just
   that copper and re-route only that net with the net filter.
6. **Topologically stuck nets.** Diagnose with an isolated single-net run and a connected-component check of the
   router's legality grid (`scipy.ndimage.label`). Source and target in different components = a placement fix
   (move the part out of the dense field), not a router tweak.
7. **Length and skew.**
   - After DDR tuning check intra-pair skew of every pair (DQS, CK), not just lane matching. A tuner can grow one
     leg (a CK_P accordion) where the other has no room, leaving 9 mm P/N skew. Fix: straighten the grown leg,
     shift it to open a channel, meander the short leg into it.
   - Trim uncoupled pairs (HDMI, USB, ETH) with accordion meanders on the shorter line against an exact clearance
     field.
   - Compute Zdiff of loosely coupled pairs at their real gaps with a 2-D field solver. If it is within spec (HDMI
     100 ohm +-15%), relax the DRU diff_pair_gap rule with a comment saying why, instead of shipping dozens of
     unexplained warnings.
   - Report remaining DDR mismatch in mm and ps (~6-7 ps/mm) with a safe starting DRAM clock.
8. **One retry pass helps; chained retries hurt.** One `LOAD=1` continuation at higher pressure after convergence
   recovers a few nets; repeated passes rip good nets (especially pairs). Never SIGTERM a router mid-negotiation:
   its restore-best-state step runs only at a controlled stop. Size `STAG` and `MAXIT` up front from where the
   conflict count actually plateaus.
9. **Interactive HTML viewer.** Export per-stage JSON (footprints, pads, tracks, vias, zone fills, nets) into one
   self-contained page: canvas renderer, per-layer toggles with a colour per layer, via toggle, net/part search and
   highlight, stage picker, placement table, a stackup/impedance tab, notes per stage. Take the ratsnest from DRC
   `unconnected_items`, not from pad clusters (see pitfalls). Publish as an Artifact and re-publish to the same
   URL as stages complete.
10. **Deliver the real project, not just images.** Ship the routed board with its matching `.kicad_pro`/`.kicad_dru`
    in the schematic project folder (release checklist below), zipped. A user who says they will redraw it from the
    images almost always wants the real, already-routed file.

## Planes, pours and connectivity repair

- After every change count fill pieces per zone and which pieces hold vias or pads. Slow signals on a power layer
  slice it into strips; a 0.65 mm fan-out via lattice blocks the fill when pitch - via - 2 x clearance is below the
  zone's min width.
- Fix order: (1) a DRU rule giving that plane zone 0.10 mm clearance only where the other item intersects the BGA
  rule area, plus zone clearance and min thickness 0.10, so the web flows between vias; (2) bridge leftover islands
  with a cluster linker: clusters = union-find over KiCad item connectivity plus via / pad-in-fill tests per fill
  piece; grid Dijkstra (0.025 mm) over the signal layers from the stranded cluster's copper (or a via-legal spot
  inside its fill) to the main cluster; vias clear all six layers and every drill; clearance = max(base, foreign
  item's own, BGA rule inside the ball field); (3) only then reroute the cutting nets with a high plane-layer cost.
- A ball with no dogbone: add the via at the standard diagonal site and check the plane finger reaches it.
- A stranded 2-pin part (e.g. a 0 ohm star tie): brute-force a new position near the target cluster (pads clear, a
  short straight stub, a ground via within ~0.9 mm) instead of routing across a dense field.
- Outer GND pours (IcePi style): 0.25 mm clearance, 0.5 mm keep-away around RF, islands removed, stitching on a
  2.4 mm lattice only where both pours exist, only deep inside power-layer pours (fill.buffer(-0.9)) so necks are
  never cut, and a hole-to-hole check against EVERY drill regardless of net (mounting holes are GND too). Add a DRU
  rule `(constraint min_resolved_spokes 1)` for GND pours when every GND pad also has its own via or track.
- Clean dangling vias/tracks from DRC positions, iterate to 0, then re-check unconnected.

## Tooling pitfalls

- **Copy `.kicad_pro` + `.kicad_dru` next to EVERY intermediate board** before `LoadBoard` + `ZONE_FILLER`. Without
  them fills use default rules and silently fragment; `kicad-cli pcb drc` checks the SAVED fills (no refill by
  default), so the damage appears later as unconnected items.
- **One bad DRU rule drops ALL custom rules silently.** Symptom: clearance errors jump to hundreds while diff-pair
  warnings vanish. `min_resolved_spokes` takes a bare number: `(constraint min_resolved_spokes 1)`.
- `CONNECTIVITY_DATA.GetConnectedItems(item)` returns direct neighbours (plus whole ZONE objects), not the transitive
  cluster: build clusters with union-find and never derive a ratsnest from it.
- After `board.Remove()` plus a second `LoadBoard()` in one process, SWIG wrappers can degrade to bare
  `SwigPyObject`s. Collect targets first, remove at the end, and split edit / analysis into separate processes.
- Rip scripts remove every unlocked item of a net, including fan-out or via-in-pad vias never locked; after a rip,
  confirm each connector pin still has its escape.
- Re-add tracks at the exact endpoints of the removed copper (52.975, not 52.98) or length graphs break.
- Never `pkill -f` / `ps | grep pattern | kill` with a pattern that also matches your own shell; use `name[x]`.
- In `kicad-cli sch export bom`, `${QUANTITY}` inside single quotes needs no backslash.

## Release checklist (manufacturer-ready)

1. Merge the board `.kicad_pro` (net classes, rules) with the schematic project's ERC section and name board, pro and
   dru after the schematic project, so one `.kicad_pro` opens schematic and routed board together.
2. `kicad-cli pcb drc --schematic-parity` until 0: fix DNP / exclude-from-BOM mismatches and copy missing symbol
   fields (MPN, notes) to footprints.
3. Write the real stackup into the board (e.g. JLC06161H-1080B) and build an impedance table from the field solver.
4. Export Gerber X2 with an explicit layer list, Excellon PTH/NPTH + maps, positions (exclude DNP) and an assembler
   CPL, a grouped BOM with quantities, schematic PDF, ERC/DRC reports, top/bottom renders.
5. Package `kicad/`, `fab/`, `docs/` (viewer, renders, length data), `tools/` (scripts) and a README; zip it.
6. Fab notes: impedance control, ENIG for fine-pitch BGA, via covering epoxy filled + capped for via-in-pad, min
   track/space and via, double-sided assembly, rotation check in the assembler preview, supplier part numbers.

## Reporting

Report every stage as it completes. When something is not ideal, give a precise breakdown and why: fully unrouted vs.
partially unrouted vs. lingering DRC, length mismatch in mm and ps, and what was traded (e.g. loosely coupled HDMI
with its computed Zdiff). Do not blur `failed` and `dropped`, and do not call a board done because DRC is clean:
clean DRC with missing nets or untuned pairs is not finished. Separate cosmetic leftovers (silk overlap, stale
schematic notes) from real risks (DDR timing, no SI/PI simulation, no 3D models for the enclosure check).