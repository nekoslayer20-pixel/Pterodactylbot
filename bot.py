import os
import logging
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN must be set in environment")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ptero-bot")

intents = discord.Intents.default()
intents.members = True  # needed to DM members reliably and resolve mentions

# We use commands.Bot to easily load cogs. Slash commands registered via bot.tree
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced.")
    except Exception as e:
        logger.exception("Failed to sync commands: %s", e)


# Load cogs
COGS = [
    "cogs.servers",
    "cogs.users",
    "cogs.panel",
]

if __name__ == "__main__":
    for cog in COGS:
        try:
            bot.load_extension(cog)
            logger.info("Loaded cog %s", cog)
        except Exception as e:
            logger.exception("Failed loading cog %s: %s", cog, e)

    bot.run(DISCORD_TOKEN)
