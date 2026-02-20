"""
Cloudflare Pages deployment via wrangler CLI.

Requires:
    - wrangler installed: npm install -g wrangler
    - Auth via CLOUDFLARE_API_TOKEN env var or `wrangler login`
"""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def deploy_site(site_dir: str, project_name: str, account_id: str = None) -> bool:
    """
    Deploy the built site to Cloudflare Pages using wrangler.

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

    cmd = ["wrangler", "pages", "deploy", site_dir, "--project-name", project_name]
    logger.info(f"Deploying {site_dir} to Cloudflare Pages project '{project_name}' …")

    env = os.environ.copy()
    if account_id:
        env["CLOUDFLARE_ACCOUNT_ID"] = account_id

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
            logger.error(f"Deployment failed (exit code {result.returncode})")
            if result.stderr:
                logger.error(result.stderr.strip())
            return False
    except FileNotFoundError:
        logger.error("wrangler not found. Install it with: npm install -g wrangler")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Deployment timed out after 120 seconds")
        return False
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        return False
