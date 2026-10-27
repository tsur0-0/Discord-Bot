import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.data import AFFINITY_STAGES

NOMENTION = discord.AllowedMentions.none()


class Fun(commands.Cog):
    """Boas-vindas, amizade e comandos secretos."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ---------------- boas-vindas ----------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cid = await self.db.get(member.guild.id, "welcome_channel")
        ch = member.guild.get_channel(int(cid)) if cid else None
        if not ch:
            return
        tpl = await self.db.get(member.guild.id, "welcome_msg")
        if not tpl:
            return
        txt = (tpl.replace("{user}", member.mention).replace("{server}", member.guild.name)
               .replace("{count}", str(member.guild.member_count)))
        try:
            await ch.send(txt, allowed_mentions=discord.AllowedMentions(users=[member]))
        except discord.HTTPException:
            pass

    # ---------------- comandos secretos (prefixo $) ----------------
    @commands.command(name="herobrine", hidden=True)
    @commands.guild_only()
    async def herobrine(self, ctx):
        await ctx.send("\U0001f441\ufe0f ...você não deveria ter dito esse nome.")

    @commands.command(name="konami", hidden=True)
    @commands.guild_only()
    async def konami(self, ctx):
        await ctx.send("⬆\ufe0f⬆\ufe0f⬇\ufe0f⬇\ufe0f⬅\ufe0f\u27a1\ufe0f⬅\ufe0f\u27a1\ufe0f\U0001f171\ufe0f\U0001f170\ufe0f — +30 vidas!")

    @commands.command(name="noteblock", hidden=True)
    @commands.guild_only()
    async def noteblock(self, ctx):
        await ctx.send("\U0001f3b5 " + " ".join(random.choice(["\u266a", "\u266b", "\u266c"]) for _ in range(8)))

    # ---------------- amizade ----------------
    @staticmethod
    def stage(points):
        name = AFFINITY_STAGES[0][1]
        for need, n in AFFINITY_STAGES:
            if points >= need:
                name = n
        return name

    @app_commands.command(name="afinidade", description="Registra uma interação de amizade (a cada 12h)")
    @app_commands.guild_only()
    async def afinidade(self, i: discord.Interaction, membro: discord.Member):
        if not await self.db.flag(i.guild_id, "affinity_enabled", True):
            return await i.response.send_message("O sistema de amizade está desativado neste servidor.", ephemeral=True)
        if membro.bot or membro.id == i.user.id:
            return await i.response.send_message("Escolha outra pessoa. \U0001f642", ephemeral=True)
        a, b = sorted((i.user.id, membro.id))
        now = int(time.time())
        row = await self.db.one("SELECT points,last FROM affinity WHERE guild_id=? AND a=? AND b=?",
                                (i.guild_id, a, b))
        points = row["points"] if row else 0
        if row and now - row["last"] < 43200:
            msg = "Vocês já interagiram há pouco — volte mais tarde!"
        else:
            points += 5
            await self.db.execute(
                "INSERT INTO affinity(guild_id,a,b,points,last) VALUES(?,?,?,?,?) "
                "ON CONFLICT(guild_id,a,b) DO UPDATE SET points=excluded.points,last=excluded.last",
                (i.guild_id, a, b, points, now))
            msg = "\U0001f49e +5 de afinidade!"
            if points >= 50:
        bar = "▰" * min(10, points // 10) + "▱" * (10 - min(10, points // 10))
        e = discord.Embed(title=f"{i.user.display_name} \U0001f91d {membro.display_name}",
                          description=f"{msg}\n**{self.stage(points)}** — {points} pts\n{bar}",
                          color=0xE91E63)
        await i.response.send_message(embed=e)

    @app_commands.command(name="amigos", description="Suas maiores afinidades")
    @app_commands.guild_only()
    async def amigos(self, i: discord.Interaction):
        if not await self.db.flag(i.guild_id, "affinity_enabled", True):
            return await i.response.send_message("O sistema de amizade está desativado neste servidor.", ephemeral=True)
        rows = await self.db.all(
            "SELECT a,b,points FROM affinity WHERE guild_id=? AND (a=? OR b=?) "
            "ORDER BY points DESC LIMIT 5", (i.guild_id, i.user.id, i.user.id))
        lines = [f"<@{r['b'] if r['a'] == i.user.id else r['a']}> — {self.stage(r['points'])} ({r['points']})"
                 for r in rows]
        await i.response.send_message("\n".join(lines) or "Você ainda não tem registros de amizade. Use /afinidade.",
                                      ephemeral=True, allowed_mentions=NOMENTION)


async def setup(bot):
    await bot.add_cog(Fun(bot))
