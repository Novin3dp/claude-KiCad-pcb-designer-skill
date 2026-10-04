# Claude Code KiCad PCB Design Automation

**Claude Code KiCad PCB Designer Skill** is an open-source **AI-agent-ready PCB design system for KiCad**. It combines Agent Skills with a runnable Python/C toolkit (KAT). The Skills provide the engineering workflow; KAT provides executable KiCad automation and routing/repair primitives. Therefore the code can be driven by Claude Code or by another AI agent that can execute Python/shell commands and manipulate project files.

Repository: https://github.com/Novin3dp/claude-KiCad-pcb-designer-skill

## What problem does it solve?

Designing a PCB with an AI coding agent is not only about generating KiCad files. A useful workflow must preserve electrical connectivity, respect component and board constraints, verify the result, and produce outputs that can be reviewed and manufactured.

This project turns Claude Code into a structured KiCad PCB design assistant with explicit verification stages.

## Main capabilities

### KiCad schematic generation

The `kicad-schematic-generator` skill can generate complete KiCad 9/10 schematic projects from Python and verify them using KiCad tooling.

The workflow covers:

- hierarchical schematic generation
- custom and multi-unit symbols
- BGA symbols and footprints
- net connectivity
- ERC verification
- netlist/parity checks
- PDF review

### KiCad PCB routing and automation

The `kicad-pcb-autorouter-workflow` skill covers an end-to-end PCB layout workflow:

- component placement
- BGA fan-out
- power planes and decoupling
- differential pair routing
- negotiated-congestion autorouting
- DRC repair
- trace-length matching
- pair-skew tuning
- design review
- manufacturing release

## The executable toolkit

The [`toolkit/`](../toolkit/README.md) directory contains the source code used to perform the PCB operations. Important components include:

- `kat/ncroute.py` — negotiated-congestion autorouter with a compiled C core.
- `kat/astar1.py` — exact local connection routing for dense areas.
- `kat/movevia.py` and `kat/place_free.py` — geometry/placement repair.
- `kat/plane_via.py`, `kat/cluster_link.py`, `kat/gnd_pour.py` — plane and copper repair.
- `kat/pair_skew.py` and `kat/ddr_tune.py` — high-speed length/skew tuning.
- `kat/eco.py` — apply schematic/netlist changes to a routed board.
- `kat/drc.sh` — refill + KiCad DRC workflow.
- `kat/make_viewer.py`, `layerplot.py`, `netplot.py` — machine-friendly visual review outputs.
- `schematic/kigen.py` and `netcheck.py` — Python schematic generation and connectivity checks.

An AI agent can orchestrate these tools stage by stage. The toolkit uses KiCad's own `pcbnew` API rather than asking the model to hand-edit raw PCB geometry.

## Verification-first PCB design

The workflow is designed around machine-verifiable engineering checkpoints instead of treating AI-generated geometry as automatically correct.

Typical pipeline:

```text
Requirements
    ↓
KiCad schematic
    ↓
ERC + netlist verification
    ↓
PCB placement
    ↓
BGA fan-out
    ↓
Power / planes / decoupling
    ↓
PCB routing
    ↓
DRC repair
    ↓
Length / skew tuning
    ↓
Independent design review
    ↓
ECO
    ↓
Gerber / BOM / CPL manufacturing release
```

## Technologies

This project is relevant to users searching for:

- Claude Code PCB design
- Claude Code KiCad
- Claude Code hardware design
- AI PCB design
- AI PCB layout
- AI EDA agent
- KiCad AI automation
- KiCad PCB automation
- KiCad schematic generator
- KiCad PCB autorouter
- KiCad routing automation
- KiCad ERC DRC automation
- kicad-cli automation
- pcbnew Python automation
- BGA PCB routing
- DDR3 PCB design
- DDR3 length matching
- differential pair routing
- Gerber manufacturing release
- Claude Code skills for electronics

## Installation

Clone the repository and install the skills into Claude Code:

```bash
git clone https://github.com/Novin3dp/claude-KiCad-pcb-designer-skill.git
cd claude-KiCad-pcb-designer-skill
./scripts/install.sh
```

The repository contains two focused skills:

```text
skills/
├── kicad-schematic-generator/
└── kicad-pcb-autorouter-workflow/
```

See the [installation guide](installation.md) for prerequisites and details.

## Documentation

- [Installation](installation.md)
- [KiCad schematic generator](schematic-generator.md)
- [KiCad PCB autorouter workflow](pcb-autorouter-workflow.md)
- [Repository metadata and discovery](repository-metadata.md)

## Example hardware workflow

The repository documents a reproducible workflow for a complex embedded board, including BGA fan-out, DDR3-related routing constraints, multi-layer PCB layout, ERC/DRC verification, ECO iterations, and manufacturing release.

The goal is not to claim that an AI agent can replace an experienced PCB engineer. The goal is to make AI-assisted KiCad work more structured, reproducible, inspectable, and easier to verify.

## License

MIT License.