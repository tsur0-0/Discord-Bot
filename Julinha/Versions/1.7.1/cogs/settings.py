import discord
from discord import app_commands
from discord.ext import commands


@app_commands.default_permissions(manage_guild=True)
@app_commands.guild_only()
class Settings(commands.GroupCog, name="config", description="Configurações do servidor"):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def _ok(self, i: discord.Interaction) -> bool:
        if not i.user.guild_permissions.manage_guild:
            await i.response.send_message("\U0001f512 Você precisa da permissão **Gerenciar Servidor**.", ephemeral=True)
            return False
        return True

    async def _done(self, i, what, msg):
        await self.bot.logs.record(i.guild, "config:alterada", actor=i.user, details=what)
        await i.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="boas_vindas", description="Canal e mensagem de boas-vindas")
    @app_commands.describe(mensagem="Use {user}, {server} e {count}. Vazio mantém a atual.")
    async def boas_vindas(self, i: discord.Interaction, canal: discord.TextChannel,
                          mensagem: app_commands.Range[str, 1, 300] | None = None):
        if not await self._ok(i):
            return
        await self.db.set(i.guild_id, "welcome_channel", canal.id)
        if mensagem:
            await self.db.set(i.guild_id, "welcome_msg", mensagem)
        await self._done(i, f"boas-vindas em #{canal.name}", f"\U0001f44b Boas-vindas em {canal.mention}.")

    @app_commands.command(name="boas_vindas_desligar", description="Desliga as boas-vindas")
    async def boas_vindas_off(self, i: discord.Interaction):
        if not await self._ok(i):
            return
        await self.db.execute("DELETE FROM settings WHERE guild_id=? AND key IN ('welcome_channel','welcome_msg')",
                              (i.guild_id,))
        await self._done(i, "boas-vindas desligadas", "Boas-vindas desligadas.")

    @app_commands.command(name="xp", description="Liga/desliga o XP e ajusta o multiplicador")
    async def xp(self, i: discord.Interaction, ativo: bool | None = None,
                 multiplicador: app_commands.Range[float, 0.1, 5.0] | None = None):
        if not await self._ok(i):
            return
        if ativo is not None:
            await self.db.set(i.guild_id, "xp_enabled", int(ativo))
        if multiplicador is not None:
            await self.db.set(i.guild_id, "xp_mult", multiplicador)
        await self._done(i, f"xp ativo={ativo} mult={multiplicador}", "\u2728 Configuração de XP salva.")

    @app_commands.command(name="nivel_mensagem", description="Mensagem de subida de nível ({user}, {level})")
    async def nivel_msg(self, i: discord.Interaction, texto: app_commands.Range[str, 1, 200]):
        if not await self._ok(i):
            return
        await self.db.set(i.guild_id, "levelup_msg", texto)
        await self._done(i, "mensagem de nível alterada", "Mensagem de nível salva.")

    @app_commands.command(name="aleatorio", description="Chance (%) de mensagens aleatórias do bot")
    async def aleatorio(self, i: discord.Interaction, chance: app_commands.Range[int, 0, 50]):
        if not await self._ok(i):
            return
        await self.db.set(i.guild_id, "random_chance", chance)
        await self._done(i, f"random_chance={chance}", f"\U0001f3b2 Chance definida para {chance}%.")

    @app_commands.command(name="afinidade", description="Liga/desliga afinidade e amizade")
    async def afinidade(self, i: discord.Interaction, ativo: bool):
        if not await self._ok(i):
            return
        await self.db.set(i.guild_id, "affinity_enabled", int(ativo))
        await self._done(i, f"afinidade={ativo}", "\U0001f49e Afinidade " + ("ligada." if ativo else "desligada."))

    @app_commands.command(name="diversao", description="Liga/desliga respostas, memes e easter eggs")
    async def diversao(self, i: discord.Interaction, ativo: bool):
        if not await self._ok(i):
            return
        await self.db.set(i.guild_id, "fun_enabled", int(ativo))
        await self._done(i, f"diversao={ativo}", "\U0001f389 Diversão " + ("ligada." if ativo else "desligada."))

    @app_commands.command(name="resposta_add", description="Adiciona uma resposta automática")
    async def resposta_add(self, i: discord.Interaction, gatilho: app_commands.Range[str, 2, 50],
                           resposta: app_commands.Range[str, 1, 500]):
        if not await self._ok(i):
            return
        await self.db.execute("INSERT INTO replies(guild_id,word,response) VALUES(?,?,?)",
                              (i.guild_id, gatilho.lower(), resposta))
        await self._done(i, f"resposta '{gatilho}' adicionada", "\U0001f4ac Resposta adicionada.")

    @app_commands.command(name="resposta_remover", description="Remove as respostas de um gatilho")
    async def resposta_remover(self, i: discord.Interaction, gatilho: str):
        if not await self._ok(i):
            return
        cur = await self.db.execute("DELETE FROM replies WHERE guild_id=? AND word=?",
                                    (i.guild_id, gatilho.lower()))
        await self._done(i, f"respostas '{gatilho}' removidas ({cur.rowcount})", f"Removidas: {cur.rowcount}.")

    @app_commands.command(name="respostas", description="Lista as respostas automáticas")
    async def respostas(self, i: discord.Interaction):
        if not await self._ok(i):
            return
        rows = await self.db.all("SELECT word,response FROM replies WHERE guild_id=? LIMIT 25", (i.guild_id,))
        txt = "\n".join(f"`{r['word']}` → {r['response'][:80]}" for r in rows) or "Nenhuma."
        await i.response.send_message(txt, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Settings(bot))
