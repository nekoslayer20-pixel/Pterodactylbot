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


class Users(commands.Cog):
    """User management commands."""

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

    @app_commands.command(name="user_list", description="List panel users (first page)")
    async def user_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.list_users()
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Failed to list users", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        lines = []
        if isinstance(data, dict) and data.get("data"):
            for u in data["data"][:50]:
                attr = u.get("attributes", {})
                lines.append(f"{attr.get('username')} (ID: {attr.get('id')}) Email: {attr.get('email')}")
        description = "\n".join(lines) or "No users found."
        await interaction.followup.send(embed=embeds.success_embed("Panel Users", description), ephemeral=True)

    @app_commands.command(name="user_search", description="Search users by email or username")
    @app_commands.describe(query="Query (email or username)")
    async def user_search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.search_users(query)
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Search failed", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        lines = []
        if isinstance(data, dict) and data.get("data"):
            for u in data["data"]:
                attr = u.get("attributes", {})
                lines.append(f"{attr.get('username')} (ID: {attr.get('id')}) Email: {attr.get('email')}")
        description = "\n".join(lines) or "No matches found."
        await interaction.followup.send(embed=embeds.success_embed("User Search", description), ephemeral=True)

    @app_commands.command(name="delete_user", description="Delete a panel user")
    @app_commands.describe(user_id="Panel user ID to delete")
    async def delete_user(self, interaction: discord.Interaction, user_id: int):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)
        resp = await ptero_api.delete_user(user_id)
        if resp.get("status") in (204, 200):
            admin_embed = embeds.warn_embed("User deleted", f"{interaction.user} deleted panel user {user_id}")
            await self._log_admin(admin_embed)
            return await interaction.followup.send(embed=embeds.success_embed("User deleted", f"User {user_id} deleted."), ephemeral=True)
        else:
            return await interaction.followup.send(embed=embeds.error_embed("Deletion failed", str(resp.get("data"))), ephemeral=True)

    @app_commands.command(name="change_password", description="Change panel user password")
    @app_commands.describe(user_id="Panel user ID", new_password="New password (leave blank to generate)")
    async def change_password(self, interaction: discord.Interaction, user_id: int, new_password: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)
        resp = await ptero_api.change_user_password(user_id, new_password)
        if resp.get("status") in (200,):
            password = resp.get("password") or new_password
            await self._log_admin(embeds.success_embed("Password changed", f"{interaction.user} changed password for user {user_id}"))
            return await interaction.followup.send(embed=embeds.success_embed("Password changed", f"New password: ||{password}||"), ephemeral=True)
        else:
            return await interaction.followup.send(embed=embeds.error_embed("Change failed", str(resp.get("data"))), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Users(bot))
