import asyncio
import logging
import sys
import traceback

import discord
from discord import app_commands
from discord.ext import commands

import config
from db import Database
from logservice import LogService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

COGS = ["cogs.core", "cogs.profile", "cogs.fun", "cogs.moderation", "cogs.logs", "cogs.videos", "cogs.social_watch", "cogs.settings", "cogs.panels"]


class CommunityBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("$"),
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )
        self.db = Database(config.DB_PATH)
        self.logs = LogService(self)
        self.startup_notification_sent = False

    async def on_ready(self):
        log.info("%s v%s está online como %s", config.BOT_NAME, config.BOT_VERSION, self.user)

    async def setup_hook(self):
        await self.db.connect()
        for cog in COGS:
            await self.load_extension(cog)
        self.tree.on_error = self.on_tree_error
        if config.DEV_GUILD_ID:
            guild = discord.Object(config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self):
        await super().close()
        await self.db.close()

    async def on_error(self, event_method, *args, **kwargs):
        tb = traceback.format_exc()
        log.error("Erro no evento %s\n%s", event_method, tb)
        try:
            await self.db.log_error(f"evento:{event_method}", tb[-1400:])
        except Exception:
            pass

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            msg = "\U0001f512 Você não tem permissão para usar isso."
        else:
            msg = "\U0001f4a5 Algo deu errado. O erro foi registrado."
            name = interaction.command.qualified_name if interaction.command else "?"
            await self.db.log_error(f"comando:{name}", "".join(
                traceback.format_exception(type(error), error, error.__traceback__))[-1400:])
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


async def main():
    if not config.TOKEN:
        sys.exit("Defina DISCORD_TOKEN no arquivo .env")
    async with CommunityBot() as bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
