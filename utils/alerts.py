import logging
import time

import discord

logger = logging.getLogger("bf1942_bot")

# A channel that keeps failing (deleted, or bot removed from the guild) has its
# subscriptions removed once it has failed this many times over this long.
# Both limits must be hit, so a short Discord outage can't wipe anyone's subs.
CHANNEL_FAILURES_BEFORE_REMOVAL = 5
CHANNEL_FAILURE_MIN_SPAN_SECONDS = 6 * 3600

# Users with DMs closed: stop trying for a while after repeated refusals
DM_FAILURES_BEFORE_MUTE = 3
DM_MUTE_SECONDS = 24 * 3600

_channel_failures = {}  # {channel_id: (count, first_failure_ts)}
_dm_failures = {}       # {user_id: consecutive Forbidden count}
_dm_muted_until = {}    # {user_id: ts}

# fetch_user is an API call and its result isn't cached by the client (no
# members intent), so keep the User objects; that also reuses their DM channel.
USER_CACHE_MAX = 5000
_users = {}             # {user_id: discord.User}


async def _get_user(bot, user_id):
    user = _users.get(user_id) or bot.get_user(user_id)
    if user is None:
        user = await bot.fetch_user(user_id)
    if len(_users) >= USER_CACHE_MAX:
        _users.clear()
    _users[user_id] = user
    return user


async def _channel_failed(bot, channel_id, reason):
    count, first = _channel_failures.get(channel_id, (0, time.time()))
    count += 1
    _channel_failures[channel_id] = (count, first)
    if count >= CHANNEL_FAILURES_BEFORE_REMOVAL and time.time() - first >= CHANNEL_FAILURE_MIN_SPAN_SECONDS:
        _channel_failures.pop(channel_id, None)
        try:
            removed = await bot.db.delete_subscriptions_for_channel(channel_id)
            logger.warning(f"Removed {removed} subscription(s) for unreachable channel {channel_id} ({reason})")
        except Exception as e:
            logger.error(f"Failed to remove subscriptions for channel {channel_id}: {e}")
    else:
        logger.warning(f"Channel {channel_id} unreachable ({reason}), failure {count}")


def _dm_failed(user_id):
    count = _dm_failures.get(user_id, 0) + 1
    if count >= DM_FAILURES_BEFORE_MUTE:
        _dm_failures.pop(user_id, None)
        _dm_muted_until[user_id] = time.time() + DM_MUTE_SECONDS
        logger.warning(f"Cannot DM user {user_id}; pausing DMs to them for 24h")
    else:
        _dm_failures[user_id] = count
        logger.warning(f"Cannot DM user {user_id}")


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
                await _channel_failed(bot, channel_id, "not found")
                return False
            if channel.guild and channel.guild.id in bot.blocked_guild_ids:
                return False
            perms = channel.permissions_for(channel.guild.me)
            if not (perms.send_messages and perms.embed_links):
                logger.warning(f"Missing permissions for channel {channel_id}")
                return False
            await channel.send(content=clean_content, embed=embed)
            _channel_failures.pop(channel_id, None)
            return True
        except (discord.NotFound, discord.Forbidden) as e:
            await _channel_failed(bot, channel_id, type(e).__name__)
        except Exception as e:
            logger.error(f"Error sending channel alert: {e}")
        return False

    muted_until = _dm_muted_until.get(user_id)
    if muted_until:
        if time.time() < muted_until:
            return False
        del _dm_muted_until[user_id]

    try:
        user = await _get_user(bot, user_id)
        await user.send(content=clean_content, embed=embed)
        _dm_failures.pop(user_id, None)
        return True
    except discord.Forbidden:
        _dm_failed(user_id)
    except Exception as e:
        logger.error(f"Error sending DM alert: {e}")
    return False
