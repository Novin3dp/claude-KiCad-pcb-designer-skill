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
- Run long jobs in restart-safe chunks (state files, `.done` markers, a lock file) because containers restart.
- One retry pass at higher pressure can recover a few nets; chained retries rip good nets. Never SIGTERM a router mid-negotiation.

## DRC repair order

shorts, clearance, unconnected, tracks_crossing, diff_pair_*, dangling. Delete only the offending copper and reroute that net with the net filter.

## Stuck nets

Run a single-net isolated route and label connected components of the legality grid (`scipy.ndimage.label`). If source and target land in different components, the fix is a placement change (move the part out of the dense field), not a router tweak.

## Length and skew

- Check intra-pair skew for every pair (DQS, CK), not just lane matching.
- Trim uncoupled pairs (HDMI, USB, ETH) with accordion meanders on the shorter line.
- Compute Zdiff at the real gaps with a 2-D field solver; if within spec (for example HDMI 100 ohm +-15%), relax the `diff_pair_gap` DRU rule and comment why.
- Report DDR mismatch in mm and ps (about 6-7 ps/mm) with a safe starting DRAM clock.

## Planes and pours

See the "Planes, pours and connectivity repair" section of the skill: DRU rules for web flow between fan-out vias, cluster linking of stranded islands, GND pours with stitching, and `(constraint min_resolved_spokes 1)` for GND pours.

## Tooling pitfalls

- Copy `.kicad_pro` and `.kicad_dru` next to **every** intermediate board before `LoadBoard` + `ZONE_FILLER`; `kicad-cli pcb drc` checks the saved fills.
- One bad DRU rule drops all custom rules silently (symptom: clearance errors jump to hundreds while diff-pair warnings vanish).
- `CONNECTIVITY_DATA.GetConnectedItems()` returns direct neighbours, not the transitive cluster; use union-find.
- After `board.Remove()` plus a second `LoadBoard()` in one process, SWIG wrappers can degrade; split edit and analysis into separate processes.
- Rip scripts remove every unlocked item of a net, including unlocked fan-out vias.
- Re-add tracks at the exact endpoints of removed copper, or length graphs break.
- Never `pkill -f` with a pattern that also matches your own shell; use the `name[x]` trick.

## Release checklist

1. Merge the board `.kicad_pro` with the schematic project's ERC section; name board, pro and dru after the schematic project.
2. `kicad-cli pcb drc --schematic-parity` to 0.
3. Write the real stackup (for example JLC06161H-1080B) and build an impedance table from the field solver.
4. Export Gerber X2, Excellon PTH/NPTH and maps, positions (excluding DNP), an assembler CPL, a grouped BOM, schematic PDF, ERC/DRC reports and renders.
5. Package `kicad/`, `fab/`, `docs/`, `tools/` and a README; zip it.
6. Fab notes: impedance control, ENIG for fine-pitch BGA, epoxy-filled and capped vias for via-in-pad, minimum track/space/via, double-sided assembly, rotation check in the assembler preview, supplier part numbers.

## Reporting

Report each stage. When something is not ideal, give the exact breakdown: fully unrouted vs. partially unrouted vs. lingering DRC, length mismatch in mm and ps, and what was traded off. Separate cosmetic leftovers from real risks.
