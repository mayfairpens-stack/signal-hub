"""
Cloudflare Pages deployment via wrangler CLI.

Requires:
    - wrangler installed: npm install -g wrangler
    - Auth via CLOUDFLARE_API_TOKEN env var or `wrangler login`
"""

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_RETRY_DELAY  = 20  # seconds between attempts


def deploy_site(site_dir: str, project_name: str, account_id: str = None) -> bool:
    """
    Deploy the built site to Cloudflare Pages using wrangler.

    Retries up to _MAX_ATTEMPTS times to handle transient Cloudflare API errors.

    Args:
        site_dir:     Path to the built site directory
        project_name: Cloudflare Pages project name
        account_id:   Cloudflare account ID (optional; falls back to env var)

    Returns:
        True if deployment succeeded
    """
    if not project_name:
        project_name = os.environ.get("CLOUDFLARE_PROJECT_NAME", "")

    if not project_name:
        logger.error(
            "Cloudflare project name not configured. "
            "Set cloudflare.project_name in config.yaml or CLOUDFLARE_PROJECT_NAME env var."
        )
        return False

    cmd = [
        "wrangler", "pages", "deploy", site_dir,
        "--project-name", project_name,
        "--commit-dirty=true",
    ]
    logger.info(f"Deploying {site_dir} to Cloudflare Pages project '{project_name}' …")

    env = os.environ.copy()
    if account_id:
        env["CLOUDFLARE_ACCOUNT_ID"] = account_id

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if result.returncode == 0:
                logger.info("Deployment succeeded")
                if result.stdout:
                    logger.info(result.stdout.strip())
                return True
            else:
                logger.warning(
                    f"Deployment attempt {attempt}/{_MAX_ATTEMPTS} failed (exit code {result.returncode})"
                )
                if result.stderr:
                    logger.warning(result.stderr.strip())
                if attempt < _MAX_ATTEMPTS:
                    logger.info(f"Retrying in {_RETRY_DELAY}s …")
                    time.sleep(_RETRY_DELAY)
        except FileNotFoundError:
            logger.error("wrangler not found. Install it with: npm install -g wrangler")
            return False
        except subprocess.TimeoutExpired:
            logger.warning(f"Deployment attempt {attempt}/{_MAX_ATTEMPTS} timed out after 120s")
            if attempt < _MAX_ATTEMPTS:
                logger.info(f"Retrying in {_RETRY_DELAY}s …")
                time.sleep(_RETRY_DELAY)
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False

    logger.error(f"Deployment failed after {_MAX_ATTEMPTS} attempts")
    return False
