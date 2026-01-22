import discord
from typing import Optional

# Colors
GREEN = discord.Color.green()
RED = discord.Color.red()
YELLOW = discord.Color.orange()

def success_embed(title: str, description: str = "", footer: Optional[str] = None) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=GREEN)
    if footer:
        e.set_footer(text=footer)
    return e

def error_embed(title: str, description: str = "", footer: Optional[str] = None) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=RED)
    if footer:
        e.set_footer(text=footer)
    return e

def warn_embed(title: str, description: str = "", footer: Optional[str] = None) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=YELLOW)
    if footer:
        e.set_footer(text=footer)
    return e
