import os
import logging
import aiohttp

logger = logging.getLogger("bf1942_bot")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


async def send_health_alert(title: str, message: str):
    """Post an alert to the configured Discord webhook (if set)."""
    if not DISCORD_WEBHOOK_URL:
        return

    payload = {
        "embeds": [{
            "title": title,
            "description": message[:2000],
            "color": 0xFF0000,
        }]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
                if resp.status >= 400:
                    logger.warning(f"Health webhook returned {resp.status}")
    except Exception as e:
        logger.error(f"Failed to send health alert: {e}")
