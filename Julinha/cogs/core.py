import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config


class Core(commands.Cog):
    """Status/presença, histórico de erros e reconexões, log de comandos admin."""

    def __init__(self, bot):
        self.bot = bot
        self.n = 0
        # Presença definida manualmente por /status; pausa a rotação automática.
        self.manual_presence = None

    async def cog_load(self):
        self.presence.start()

    async def cog_unload(self):
        self.presence.cancel()

    @tasks.loop(minutes=config.PRESENCE_MINUTES)
    async def presence(self):
        if self.manual_presence is not None:
            activity_type, text, status = self.manual_presence
            activity = discord.Activity(type=activity_type, name=text) if activity_type is not None and text else None
            await self.bot.change_presence(status=status, activity=activity)
            return

        kind, txt = config.PRESENCES[self.n % len(config.PRESENCES)]
        self.n += 1
        txt = txt.format(servers=len(self.bot.guilds),
                         members=sum(g.member_count or 0 for g in self.bot.guilds))
        types = {"playing": discord.ActivityType.playing,
                 "watching": discord.ActivityType.watching,
                 "listening": discord.ActivityType.listening}
        await self.bot.change_presence(status=discord.Status.online,
                                       activity=discord.Activity(type=types.get(kind, types["playing"]), name=txt))

    @presence.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    # ---- conexão ----
    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.db.log_error("pronto", f"Conectado como {self.bot.user} ({len(self.bot.guilds)} servidores)")

    @commands.Cog.listener()
    async def on_disconnect(self):
        await self.bot.db.log_error("desconexao", "Conexão com o gateway perdida")

    @commands.Cog.listener()
    async def on_resumed(self):
        await self.bot.db.log_error("reconexao", "Sessão retomada")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
            return
        await self.bot.db.log_error(f"prefixo:{ctx.command}", repr(error))

    # ---- comandos administrativos ----
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction, command):
        root = getattr(command, "root_parent", None) or command
        if getattr(root, "default_permissions", None) is None or not interaction.guild:
            return
        ns = {k: str(v)[:60] for k, v in dict(interaction.namespace).items()}
        await self.bot.logs.record(interaction.guild, "comando:admin", actor=interaction.user,
                                   details=f"/{command.qualified_name} {ns}")

    @app_commands.command(name="status", description="Altera a atividade e o estado online do bot")
    @app_commands.describe(
        tipo="Tipo de atividade que aparece no perfil",
        texto="Texto exibido na atividade (opcional)",
        estado="Estado de presença do bot"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Jogando", value="playing"),
        app_commands.Choice(name="Assistindo", value="watching"),
        app_commands.Choice(name="Ouvindo", value="listening"),
        app_commands.Choice(name="Sem atividade", value="none"),
    ], estado=[
        app_commands.Choice(name="Online", value="online"),
        app_commands.Choice(name="Ausente", value="idle"),
        app_commands.Choice(name="Não perturbe", value="dnd"),
        app_commands.Choice(name="Invisível", value="invisible"),
    ])
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, i: discord.Interaction, tipo: str, texto: str = "", estado: str = "online"):
        activity_types = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
        }
        presence_statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        activity_type = activity_types.get(tipo)
        clean_text = texto.strip()[:128]
        self.manual_presence = (activity_type, clean_text, presence_statuses[estado])
        activity = discord.Activity(type=activity_type, name=clean_text) if activity_type is not None and clean_text else None
        await self.bot.change_presence(status=presence_statuses[estado], activity=activity)
        labels = {"playing": "Jogando", "watching": "Assistindo", "listening": "Ouvindo", "none": "Sem atividade"}
        status_labels = {"online": "Online", "idle": "Ausente", "dnd": "Não perturbe", "invisible": "Invisível"}
        activity_label = f" `{clean_text}`" if clean_text else ""
        await i.response.send_message(
            f"Status atualizado: **{labels[tipo]}**{activity_label} · **{status_labels[estado]}**.\n"
            "A rotação automática ficará pausada até reiniciar a Julinha.",
            ephemeral=True,
        )

    @app_commands.command(name="status_auto", description="Volta a alternar automaticamente as atividades")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def status_auto(self, i: discord.Interaction):
        self.manual_presence = None
        await self.presence()
        await i.response.send_message("Rotação automática de status reativada.", ephemeral=True)

    @app_commands.command(name="ping", description="Mostra a latência do bot")
    async def ping(self, i: discord.Interaction):
        await i.response.send_message(f"Latência: {round(self.bot.latency * 1000)} ms")

    @app_commands.command(name="sobre", description="Informações sobre o bot")
    async def sobre(self, i: discord.Interaction):
        e = discord.Embed(title=config.BOT_NAME, color=config.BRAND_COLOR,
                          description="Ferramentas de comunidade, perfis, níveis, moderação e auditoria.")
        e.set_footer(text=f"v{config.BOT_VERSION} • {len(self.bot.guilds)} servidores")
        await i.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Core(bot))
