import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import api as ptero_api
from utils import embeds
from utils import checks

ADMIN_LOG_CHANNEL_ID = int(os.getenv("ADMIN_LOG_CHANNEL_ID", "0"))


def _is_admin(interaction: discord.Interaction) -> bool:
    return checks.is_admin_id(interaction.user.id)


class Panel(commands.Cog):
    """Panel and infrastructure commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log_admin(self, embed: discord.Embed):
        if ADMIN_LOG_CHANNEL_ID == 0:
            return
        channel = self.bot.get_channel(ADMIN_LOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ADMIN_LOG_CHANNEL_ID)
            except Exception:
                return
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @app_commands.command(name="nodes", description="List nodes")
    async def nodes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.list_nodes()
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Failed to fetch nodes", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        lines = []
        if isinstance(data, dict) and data.get("data"):
            for n in data["data"]:
                a = n.get("attributes", {})
                lines.append(f"{a.get('name')} (ID: {a.get('id')}) Location: {a.get('location_id')}")
        description = "\n".join(lines) or "No nodes found."
        await interaction.followup.send(embed=embeds.success_embed("Nodes", description), ephemeral=True)

    @app_commands.command(name="eggs", description="List eggs")
    async def eggs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.list_eggs()
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Failed to fetch eggs", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        lines = []
        if isinstance(data, dict) and data.get("data"):
            for e in data["data"]:
                a = e.get("attributes", {})
                lines.append(f"{a.get('name')} (ID: {a.get('id')}) Nest: {a.get('nest')}")
        description = "\n".join(lines) or "No eggs found."
        await interaction.followup.send(embed=embeds.success_embed("Eggs", description), ephemeral=True)

    @app_commands.command(name="panel_status", description="Check panel status (simple)")
    async def panel_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok = await ptero_api.ping_panel()
        if ok:
            await interaction.followup.send(embed=embeds.success_embed("Panel status", "Panel is reachable"), ephemeral=True)
        else:
            await interaction.followup.send(embed=embeds.error_embed("Panel unreachable", "Could not reach panel API"), ephemeral=True)

    @app_commands.command(name="backup_list", description="List backups for a server")
    @app_commands.describe(server_id="Server ID")
    async def backup_list(self, interaction: discord.Interaction, server_id: str):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.list_backups(server_id)
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Failed to fetch backups", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        lines = []
        if isinstance(data, dict) and data.get("data"):
            for b in data["data"]:
                a = b.get("attributes", {})
                lines.append(f"Backup ID: {a.get('uuid')} | Name: {a.get('name')} | Size: {a.get('bytes')}")
        description = "\n".join(lines) or "No backups found."
        await interaction.followup.send(embed=embeds.success_embed("Backups", description), ephemeral=True)

    @app_commands.command(name="maintenance_on", description="Set maintenance mode ON for a server (sends DM)")
    @app_commands.describe(server_id="Server ID or UUID", user="Discord user to notify")
    async def maintenance_on(self, interaction: discord.Interaction, server_id: str, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)
        # NOTE: Pterodactyl does not have a universal "maintenance" API endpoint across all versions.
        # We'll inform the user and log — implement your panel-specific maintenance toggle if available.
        dm_embed = embeds.warn_embed("⚠️ MAINTENANCE ON", f"Server ID: {server_id}\nMaintenance: ON")
        dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Maintenance ON for {server_id}")
        await self._log_admin(embeds.warn_embed("Maintenance toggled ON", f"{interaction.user} set maintenance ON for {server_id}. DM sent: {dm_sent}"))
        await interaction.followup.send(embed=embeds.success_embed("Maintenance ON", f"User notified: {dm_sent}"), ephemeral=True)

    @app_commands.command(name="maintenance_off", description="Set maintenance mode OFF for a server (sends DM)")
    @app_commands.describe(server_id="Server ID or UUID", user="Discord user to notify")
    async def maintenance_off(self, interaction: discord.Interaction, server_id: str, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)
        dm_embed = embeds.success_embed("✅ MAINTENANCE OFF", f"Server ID: {server_id}\nMaintenance: OFF")
        dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Maintenance OFF for {server_id}")
        await self._log_admin(embeds.success_embed("Maintenance toggled OFF", f"{interaction.user} set maintenance OFF for {server_id}. DM sent: {dm_sent}"))
        await interaction.followup.send(embed=embeds.success_embed("Maintenance OFF", f"User notified: {dm_sent}"), ephemeral=True)

    async def _dm_user_or_log(self, member: discord.User, embed: discord.Embed, fallback_text: Optional[str] = None):
        try:
            await member.send(embed=embed)
            return True
        except Exception as e:
            reason = str(e)
            warn = embeds.warn_embed(
                "DM Failure: Could not notify user",
                f"Could not DM {member} ({member.id}). Reason: {reason}\nFallback: {fallback_text or 'See admin log.'}"
            )
            await self._log_admin(warn)
            return False


async def setup(bot: commands.Bot):
    await bot.add_cog(Panel(bot))
