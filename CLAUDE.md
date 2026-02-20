# Signal Hub

Combined daily digest: **Pure Signal** (frontier AI intelligence) + **Maranello Signal** (Ferrari F1 intelligence). Both pipelines run on one schedule and publish a single Cloudflare Pages site.

## Project structure

```
src/
  main.py                        # Orchestrator — runs both pipelines, builds & deploys
  site_builder.py                # Combined static site builder
  deployer.py                    # Cloudflare Pages deployment via wrangler
  pure_signal/
    pipeline.py                  # Fetch + synthesize AI content → markdown string
    synthesizer.py               # Claude API synthesis (TTS-optimised narrative)
    dedup.py                     # JSON-backed dedup store
    fetchers/
      rss_fetcher.py             # RSS/Atom parsing (ContentItem dataclass)
      web_fetcher.py             # DuckDuckGo news search
  maranello/
    pipeline.py                  # Poll Ferrari RSS + Claude analysis → {briefing, source_links}
config/
  config.yaml                    # People, sources, synthesis settings, Cloudflare config
  credentials.yaml               # API keys (gitignored — copy from .template)
  credentials.yaml.template      # Template for credentials.yaml
data/
  pure_signal_processed.json     # Pure Signal dedup store (gitignored)
  maranello_seen.db              # Maranello SQLite dedup (gitignored)
  archive/                       # YYYY-MM-DD.json combined archive (gitignored)
site/                            # Built static site (gitignored, deployed via wrangler)
logs/
  signal_hub.log
signal-hub.service               # systemd oneshot service
signal-hub.timer                 # systemd timer — 6 AM ET daily
run.sh                           # Bash wrapper (activates venv)
```

## How it works

1. **Pure Signal pipeline** (`src/pure_signal/pipeline.py`)
   - Polls RSS feeds + DuckDuckGo web search for 17 frontier AI researchers
   - Deduplicates against `data/pure_signal_processed.json`
   - Sends new items to Claude for a TTS-optimised narrative digest
   - Returns markdown string (or `""` if nothing new)

2. **Maranello pipeline** (`src/maranello/pipeline.py`)
   - Polls 4 Ferrari F1 RSS feeds (Italian + English)
   - Deduplicates against `data/maranello_seen.db` (SQLite)
   - Sends items to Claude for Ferrari filtering + podcast-style narrative
   - Returns `{"briefing": "...", "source_links": [...]}`

3. **Site builder** (`src/site_builder.py`)
   - Saves combined output to `data/archive/YYYY-MM-DD.json`
   - Rebuilds static site from all archive files
   - Each daily page has two visually distinct sections (indigo = AI, red = Ferrari)

4. **Deploy** — `wrangler pages deploy site/ --project-name signal-hub`

## Setup

```bash
cd /home/mithrandir/claude/Signal_Hub

# Create venv and install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up credentials
cp config/credentials.yaml.template config/credentials.yaml
# Edit config/credentials.yaml with your Anthropic key + Cloudflare token

# Create Cloudflare Pages project (first time only)
wrangler pages project create signal-hub

# Test run (no deploy)
python -m src.main --dry-run

# Full run
python -m src.main
```

## Scheduling (systemd)

```bash
# Install timer (user-level)
mkdir -p ~/.config/systemd/user
cp signal-hub.service signal-hub.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now signal-hub.timer

# Check status
systemctl --user status signal-hub.timer
journalctl --user -u signal-hub.service -n 50
```

## Run modes

```bash
python -m src.main              # Full pipeline + deploy
python -m src.main --dry-run    # Build site, skip deploy
python -m src.main --no-deploy  # Same as --dry-run
python -m src.main --verbose    # Debug logging
./run.sh                        # Same as python -m src.main (used by systemd)
```

## Configuration

- **Add a Pure Signal source**: Add entry to `people:` block in `config/config.yaml`
- **Add a Ferrari feed**: Edit `FEEDS` list in `src/maranello/pipeline.py`
- **Change model**: Edit `synthesis.model` in `config/config.yaml`
- **Change schedule**: Edit `OnCalendar` in `signal-hub.timer`
- **Reset Pure Signal dedup**: `rm data/pure_signal_processed.json`
- **Reset Maranello dedup**: `rm data/maranello_seen.db`

## Cloudflare

- **Account ID**: `4a55b445f11c7fcf37342301937f8d2c`
- **Project name**: `signal-hub` (create with `wrangler pages project create signal-hub`)
- **Live site**: `https://signal-hub.pages.dev` (after first deploy)

## Key technical details

- Both pipelines share the same Claude model (configured once in `config.yaml`)
- Pure Signal dedup: JSON file (persistent across runs)
- Maranello dedup: SQLite (persistent across runs)
- Timezone: All date calculations use `America/New_York`
- If one pipeline returns empty, the other's content still publishes
- If both are empty, nothing is published
