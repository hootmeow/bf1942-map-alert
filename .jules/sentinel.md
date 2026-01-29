# Sentinel's Journal

## 2025-02-18 - Missing Authorization on Channel Subscriptions
**Vulnerability:** The `/subscribe` and `/subscribe_server` commands allowed any user to set up alerts for any channel the bot could access, without checking if the user had permission to manage that channel.
**Learning:** Checking bot permissions (`ctx.guild.me`) is not enough; you must also check the acting user's permissions (`ctx.author`) when performing sensitive actions like configuring channel-wide alerts. This is a classic "Confused Deputy" problem.
**Prevention:** Always verify that the user triggering an action has the appropriate rights for the target resource (channel), especially when the bot acts on their behalf.
