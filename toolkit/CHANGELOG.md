# KAT Changelog

## v4.4 — 2026-11-02

This release was developed from the MSLA_SHARP04 four-layer board's final connectivity-repair work.

### New workflows
- **Plane layer as last resort:** route on normal signal layers first, then permit only remaining open signal nets onto a designated plane layer. Preserve inherited keep-outs, shield high-speed copper, refill zones, bridge plane slots, repair islands, and inspect the escalation report.
- **Slot bridging:** restore plane continuity around signal tracks that cut a plane by adding paired plane vias and a short bridge on another copper layer. Prefer bridges at signal/bus crossings, then add pitch-based bridges where needed.
- **Transactional push-and-shove routing:** `ncroute_msla.py` can reroute colliding nets as a bounded transaction during negotiated-congestion routing. Use late, with a small conflict set; each pass can take many minutes.
- **Signal-cluster placement:** group signal-connected parts, compact them, move rigid groups away from congested corridors, remove stale copper selectively, and pass the result through plane-via insertion, routing, closure and DRC.

### New and supporting tools
`escalate.sh`, `cfg_escalate.py`, `esc_layer.py`, `slot_bridge.py`, `ncroute_msla.py`, `cluster_place.py`, `cluster_flow.sh`, `plane_repair.py`, `oracle.py`, `gate.py`, `review.py`, `place_score.py`, `placer.py`, `relocate.py`, `decap_fix.py`, `stitch.py`, `neckdown.py`, `ipc_width.py`, `net_area.py`, `rip_nets.py`, `rip_window.py`, `snap.py`, `prune.py`, `gnd_islands.py`, and `fat_vias.py`.

### Important limitations and lessons
- Plane-layer escalation is not a general replacement for a continuous return plane. Never allow high-speed copper to cross a plane cut; inspect bus runs along cuts and every bridge.
- Only nets that own a zone on the plane layer are plane nets. Other rails must be routed like signals if their copper is removed.
- A grid router may fail short same-chip links that can be completed manually; do not endlessly repeat expensive routing rounds.
- Cluster placement is most useful among small parts. Around large ICs and buses it may not create enough free space.
- Push-and-shove is expensive on a full board. Enable it late and accept a transaction only when the aggregate conflict score improves.
- Refill zones and run KiCad DRC plus connectivity checks after every accepted change. A clean DRC alone does not prove the board is electrically correct.

## Earlier releases
See the tagged source archive and the detailed v4.4 notes for the preceding v2–v4.3 development history.
