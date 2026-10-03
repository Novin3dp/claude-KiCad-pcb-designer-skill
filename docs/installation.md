# Installation

## Install the skills

Claude Code loads skills from `~/.claude/skills/<name>/SKILL.md` (personal) or `<project>/.claude/skills/<name>/SKILL.md` (per project).

```bash
git clone https://github.com/Novin3dp/claude-KiCad-pcb-designer-skill.git
cd claude-KiCad-pcb-designer-skill
./scripts/install.sh              # -> ~/.claude/skills
./scripts/install.sh --project    # -> ./.claude/skills (run from your project root)
```

The script replaces any previously installed copy of the same skill. To build `.skill` archives (zip files with `<skill-name>/SKILL.md` inside) run `./scripts/package.sh`; the output goes to `dist/`.

Start a new Claude Code session afterwards so the skills are listed.

## KiCad setup (Ubuntu 24.04)

Install the **same KiCad major version you use** (ask yourself which one if unsure). The generator embeds symbols copied from the installed library, so the output matches that version.

- Files built with KiCad 10 libraries can contain tokens KiCad 9 cannot read.
- KiCad 7 from the distribution has no `kicad-cli sch erc`.

```bash
V=10.0   # or 9.0
curl -s "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x245D5502FAD7A805" | gpg --dearmor > /etc/apt/trusted.gpg.d/kicad.gpg
echo "deb https://ppa.launchpadcontent.net/kicad/kicad-$V-releases/ubuntu noble main" > /etc/apt/sources.list.d/kicad.list
apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends kicad kicad-symbols kicad-footprints poppler-utils
mkdir -p ~/.config/kicad/$V && cp /usr/share/kicad/template/{sym,fp}-lib-table ~/.config/kicad/$V/
```

On other systems install KiCad from [kicad.org](https://www.kicad.org/download/) and make sure `kicad-cli`, the symbol library directory and `pdftotext`/`pdftoppm` are available. If the symbol libraries are not in `/usr/share/kicad/symbols`, set `KICAD_SYMBOL_DIR`.

## Environment variables read by `kigen`

| Variable | Default | Meaning |
|---|---|---|
| `KICAD_SYMBOL_DIR` | `/usr/share/kicad/symbols` | Where stock `.kicad_sym` libraries live. |
| `KIGEN_PROJECT` | `project` | Default project name. |
| `KIGEN_COMPANY` | empty | Company field in the title block. |
| `KIGEN_DATE` | empty | Date field in the title block. |

## Checking your install

```bash
python3 -m py_compile skills/kicad-schematic-generator/gen/*.py
python3 examples/minimal-board/build.py
kicad-cli sch erc -o /tmp/erc.rpt --severity-all examples/minimal-board/kicad/minimal.kicad_sch
```

The example's ERC result has not been checked in this repository's CI; treat the last command as your own smoke test.
