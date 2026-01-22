import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import api as ptero_api
from utils import embeds
from utils import checks

ADMIN_LOG_CHANNEL_ID = int(os.getenv("ADMIN_LOG_CHANNEL_ID", "0"))
MAX_RAM = int(os.getenv("MAX_RAM", "32768"))
MAX_CPU = int(os.getenv("MAX_CPU", "800"))
MAX_DISK = int(os.getenv("MAX_DISK", "200000"))


def _is_admin(interaction: discord.Interaction) -> bool:
    return checks.is_admin_id(interaction.user.id)


class Servers(commands.Cog):
    """Server management commands."""

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
            # Best-effort logging only
            try:
                self.bot.logger.exception("Failed to send admin log message.")
            except Exception:
                pass

    async def _dm_user_or_log(self, member: discord.User, embed: discord.Embed, fallback_text: Optional[str] = None):
        """Try to DM; on failure, log to admin channel with details."""
        try:
            await member.send(embed=embed)
            return True
        except Exception as e:
            # DM failed: send a log to admin channel
            reason = str(e)
            warn = embeds.warn_embed(
                "DM Failure: Could not notify user",
                f"Could not DM {member} ({member.id}). Reason: {reason}\nFallback: {fallback_text or 'See admin log.'}"
            )
            await self._log_admin(warn)
            return False

    # -----------------------
    # /createserver
    # -----------------------
    @app_commands.command(name="createserver", description="Create a new server on the panel")
    @app_commands.describe(
        name="Server name",
        ram="RAM in MB",
        cpu="CPU units (integer)",
        disk="Disk in MB",
        version="Server startup/version string",
        node_id="Node ID to create the server on",
        egg_id="Egg ID to use",
        user="Discord user who will own the created server"
    )
    async def createserver(
        self,
        interaction: discord.Interaction,
        name: str,
        ram: int,
        cpu: int,
        disk: int,
        version: str,
        node_id: int,
        egg_id: int,
        user: discord.User
    ):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)

        # Validate resources
        if ram <= 0 or cpu <= 0 or disk <= 0:
            return await interaction.followup.send(embed=embeds.error_embed("Invalid resources", "RAM/CPU/Disk must be positive integers."), ephemeral=True)
        if ram > MAX_RAM or cpu > MAX_CPU or disk > MAX_DISK:
            return await interaction.followup.send(
                embed=embeds.error_embed(
                    "Resource limits exceeded",
                    f"Requested resources exceed allowed maxima (MAX_RAM={MAX_RAM}, MAX_CPU={MAX_CPU}, MAX_DISK={MAX_DISK})."
                ),
                ephemeral=True
            )

        # Validate node and egg
        node = await ptero_api.get_node(node_id)
        if node.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Invalid node", f"Node {node_id} not found or unreachable."), ephemeral=True)
        egg = await ptero_api.get_egg(egg_id)
        if egg.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Invalid egg", f"Egg {egg_id} not found or unreachable."), ephemeral=True)

        # Ensure panel user exists or create
        panel_email = f"{user.id}@discord.local"
        panel_username = f"{user.name}".replace(" ", "_")[:32]

        found = await ptero_api.find_user_by_email(panel_email)
        created_password = None
        panel_user_id = None

        if found:
            # Try to get ID from possible response shapes
            panel_user_id = found.get("id") or found.get("attributes", {}).get("id")
        else:
            # Create user
            create_resp = await ptero_api.create_user(email=panel_email, username=panel_username, first_name=user.name, last_name="", password=None)
            if create_resp.get("status") not in (201, 200):
                desc = create_resp.get("data") or "Unknown error creating panel user."
                return await interaction.followup.send(embed=embeds.error_embed("Failed to create panel user", str(desc)), ephemeral=True)
            data = create_resp.get("data", {})
            # extract id
            panel_user_id = data.get("attributes", {}).get("id") or data.get("id")
            created_password = create_resp.get("password")

        if not panel_user_id:
            return await interaction.followup.send(embed=embeds.error_embed("User resolution error", "Could not determine panel user ID."), ephemeral=True)

        # Create server
        server_resp = await ptero_api.create_server(
            name=name,
            user_id=int(panel_user_id),
            node_id=node_id,
            egg_id=egg_id,
            ram=ram,
            cpu=cpu,
            disk=disk,
            version=version,
            startup=version
        )

        if server_resp.get("status") not in (201, 200):
            return await interaction.followup.send(embed=embeds.error_embed("Server creation failed", str(server_resp.get("data"))), ephemeral=True)

        server_data = server_resp.get("data", {})
        # extract server id and identifier if present
        server_id = None
        identifier = None
        if isinstance(server_data, dict):
            if "attributes" in server_data:
                server_id = server_data["attributes"].get("id")
                identifier = server_data["attributes"].get("identifier")
            elif "data" in server_data and isinstance(server_data["data"], dict):
                attr = server_data["data"].get("attributes", {})
                server_id = attr.get("id") or server_data["data"].get("id")
                identifier = attr.get("identifier")

        # Send DM to user
        dm_embed = embeds.success_embed("✅ SERVER CREATED", f"Server Name: {name}\nServer ID: {server_id or identifier}\nNode: {node_id}\nRAM: {ram} MB\nCPU: {cpu}\nDisk: {disk} MB\nVersion: {version}\nPanel URL: {ptero_api.PANEL_URL}")
        if created_password:
            dm_embed.add_field(name="Username", value=panel_username, inline=True)
            dm_embed.add_field(name="Password (new user)", value=created_password, inline=True)

        dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Server {server_id or identifier} created")

        # Log to admin channel
        admin_embed = embeds.success_embed("Server Creation", f"{interaction.user} created server {name} for {user} (Server ID: {server_id or identifier})")
        await self._log_admin(admin_embed)

        return await interaction.followup.send(embed=embeds.success_embed("Server created", f"Server created for {user.mention}. DM sent: {dm_sent}"), ephemeral=True)

    # -----------------------
    # /delete_server
    # -----------------------
    @app_commands.command(name="delete_server", description="Delete a server by ID")
    @app_commands.describe(server_id="Server ID or UUID", user="Discord user to notify")
    async def delete_server(self, interaction: discord.Interaction, server_id: str, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)

        resp = await ptero_api.delete_server(server_id)
        if resp.get("status") in (204, 200):
            # DM user
            dm_embed = embeds.error_embed("❌ SERVER DELETED", f"Server ID: {server_id}\nDeleted By: {interaction.user}\nDate & Time: {discord.utils.utcnow().isoformat()}")
            dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Server {server_id} deleted by {interaction.user}")
            # Log
            admin_embed = embeds.warn_embed("Server Deleted", f"{interaction.user} deleted server {server_id} for {user}. DM sent: {dm_sent}")
            await self._log_admin(admin_embed)
            return await interaction.followup.send(embed=embeds.success_embed("Server deleted", f"Server {server_id} deleted. User notified: {dm_sent}"), ephemeral=True)
        else:
            return await interaction.followup.send(embed=embeds.error_embed("Delete failed", str(resp.get("data"))), ephemeral=True)

    # -----------------------
    # /suspend
    # -----------------------
    @app_commands.command(name="suspend", description="Suspend a server by ID")
    @app_commands.describe(server_id="Server ID or UUID", user="Discord user to notify", reason="Optional reason")
    async def suspend(self, interaction: discord.Interaction, server_id: str, user: discord.User, reason: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)

        resp = await ptero_api.suspend_server(server_id)
        if resp.get("status") in (200,):
            dm_embed = embeds.warn_embed("⚠️ SERVER SUSPENDED", f"Server ID: {server_id}\nReason: {reason or 'No reason provided'}")
            dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Server {server_id} suspended")
            admin_embed = embeds.warn_embed("Server Suspended", f"{interaction.user} suspended server {server_id} for {user}. DM sent: {dm_sent}")
            await self._log_admin(admin_embed)
            return await interaction.followup.send(embed=embeds.success_embed("Server suspended", f"Server {server_id} suspended. User notified: {dm_sent}"), ephemeral=True)
        else:
            return await interaction.followup.send(embed=embeds.error_embed("Suspend failed", str(resp.get("data"))), ephemeral=True)

    # -----------------------
    # /unsuspend
    # -----------------------
    @app_commands.command(name="unsuspend", description="Unsuspend a server by ID")
    @app_commands.describe(server_id="Server ID or UUID", user="Discord user to notify")
    async def unsuspend(self, interaction: discord.Interaction, server_id: str, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)

        resp = await ptero_api.unsuspend_server(server_id)
        if resp.get("status") in (200,):
            dm_embed = embeds.success_embed("✅ SERVER UNSUSPENDED", f"Server ID: {server_id}")
            dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Server {server_id} unsuspended")
            admin_embed = embeds.success_embed("Server Unsuspended", f"{interaction.user} unsuspended server {server_id} for {user}. DM sent: {dm_sent}")
            await self._log_admin(admin_embed)
            return await interaction.followup.send(embed=embeds.success_embed("Server unsuspended", f"Server {server_id} unsuspended. User notified: {dm_sent}"), ephemeral=True)
        else:
            return await interaction.followup.send(embed=embeds.error_embed("Unsuspend failed", str(resp.get("data"))), ephemeral=True)

    # -----------------------
    # /set_resources
    # -----------------------
    @app_commands.command(name="set_resources", description="Change server resources (memory/cpu/disk)")
    @app_commands.describe(server_id="Server ID or UUID", memory="Memory in MB", cpu="CPU units", disk="Disk in MB", user="User to notify")
    async def set_resources(self, interaction: discord.Interaction, server_id: str, memory: Optional[int], cpu: Optional[int], disk: Optional[int], user: discord.User):
        await interaction.response.defer(ephemeral=True)
        if not _is_admin(interaction):
            return await interaction.followup.send(embed=embeds.error_embed("Permission denied", "You are not allowed to use this command."), ephemeral=True)

        # Validate limits
        if memory is not None and (memory <= 0 or memory > MAX_RAM):
            return await interaction.followup.send(embed=embeds.error_embed("Memory limit error", f"Memory must be 1..{MAX_RAM} MB"), ephemeral=True)
        if cpu is not None and (cpu <= 0 or cpu > MAX_CPU):
            return await interaction.followup.send(embed=embeds.error_embed("CPU limit error", f"CPU must be 1..{MAX_CPU}"), ephemeral=True)
        if disk is not None and (disk <= 0 or disk > MAX_DISK):
            return await interaction.followup.send(embed=embeds.error_embed("Disk limit error", f"Disk must be 1..{MAX_DISK} MB"), ephemeral=True)

        resp = await ptero_api.set_server_resources(server_id, memory=memory, cpu=cpu, disk=disk)
        if resp.get("status") in (200,):
            details = f"Memory: {memory if memory is not None else 'unchanged'} MB\nCPU: {cpu if cpu is not None else 'unchanged'}\nDisk: {disk if disk is not None else 'unchanged'}"
            dm_embed = embeds.success_embed("✅ RESOURCES UPDATED", f"Server ID: {server_id}\n{details}")
            dm_sent = await self._dm_user_or_log(user, dm_embed, fallback_text=f"Resources updated for server {server_id}")
            admin_embed = embeds.success_embed("Resources changed", f"{interaction.user} changed resources for {server_id}. DM sent: {dm_sent}\n{details}")
            await self._log_admin(admin_embed)
            return await interaction.followup.send(embed=embeds.success_embed("Resources updated", f"User notified: {dm_sent}"), ephemeral=True)
        else:
            return await interaction.followup.send(embed=embeds.error_embed("Failed to update resources", str(resp.get("data"))), ephemeral=True)

    # -----------------------
    # /list_servers
    # -----------------------
    @app_commands.command(name="list_servers", description="List servers on the panel")
    async def list_servers(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.list_servers()
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Failed to list servers", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        items = []
        # Attempt to parse common response shapes
        if isinstance(data, dict) and data.get("data"):
            for item in data["data"]:
                attr = item.get("attributes", {})
                items.append(f"{attr.get('name')} (ID: {attr.get('id')}) Owner: {attr.get('user')}")
        elif isinstance(data, list):
            for s in data:
                items.append(str(s))
        else:
            items.append(str(data))
        description = "\n".join(items[:25]) or "No servers found."
        await interaction.followup.send(embed=embeds.success_embed("Servers", description), ephemeral=True)

    # -----------------------
    # /server_info
    # -----------------------
    @app_commands.command(name="server_info", description="Get info for a server")
    @app_commands.describe(server_id="Server ID or UUID")
    async def server_info(self, interaction: discord.Interaction, server_id: str):
        await interaction.response.defer(ephemeral=True)
        resp = await ptero_api.get_server(server_id)
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Failed to fetch server", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        # Present some fields
        attr = None
        if isinstance(data, dict):
            attr = data.get("attributes") or data.get("data", {}).get("attributes") or data.get("data")
        if not attr:
            return await interaction.followup.send(embed=embeds.error_embed("Unexpected response", str(data)), ephemeral=True)
        desc_lines = []
        for k in ("name", "identifier", "uuid", "node", "memory", "disk", "cpu"):
            if k in attr:
                desc_lines.append(f"{k}: {attr.get(k)}")
        await interaction.followup.send(embed=embeds.success_embed("Server Info", "\n".join(desc_lines)), ephemeral=True)

    # -----------------------
    # /server_search
    # -----------------------
    @app_commands.command(name="server_search", description="Search servers by name or owner")
    @app_commands.describe(query="Search query (name or owner)")
    async def server_search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        # Naive search: fetch list and filter
        resp = await ptero_api.list_servers()
        if resp.get("status") not in (200,):
            return await interaction.followup.send(embed=embeds.error_embed("Search failed", str(resp.get("data"))), ephemeral=True)
        data = resp.get("data") or {}
        matches = []
        if isinstance(data, dict) and data.get("data"):
            for item in data["data"]:
                attr = item.get("attributes", {})
                name = attr.get("name", "")
                owner = str(attr.get("user", ""))
                if query.lower() in name.lower() or query in str(owner):
                    matches.append(f"{name} (ID: {attr.get('id')}) Owner: {owner}")
        description = "\n".join(matches[:25]) or "No matches found."
        await interaction.followup.send(embed=embeds.success_embed("Search results", description), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Servers(bot))
