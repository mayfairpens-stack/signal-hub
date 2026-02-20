"""
Combined static site builder for Signal Hub.

Builds a site where each daily page shows two sections:
  - Pure Signal  — AI/tech researcher intelligence (markdown)
  - Maranello Signal — Ferrari F1 briefing (plain text + source links)

Archive format:  data/archive/YYYY-MM-DD.json
Site output:
  site/index.html          — latest combined digest
  site/archive/index.html  — archive listing
  site/archive/YYYY-MM-DD.html — individual day pages
  site/style.css
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SiteBuilder:
    """Builds the combined Signal Hub static site."""

    def __init__(self, site_dir: str, archive_dir: str):
        self.site_dir = Path(site_dir)
        self.archive_dir = Path(archive_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_combined_archive(
        self,
        date_str: str,
        pure_signal_md: str,
        maranello: dict,
    ) -> None:
        """
        Save today's combined data to data/archive/YYYY-MM-DD.json.

        Args:
            date_str:       "YYYY-MM-DD"
            pure_signal_md: Markdown digest (may be "" if quiet day)
            maranello:      {"briefing": "...", "source_links": [...]}
        """
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": date_str,
            "pure_signal": pure_signal_md,
            "maranello": maranello,
        }
        out_path = self.archive_dir / f"{date_str}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved combined archive: %s", out_path)

    def build(self) -> None:
        """
        Build (or rebuild) the full static site from the JSON archive.
        Call after save_combined_archive() to publish the latest digest.
        """
        self.site_dir.mkdir(parents=True, exist_ok=True)
        (self.site_dir / "archive").mkdir(parents=True, exist_ok=True)

        entries = self._load_archive()

        if not entries:
            logger.warning("No archive entries found — nothing to build")
            return

        self._write_css()

        for entry in entries:
            self._build_day_page(entry, css_path="../style.css")

        self._build_index(entries[0])
        self._build_archive_index(entries)

        logger.info("Site built: %d day(s) in archive", len(entries))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_archive(self) -> list[dict]:
        """Load all archive JSON files, sorted newest-first."""
        entries = []
        if not self.archive_dir.exists():
            return entries
        for path in sorted(self.archive_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entries.append(data)
            except Exception as e:
                logger.warning("Failed to read %s: %s", path, e)
        return entries

    def _format_date(self, date_str: str) -> str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
        except ValueError:
            return date_str

    # ------ Markdown → HTML (Pure Signal) ------

    def _md_to_html(self, md: str) -> str:
        html = md
        html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = re.sub(r"^---+\s*$", "<hr>", html, flags=re.MULTILINE)
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = html.replace("—", "&mdash;")
        parts = []
        for p in html.split("\n\n"):
            p = p.strip()
            if not p:
                continue
            if p.startswith(("<h1>", "<h2>", "<h3>", "<hr>")):
                parts.append(p)
            else:
                parts.append(f"<p>{p}</p>")
        return "\n".join(parts)

    # ------ Maranello briefing → HTML ------

    def _maranello_to_html(self, maranello: dict) -> str:
        briefing = maranello.get("briefing", "")
        source_links = maranello.get("source_links", [])

        if not briefing:
            return '<p class="quiet-day">No Ferrari news today.</p>'

        # Escape and paragraph-wrap the briefing text
        escaped = briefing.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        paragraphs = [
            f"<p>{p.strip()}</p>"
            for p in escaped.split("\n\n")
            if p.strip()
        ]
        html = "\n".join(paragraphs)

        if source_links:
            items = "".join(
                f'<li><a href="{lnk["url"]}" target="_blank" rel="noopener">{lnk["title"]}</a></li>'
                for lnk in source_links
            )
            html += f'\n<div class="source-links"><h4>Sources</h4><ul>{items}</ul></div>'

        return html

    # ------ Page assembly ------

    def _day_body(self, entry: dict) -> str:
        date_str = entry.get("date", "")
        date_display = self._format_date(date_str)

        pure_signal_md = entry.get("pure_signal", "")
        maranello = entry.get("maranello", {})

        ps_html = self._md_to_html(pure_signal_md) if pure_signal_md else '<p class="quiet-day">No AI digest today.</p>'
        mar_html = self._maranello_to_html(maranello)

        return f"""    <time>{date_display}</time>

    <section class="section pure-signal-section">
      <h2 class="section-title pure-signal-title">
        <span class="dot ps-dot"></span> Pure Signal
        <span class="section-sub">AI Intelligence</span>
      </h2>
      <div class="section-body">
{ps_html}
      </div>
    </section>

    <section class="section maranello-section">
      <h2 class="section-title maranello-title">
        <span class="dot mar-dot"></span> Maranello Signal
        <span class="section-sub">Ferrari F1</span>
      </h2>
      <div class="section-body">
{mar_html}
      </div>
    </section>"""

    def _html_page(self, title: str, body: str, css_path: str = "style.css") -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
  <nav>
    <a href="/" class="nav-brand">Signal Hub</a>
    <a href="/archive/">Archive</a>
  </nav>
  <main>
{body}
  </main>
</body>
</html>"""

    def _build_index(self, latest_entry: dict) -> None:
        body = self._day_body(latest_entry)
        page = self._html_page("Signal Hub", body)
        (self.site_dir / "index.html").write_text(page, encoding="utf-8")
        logger.info("Built index.html")

    def _build_day_page(self, entry: dict, css_path: str = "../style.css") -> None:
        date_str = entry.get("date", "unknown")
        date_display = self._format_date(date_str)
        body = self._day_body(entry)
        title = f"Signal Hub — {date_display}"
        page = self._html_page(title, body, css_path=css_path)
        (self.site_dir / "archive" / f"{date_str}.html").write_text(page, encoding="utf-8")

    def _build_archive_index(self, entries: list[dict]) -> None:
        items = []
        for entry in entries:
            date_str = entry.get("date", "")
            date_display = self._format_date(date_str)
            has_ps = bool(entry.get("pure_signal", "").strip())
            has_mar = bool(entry.get("maranello", {}).get("briefing", "").strip())
            badges = ""
            if has_ps:
                badges += '<span class="badge ps-badge">AI</span>'
            if has_mar:
                badges += '<span class="badge mar-badge">F1</span>'
            items.append(
                f'    <li>'
                f'<a href="/archive/{date_str}.html">{date_display}</a>'
                f'<span class="badges">{badges}</span>'
                f'</li>'
            )

        list_html = "\n".join(items) if items else "    <li>No digests yet.</li>"
        body = f"    <h1>Archive</h1>\n    <ul class=\"archive-list\">\n{list_html}\n    </ul>"
        page = self._html_page("Signal Hub — Archive", body, css_path="../style.css")
        (self.site_dir / "archive" / "index.html").write_text(page, encoding="utf-8")
        logger.info("Built archive index (%d entries)", len(entries))

    def _write_css(self) -> None:
        css = """\
:root {
  --bg:       #fafaf9;
  --fg:       #1c1917;
  --muted:    #78716c;
  --border:   #e7e5e4;
  --max-w:    720px;

  /* Section accent colours */
  --ps-color:  #4a4a8a;   /* indigo — Pure Signal */
  --mar-color: #DC0000;   /* Ferrari red — Maranello */
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.75;
  color: var(--fg);
  background: var(--bg);
  max-width: var(--max-w);
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

/* ── Nav ─────────────────────────────── */
nav {
  display: flex;
  gap: 1.5rem;
  align-items: baseline;
  margin-bottom: 2.5rem;
  font-size: 0.9rem;
}
.nav-brand {
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.01em;
}
nav a { color: var(--fg); text-decoration: none; }
nav a:hover { text-decoration: underline; }

/* ── Date ────────────────────────────── */
main > time {
  display: block;
  color: var(--muted);
  font-size: 0.85rem;
  margin-bottom: 2rem;
}

/* ── Sections ────────────────────────── */
.section {
  margin-bottom: 3rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding-bottom: 0.5rem;
  margin-bottom: 1.25rem;
  border-bottom: 2px solid var(--border);
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ps-dot  { background: var(--ps-color); }
.mar-dot { background: var(--mar-color); }

.pure-signal-title { color: var(--ps-color); }
.maranello-title   { color: var(--mar-color); }

.section-sub {
  font-weight: 400;
  font-size: 0.8rem;
  color: var(--muted);
  text-transform: none;
  letter-spacing: 0;
  margin-left: 0.25rem;
}

/* ── Content typography ──────────────── */
.section-body p    { margin: 0.9rem 0; }
.section-body h1,
.section-body h2,
.section-body h3   { margin: 1.5rem 0 0.5rem; }
.section-body h2   { font-size: 1.05rem; color: var(--fg); }
.section-body h3   { font-size: 0.95rem; color: var(--muted); font-weight: 600; }
.section-body hr   { border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }
.section-body strong { color: var(--fg); }

.quiet-day {
  color: var(--muted);
  font-style: italic;
}

/* ── Source links (Maranello) ────────── */
.source-links {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}
.source-links h4 {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 0.5rem;
}
.source-links ul { list-style: none; padding: 0; }
.source-links li { padding: 0.2rem 0; }
.source-links a  { color: var(--mar-color); text-decoration: none; font-size: 0.9rem; }
.source-links a:hover { text-decoration: underline; }

/* ── Archive list ────────────────────── */
h1 {
  font-size: 1.4rem;
  margin-bottom: 1.5rem;
  padding-bottom: 0.4rem;
  border-bottom: 2px solid var(--border);
}

.archive-list { list-style: none; padding: 0; }
.archive-list li {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--border);
}
.archive-list a {
  color: var(--fg);
  text-decoration: none;
  font-size: 1rem;
  flex: 1;
}
.archive-list a:hover { text-decoration: underline; }

.badges { display: flex; gap: 0.3rem; }
.badge {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  color: #fff;
}
.ps-badge  { background: var(--ps-color); }
.mar-badge { background: var(--mar-color); }

/* ── Responsive ──────────────────────── */
@media (max-width: 600px) {
  body { padding: 1rem; }
  .section-title { font-size: 0.95rem; }
}
"""
        (self.site_dir / "style.css").write_text(css, encoding="utf-8")
        logger.info("Wrote style.css")
