```markdown
# Pterodactyl Discord Bot — Setup Guide

This guide walks you through installing, configuring, and running the Pterodactyl Discord bot.

Requirements
- Python 3.10+
- A Pterodactyl Panel Application API key (with application-level permissions)
- A Discord bot token with applications.commands and bot privileges
- Admin Discord user IDs who are allowed to run privileged commands
- An admin channel ID to receive DM failure logs

Quick setup

1. Clone the repository
   git clone <repo-url>
   cd pterodactyl-discord-bot

2. Create and activate a Python virtual environment
   python -m venv venv
   source venv/bin/activate   # macOS / Linux
   venv\Scripts\activate      # Windows

3. Install dependencies
   pip install -r requirements.txt

4. Create a `.env` file based on `.env.example` and fill values:
   - DISCORD_TOKEN
   - PTERODACTYL_PANEL_URL
   - PTERODACTYL_API_KEY
   - ADMIN_IDS (comma-separated Discord IDs permitted for admin-only commands)
   - ADMIN_LOG_CHANNEL_ID (channel ID where DM failures / admin logs are posted)
   - OPTIONAL: MAX_RAM, MAX_CPU, MAX_DISK, DEFAULT_USER_PASSWORD_LENGTH

5. Invite the bot with the scopes:
   - applications.commands
   - bot (permissions: Send Messages, Embed Links, Use External Emojis if needed)

6. Run the bot
   python bot.py

Important behavior & security
- All Pterodactyl API keys are read from environment variables (see `.env.example`).
- Only Discord user IDs listed in `ADMIN_IDS` can run restricted commands:
  `/createserver`, `/delete_server`, `/suspend`, `/unsuspend`, `/set_resources`, `/delete_user`.
- Every server-related action attempts to DM the target user. If DM fails, the bot logs the failure to the `ADMIN_LOG_CHANNEL_ID`.
- Commands reply ephemerally to the invoker to avoid leaking sensitive data.
- Adjustable limits: `MAX_RAM`, `MAX_CPU`, `MAX_DISK` environment variables protect resource over-provisioning.
- Review Pterodactyl payloads (startup, nest/egg relationships, docker images) to match your panel version and eggs/nests structure.

Troubleshooting
- If slash commands do not appear immediately, allow up to 1 hour for global commands. For quicker testing, register commands to a test guild (modify cog registration or use app_commands.guild).
- Check bot logs and the configured admin log channel for DM failure messages.

Extending
- Add persistent storage for maintenance state if needed.
- Expand user search/filters using more Pterodactyl query parameters.
- Add more UI using discord.ui Views and modals.
```
