import asyncio
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import images
from utils.data import ACCENTS
from utils.leveling import level_from_xp


class Profile(commands.Cog):
    """XP, níveis, perfil e preferências."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ---------------- XP -------------------------
    @commands.Cog.listener()
    async def on_message(self, m: discord.Message):
        if m.author.bot or not m.guild or m.content.startswith("$"):
            return
        gid = m.guild.id
        if not await self.db.flag(gid, "xp_enabled", True):
            return
        now = int(time.time())
        row = await self.db.user(gid, m.author.id)
        gain = 0
        if now - row["last_xp"] >= config.XP_COOLDOWN:
            mult = await self.db.number(gid, "xp_mult", 1.0)
            gain = max(1, int(random.randint(config.XP_MIN, config.XP_MAX) * mult))
        await self.db.execute(
            "UPDATE users SET xp=xp+?, messages=messages+1, last_xp=? WHERE guild_id=? AND user_id=?",
            (gain, now if gain else row["last_xp"], gid, m.author.id))
        msgs = row["messages"] + 1
        old_lvl = level_from_xp(row["xp"])[0]
        new_lvl = level_from_xp(row["xp"] + gain)[0]

        if new_lvl > old_lvl:
            await self.sync_level_roles(m.author, new_lvl)
            if row["notify"]:
                tpl = await self.db.get(gid, "levelup_msg") or "\U0001f389 {user} subiu para o **nível {level}**!"
                txt = tpl.replace("{user}", m.author.mention).replace("{level}", str(new_lvl))
                try:
                    await m.channel.send(txt, allowed_mentions=discord.AllowedMentions(users=[m.author]))
                except discord.HTTPException:
                    pass

    async def sync_level_roles(self, member, level):
        me = member.guild.me
        if not me.guild_permissions.manage_roles:
            return
        rows = await self.db.all(
            "SELECT role_id FROM level_roles WHERE guild_id=? AND level<=?", (member.guild.id, level))
        roles = [member.guild.get_role(r["role_id"]) for r in rows]
        add = [r for r in roles if r and r not in member.roles and not r.managed and r < me.top_role]
        if add:
            try:
                await member.add_roles(*add, reason="[auto] nível alcançado")
            except discord.HTTPException:
                pass

    # ---------------- cartão ----------------
    async def build_profile(self, member: discord.Member, viewer: discord.Member):
        gid = member.guild.id
        row = await self.db.user(gid, member.id)
        private = (not row["public"] and viewer.id != member.id
                   and not viewer.guild_permissions.manage_guild)
        if private:
            e = discord.Embed(title=f"Perfil de {member.display_name}", color=config.BRAND_COLOR,
                              description="\U0001f512 Este perfil é privado.")
            e.set_thumbnail(url=member.display_avatar.url)
            return None, e

        level, prog, need = level_from_xp(row["xp"])
        rank = await self.db.rank(gid, member.id)
        accent = ACCENTS.get(row["accent"], ACCENTS["verde"])
        joined = member.joined_at
        days = max(1, (discord.utils.utcnow() - joined).days) if joined else 1
        stats = {"Mensagens": row["messages"], "XP total": row["xp"],
                 "Msgs/dia": round(row["messages"] / days, 1)}
        avatar = await member.display_avatar.replace(size=256, format="png").read()
        buf = await asyncio.to_thread(
            images.render_profile_card, avatar, member.display_name,
            joined.strftime("%d/%m/%Y") if joined else "?", level, prog, need, rank, row["xp"],
            row["bio"] or "Sem biografia ainda. Use /bio!",
            f"« {row['title']} »" if row["title"] else "", accent, stats)
        file = discord.File(buf, "perfil.png")
        e = discord.Embed(color=discord.Color.from_rgb(*accent))
        e.set_image(url="attachment://perfil.png")
        roles = [r.mention for r in reversed(member.roles) if not r.is_default()][:10]
        e.add_field(name="Cargos", value=" ".join(roles) or "Nenhum", inline=False)
        return file, e

    @app_commands.command(name="perfil", description="Mostra o cartão de perfil")
    @app_commands.guild_only()
    async def perfil(self, i: discord.Interaction, membro: discord.Member | None = None):
        await i.response.defer()
        file, embed = await self.build_profile(membro or i.user, i.user)
        if file:
            await i.followup.send(file=file, embed=embed)
        else:
            await i.followup.send(embed=embed)

    @app_commands.command(name="ranking", description="Top 10 do servidor por XP")
    @app_commands.guild_only()
    async def ranking(self, i: discord.Interaction):
        rows = await self.db.top(i.guild_id, 10)
        lines = [f"**{n}.** <@{r['user_id']}> — nível {level_from_xp(r['xp'])[0]} ({r['xp']} XP)"
                 for n, r in enumerate(rows, 1)]
        e = discord.Embed(title="\U0001f3c6 Ranking", description="\n".join(lines) or "Ninguém pontuou ainda.",
                          color=config.BRAND_COLOR)
        await i.response.send_message(embed=e, allowed_mentions=discord.AllowedMentions.none())

    # ---------------- personalização ----------------
    @app_commands.command(name="bio", description="Define sua biografia (até 160 caracteres)")
    @app_commands.guild_only()
    async def bio(self, i: discord.Interaction, texto: app_commands.Range[str, 0, 160]):
        await self.db.user(i.guild_id, i.user.id)
        await self.db.execute("UPDATE users SET bio=? WHERE guild_id=? AND user_id=?",
                              (texto, i.guild_id, i.user.id))
        await i.response.send_message("\U0001f4dd Biografia atualizada!", ephemeral=True)

    @app_commands.command(name="privacidade", description="Deixa seu perfil público ou privado")
    @app_commands.guild_only()
    @app_commands.choices(modo=[app_commands.Choice(name="Público", value=1),
                                app_commands.Choice(name="Privado", value=0)])
    async def privacidade(self, i: discord.Interaction, modo: app_commands.Choice[int]):
        await self.db.user(i.guild_id, i.user.id)
        await self.db.execute("UPDATE users SET public=? WHERE guild_id=? AND user_id=?",
                              (modo.value, i.guild_id, i.user.id))
        await i.response.send_message(f"\U0001f510 Seu perfil agora é **{modo.name.lower()}**.", ephemeral=True)

    @app_commands.command(name="preferencias", description="Cor do cartão e avisos de nível")
    @app_commands.guild_only()
    @app_commands.choices(cor=[app_commands.Choice(name=k.capitalize(), value=k) for k in ACCENTS])
    async def preferencias(self, i: discord.Interaction, cor: app_commands.Choice[str] | None = None,
                           avisos_de_nivel: bool | None = None):
        await self.db.user(i.guild_id, i.user.id)
        if cor:
            await self.db.execute("UPDATE users SET accent=? WHERE guild_id=? AND user_id=?",
                                  (cor.value, i.guild_id, i.user.id))
        if avisos_de_nivel is not None:
            await self.db.execute("UPDATE users SET notify=? WHERE guild_id=? AND user_id=?",
                                  (int(avisos_de_nivel), i.guild_id, i.user.id))
        await i.response.send_message("\u2699\ufe0f Preferências salvas!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Profile(bot))
