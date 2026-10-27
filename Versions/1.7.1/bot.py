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

COGS = ["cogs.core", "cogs.profile", "cogs.fun", "cogs.moderation", "cogs.logs", "cogs.videos", "cogs.social_watch"]


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
        # on_ready pode acontecer novamente após reconexões; avisa apenas uma vez por inicialização.
        if self.startup_notification_sent:
            return
        self.startup_notification_sent = True

        log.info("%s v%s está online como %s", config.BOT_NAME, config.BOT_VERSION, self.user)
        try:
            from io import BytesIO
            from datetime import datetime
            from PIL import Image, ImageDraw, ImageFont

            image = Image.new("RGB", (1000, 420), (18, 20, 28))
            draw = ImageDraw.Draw(image)
            try:
                title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
                body_font = ImageFont.truetype("DejaVuSans.ttf", 28)
                small_font = ImageFont.truetype("DejaVuSans.ttf", 20)
            except OSError:
                title_font = ImageFont.load_default()
                body_font = ImageFont.load_default()
                small_font = ImageFont.load_default()

            draw.rounded_rectangle((24, 24, 976, 396), radius=28, fill=(29, 33, 45), outline=(88, 101, 242), width=4)
            draw.ellipse((64, 72, 100, 108), fill=(65, 220, 130))
            draw.text((122, 62), "JULINHA CHAN", font=title_font, fill=(245, 247, 255))
            draw.text((66, 155), "STATUS: ATIVA", font=body_font, fill=(91, 230, 150))
            draw.text((66, 215), f"Versão {config.BOT_VERSION}", font=body_font, fill=(225, 229, 255))
            draw.text((66, 280), f"Conectada a {len(self.guilds)} servidor(es)", font=small_font, fill=(190, 197, 215))
            draw.text((66, 330), datetime.now().strftime("Inicializada em %d/%m/%Y às %H:%M:%S"), font=small_font, fill=(160, 169, 190))

            buffer = BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            file = discord.File(buffer, filename="julinha-status.png")
            embed = discord.Embed(
                title="\U0001f7e2 Julinha Chan está ativa!",
                description=f"Inicialização concluída com sucesso.\n**Versão atual:** {config.BOT_VERSION}",
                color=config.BRAND_COLOR,
            )
            embed.set_image(url="attachment://julinha-status.png")
            embed.set_footer(text=f"Online como {self.user}")
            owner = await self.fetch_user(config.STARTUP_NOTIFY_USER_ID)
            await owner.send(embed=embed, file=file)
            log.info("Notificação de inicialização enviada por DM para %s", config.STARTUP_NOTIFY_USER_ID)
        except Exception:
            log.exception("Não foi possível enviar a DM de inicialização")

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
