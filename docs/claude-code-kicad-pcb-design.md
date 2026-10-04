# Claude Code KiCad PCB Design Automation

**Claude Code KiCad PCB Designer Skill** is an open-source workflow for AI-assisted PCB design with KiCad. It provides Claude Code skills for generating schematics, designing and routing PCBs, running ERC/DRC verification, tuning high-speed constraints, reviewing designs, and preparing manufacturing outputs.

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