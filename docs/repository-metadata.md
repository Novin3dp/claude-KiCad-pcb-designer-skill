# GitHub repository metadata

GitHub topics and the About description can only be set in the repository UI (or with `gh repo edit`). Use these values so the repository shows up in searches.

## About → Description

```
Claude Code skills for KiCad: generate ERC-clean schematics from Python, then place, autoroute, DRC-check and release manufacturer-ready PCBs.
```

## About → Topics

```
kicad kicad-9 kicad-10 kicad-cli pcb pcb-design pcb-routing autorouter schematic
eda electronics hardware-design python pcbnew drc erc gerber bga ddr3
claude claude-code claude-skills anthropic ai-agent agent-skills
```

Apply with the GitHub CLI:

```bash
gh repo edit Novin3dp/claude-KiCad-pcb-designer-skill \
  --description "Claude Code skills for KiCad: generate ERC-clean schematics from Python, then place, autoroute, DRC-check and release manufacturer-ready PCBs." \
  --add-topic kicad,kicad-9,kicad-10,kicad-cli,pcb,pcb-design,pcb-routing,autorouter,schematic,eda,electronics,hardware-design,python,pcbnew,drc,erc,gerber,bga,ddr3,claude,claude-code,claude-skills,anthropic,ai-agent,agent-skills
```

Or in the browser: repository home page → gear icon next to **About** → paste the description and add the topics.

## Other discoverability settings

- Social preview: Settings → General → Social preview → upload `docs/images/example-board-3d.png`.
- Set the default branch (Settings → Branches) once the work is merged.
- Create a release (for example `v1.0.0`) after merging so the `.skill` archives from `./scripts/package.sh` can be attached.
