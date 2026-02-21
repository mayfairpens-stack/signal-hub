#!/usr/bin/env python3
"""
Signal Hub — Combined daily digest orchestrator.

Runs the Pure Signal (AI intelligence) and Maranello Signal (Ferrari F1)
pipelines, merges their output into a single page, and deploys to
Cloudflare Pages.

Usage:
    python -m src.main                # Full run: fetch, synthesize, build, deploy
    python -m src.main --dry-run      # Build site locally, skip deploy
    python -m src.main --no-deploy    # Same as --dry-run
    python -m src.main --verbose      # Enable debug logging
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pure_signal import pipeline as ps_pipeline
from src.maranello import pipeline as mar_pipeline
from src.hn_signal import pipeline as hn_pipeline
from src.site_builder import SiteBuilder
from src.deployer import deploy_site

logger = logging.getLogger(__name__)


def setup_logging(log_file: Path = None, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=handlers,
    )


def load_config() -> dict:
    path = PROJECT_ROOT / "config" / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_credentials() -> dict:
    """Load credentials from env vars (priority) or credentials.yaml."""
    creds = {
        "anthropic": {"api_key": os.environ.get("ANTHROPIC_API_KEY", "")},
        "cloudflare": {"api_token": os.environ.get("CLOUDFLARE_API_TOKEN", "")},
    }
    path = PROJECT_ROOT / "config" / "credentials.yaml"
    if path.exists():
        with open(path) as f:
            file_creds = yaml.safe_load(f) or {}
        for section, values in file_creds.items():
            if section not in creds:
                creds[section] = {}
            for key, value in values.items():
                if not creds[section].get(key):
                    creds[section][key] = value
    return creds


def main() -> int:
    parser = argparse.ArgumentParser(description="Signal Hub — combined daily digest")
    parser.add_argument("--dry-run", action="store_true", help="Build site but skip deploy")
    parser.add_argument("--no-deploy", action="store_true", help="Same as --dry-run")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    config = load_config()
    log_path = PROJECT_ROOT / config.get("paths", {}).get("log_file", "logs/signal_hub.log")
    setup_logging(log_path, args.verbose)

    logger.info("=== Signal Hub — starting daily run ===")

    credentials = load_credentials()
    api_key = credentials.get("anthropic", {}).get("api_key", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — aborting")
        return 1

    paths_cfg = config.get("paths", {})
    ps_dedup_path = PROJECT_ROOT / paths_cfg.get("pure_signal_dedup", "data/pure_signal_processed.json")
    mar_db_path   = PROJECT_ROOT / paths_cfg.get("maranello_seen_db",  "data/maranello_seen.db")
    hn_seen_path  = PROJECT_ROOT / paths_cfg.get("hn_signal_seen",     "data/hn_signal_seen.json")
    archive_dir   = PROJECT_ROOT / paths_cfg.get("archive_dir",        "data/archive")
    site_dir      = PROJECT_ROOT / "site"

    synthesis_cfg = config.get("synthesis", {})
    model         = synthesis_cfg.get("model", "claude-sonnet-4-6")
    max_tokens    = synthesis_cfg.get("max_tokens", 8000)
    temperature   = synthesis_cfg.get("temperature", 0.7)
    lookback      = config.get("lookback_hours", 24)

    # ── Run Pure Signal pipeline ────────────────────────────────────────
    try:
        pure_signal_digest = ps_pipeline.run(
            people_config=config.get("people", {}),
            api_key=api_key,
            dedup_path=ps_dedup_path,
            synthesis_model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            lookback_hours=lookback,
            rss_delay=config.get("rate_limits", {}).get("rss_delay_seconds", 1.0),
        )
    except Exception:
        logger.exception("Pure Signal pipeline failed")
        pure_signal_digest = ""

    # ── Run Maranello pipeline ──────────────────────────────────────────
    try:
        maranello_result = mar_pipeline.run(
            api_key=api_key,
            db_path=mar_db_path,
            model=model,
        )
    except Exception:
        logger.exception("Maranello pipeline failed")
        maranello_result = {"briefing": "", "source_links": []}

    # ── Run HN Signal pipeline ──────────────────────────────────────────
    try:
        hn_signal_digest = hn_pipeline.run(
            api_key=api_key,
            seen_ids_path=hn_seen_path,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception:
        logger.exception("HN Signal pipeline failed")
        hn_signal_digest = ""

    # ── Check if anything happened today ───────────────────────────────
    has_ps  = bool(pure_signal_digest.strip())
    has_mar = bool(maranello_result.get("briefing", "").strip())
    has_hn  = bool(hn_signal_digest.strip())

    if not has_ps and not has_mar and not has_hn:
        logger.info("All pipelines returned empty — nothing to publish today.")
        return 0

    logger.info(
        "Results: Pure Signal=%s  HN Signal=%s  Maranello=%s",
        "yes" if has_ps else "quiet",
        "yes" if has_hn else "quiet",
        "yes" if has_mar else "quiet",
    )

    # ── Build and publish ───────────────────────────────────────────────
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

    builder = SiteBuilder(site_dir=str(site_dir), archive_dir=str(archive_dir))
    builder.save_combined_archive(today, pure_signal_digest, maranello_result, hn_signal=hn_signal_digest)
    builder.build()

    if args.dry_run or args.no_deploy:
        logger.info("Skipping deploy (site built in site/)")
        return 0

    cf_cfg      = config.get("cloudflare", {})
    project     = cf_cfg.get("project_name", "")
    account_id  = cf_cfg.get("account_id", "")

    # Inject Cloudflare token into env if supplied via credentials file
    cf_token = credentials.get("cloudflare", {}).get("api_token", "")
    if cf_token and not os.environ.get("CLOUDFLARE_API_TOKEN"):
        os.environ["CLOUDFLARE_API_TOKEN"] = cf_token

    success = deploy_site(str(site_dir), project_name=project, account_id=account_id)
    if success:
        logger.info("=== Signal Hub — published successfully ===")
    else:
        logger.error("Site built but deployment failed")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
