import logging

import discord

logger = logging.getLogger("bf1942_bot")


async def send_alert(bot, embed, clean_content, channel_id, user_id) -> bool:
    """Send an alert to a channel, or to the user's DMs when channel_id is empty.

    Skips users and guilds on the bot's blocklist. Returns True if sent.
    """
    if user_id in bot.blocked_user_ids:
        return False

    if channel_id:
        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Could not find channel {channel_id}")
                return False
            if channel.guild and channel.guild.id in bot.blocked_guild_ids:
                return False
            perms = channel.permissions_for(channel.guild.me)
            if not (perms.send_messages and perms.embed_links):
                logger.warning(f"Missing permissions for channel {channel_id}")
                return False
            await channel.send(content=clean_content, embed=embed)
            return True
        except Exception as e:
            logger.error(f"Error sending channel alert: {e}")
            return False

    try:
        user = await bot.fetch_user(user_id)
        await user.send(content=clean_content, embed=embed)
        return True
    except discord.Forbidden:
        logger.warning(f"Cannot DM user {user_id}")
    except Exception as e:
        logger.error(f"Error sending DM alert: {e}")
    return False
