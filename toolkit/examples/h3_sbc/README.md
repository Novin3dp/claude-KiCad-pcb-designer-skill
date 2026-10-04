# Reference: the 6-layer Allwinner H3 + DDR3 Klipper SBC

These are the configs and scripts used on the real board (85 x 56 mm, TFBGA-347, DDR3 x16, HDMI, 4 x USB, Ethernet,
Wi-Fi). They are kept as worked examples. The paths inside point at the original project, so read them for the
technique; do not run them as-is.

| File | What it shows |
| --- | --- |
| `cfg_sbc.py`, `cfg_sbc_final.py` | Router config for a 6-layer BGA board: 0.05 mm grid aligned with the ball gaps, net-class clearances, DDR lane / address length bounds, HDMI / USB pairs, RF net on L1 only, keepouts protecting split-plane necks, a BGA relief rule area. |
| `sbc_ddr.py` | DDR length profile (layer depths for via barrels, pass-through pads). It is the same as `kat/ddr_profile.py`. |
| `v5_move.py`, `v5_vias.py`, `v5_zone5v.py`, `v51_vbus_zone.py` | ECO steps of a full-review release: re-placing a buck block and turning a microSD socket, adding EP / stitching / GND vias, widening a feed in a split plane, a VBUS pour into USB-C pads. |
| `drc5.sh`, `release_v5.sh` | Board DRC wrapper and the complete release script (merged project, ERC, DRC + parity, Gerber X2, drill, CPL, BOM with LCSC numbers, JLC BOM, PDF, renders, kicad_skills review). |
| `viewer.py`, `sbc_viewer_v51.py` | The multi-stage viewer with block overlays, signal flows and Persian notes (the generic version is `kat/make_viewer.py`). |
| `gen/` | The schematic generators: `build_sbc.py` (10 sheets, assembled from two older generators, with ECO-safe reference handling and MPN / LCSC field injection), `symbols.py` (custom H3 / DDR3 / regulator symbols), `gen_fp.py` (BGA footprint from a ball map). |
