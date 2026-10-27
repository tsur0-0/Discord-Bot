import re
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from logservice import fmt_log
from utils.data import LOG_CATEGORIES

A = discord.AuditLogAction

# ação de auditoria -> (categoria, descrição)
AUDIT_MAP = {}
for _name, _cat, _desc in [
    ("kick", "punicao", "Expulsão"), ("ban", "punicao", "Banimento"), ("unban", "punicao", "Banimento removido"),
    ("member_role_update", "cargo", "Cargos de membro alterados"),
    ("member_update", "membro", "Membro alterado (apelido/silêncio)"),
    ("role_create", "cargo", "Cargo criado"), ("role_update", "cargo", "Cargo alterado"),
    ("role_delete", "cargo", "Cargo excluído"),
    ("channel_create", "canal", "Canal criado"), ("channel_update", "canal", "Canal alterado"),
    ("channel_delete", "canal", "Canal excluído"),
    ("overwrite_create", "canal", "Permissões de canal criadas"),
    ("overwrite_update", "canal", "Permissões de canal alteradas"),
    ("overwrite_delete", "canal", "Permissões de canal removidas"),
    ("message_delete", "mensagem", "Mensagem apagada por moderador"),
    ("message_bulk_delete", "mensagem", "Mensagens apagadas em massa"),
    ("guild_update", "config", "Servidor alterado"),
]:
    if hasattr(A, _name):
        AUDIT_MAP[getattr(A, _name)] = (_cat, _desc)


def short(v, n=80):
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def describe_target(t, fallback_id):
    if t is None:
        return f"ID {fallback_id}"
    if isinstance(t, (discord.Member, discord.User)):
        return f"{t} ({t.id})"
    if hasattr(t, "mention"):
        return t.mention
    return f"ID {getattr(t, 'id', fallback_id)}"


def diff(entry):
    try:
        b, a = dict(entry.before), dict(entry.after)
    except Exception:
        return ""
    parts = [f"{k}: {short(b.get(k))} → {short(a.get(k))}"
             for k in sorted(set(a) | set(b)) if b.get(k) != a.get(k)]
    return "\n".join(parts)[:900]


def parse_period(s: str):
    s = s.strip().lower()
    if s in ("tudo", "all", ""):
        return None
    m = re.fullmatch(r"(\d+)\s*([mhdw])", s)
    if not m:
        raise ValueError
    n, unit = int(m[1]), m[2]
    return int(time.time()) - n * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]


class Logs(commands.Cog):
    """Auditoria completa: mensagens, membros, punições, cargos, canais, configurações."""

    def __init__(self, bot):
        self.bot = bot

    def rec(self, *a, **k):
        return self.bot.logs.record(*a, **k)

    async def _is_log_channel(self, guild, channel_id):
        return str(channel_id) == await self.bot.db.get(guild.id, "log_channel")

    # ---------------- mensagens (precisam do intent message_content) ----------------
    @commands.Cog.listener()
    async def on_message_delete(self, m: discord.Message):
        if not m.guild or m.author.bot or await self._is_log_channel(m.guild, m.channel.id):
            return
        txt = short(m.content, 900) if m.content else "(sem texto)"
        extra = f"\nAnexos: {len(m.attachments)}" if m.attachments else ""
        await self.rec(m.guild, "mensagem:apagada", target=m.author,
                       details=f"Canal: {m.channel.mention}\nConteúdo: {txt}{extra}",
                       title="Mensagem apagada")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, p: discord.RawMessageDeleteEvent):
        if p.cached_message is not None or not p.guild_id:  # já tratada acima
            return
        guild = self.bot.get_guild(p.guild_id)
        if guild and not await self._is_log_channel(guild, p.channel_id):
            await self.rec(guild, "mensagem:apagada",
                           details=f"Canal: <#{p.channel_id}>\nConteúdo indisponível (mensagem fora do cache).",
                           title="Mensagem apagada")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot or before.content == after.content:
            return
        await self.rec(after.guild, "mensagem:editada", target=after.author,
                       details=f"Canal: {after.channel.mention} • [ir]({after.jump_url})\n"
                               f"Antes: {short(before.content, 450)}\nDepois: {short(after.content, 450)}",
                       title="Mensagem editada")

    # ---------------- entradas e saídas ----------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        age = int(member.created_at.timestamp())
        await self.rec(member.guild, "membro:entrou", target=member,
                       details=f"Conta criada <t:{age}:R>", title="Membro entrou")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = ", ".join(r.name for r in member.roles if not r.is_default()) or "nenhum"
        await self.rec(member.guild, "membro:saiu", target=member,
                       details=f"Cargos: {short(roles, 300)}", title="Membro saiu")

    # ---------------- auditoria (quem fez o quê) ----------------
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        guild = entry.guild
        cat, desc = AUDIT_MAP.get(entry.action, ("auditoria", entry.action.name))
        changes = diff(entry)
        if entry.action == A.member_update and "timed_out_until" in changes:
            cat, desc = "punicao", "Silenciamento (timeout) alterado"
        elif entry.action == A.member_update and "nick" in changes:
            desc = "Apelido alterado"

        actor_id = entry.user_id
        reason = entry.reason or ""
        via = ""
        if self.bot.user and actor_id == self.bot.user.id:
            m = re.match(r"\[por (\d+)\]\s*(.*)", reason)
            if m:  # ação feita pelo bot a pedido de um humano (painel)
                actor_id, reason = int(m[1]), m[2]
                via = " (via painel do bot)"
            else:
                via = " (ação automática do bot)"
        target_id = entry.target.id if isinstance(entry.target, (discord.Member, discord.User)) else None
        parts = [f"{desc}{via}", f"Alvo: {describe_target(entry.target, entry.target_id)}"]
        if reason:
            parts.append(f"Motivo: {short(reason, 200)}")
        if changes:
            parts.append(changes)
        await self.rec(guild, f"{cat}:{entry.action.name}", actor=actor_id, target=target_id,
                       details="\n".join(parts), title=desc)

    # ---------------- consultas ----------------
    @app_commands.command(name="logs", description="Pesquisa o histórico de eventos")
    @app_commands.guild_only()
    @app_commands.default_permissions(view_audit_log=True)
    @app_commands.describe(usuario="Responsável ou alvo", periodo="Ex.: 30m, 12h, 7d, 2w ou tudo",
                           categoria="Tipo de evento")
    @app_commands.choices(categoria=[app_commands.Choice(name=v, value=k) for k, v in LOG_CATEGORIES.items()])
    async def logs(self, i: discord.Interaction, usuario: discord.User | None = None, periodo: str = "24h",
                   categoria: app_commands.Choice[str] | None = None,
                   limite: app_commands.Range[int, 1, 25] = 15):
        if not i.user.guild_permissions.view_audit_log:
            return await i.response.send_message("\U0001f512 Requer **Ver registro de auditoria**.", ephemeral=True)
        try:
            since = parse_period(periodo)
        except ValueError:
            return await i.response.send_message("Período inválido. Use algo como `30m`, `12h`, `7d`, `2w` ou `tudo`.",
                                                 ephemeral=True)
        rows = await self.bot.db.search_logs(i.guild_id, usuario.id if usuario else None, since,
                                             categoria.value if categoria else None, limite)
        text = "\n".join(fmt_log(r) for r in rows) or "Nenhum registro encontrado."
        e = discord.Embed(title="\U0001f4d6 Logs", description=text[:4000], color=config.BRAND_COLOR)
        e.set_footer(text=f"{len(rows)} resultado(s) • período: {periodo}")
        await i.response.send_message(embed=e, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="erros", description="Histórico de erros e reconexões do bot")
    @app_commands.default_permissions(administrator=True)
    async def erros(self, i: discord.Interaction):
        is_admin = i.guild and i.user.guild_permissions.administrator
        if i.user.id not in config.OWNER_IDS and not is_admin:
            return await i.response.send_message("\U0001f512 Apenas donos do bot ou administradores.", ephemeral=True)
        rows = await self.bot.db.recent_errors(15)
        lines = [f"<t:{r['ts']}:R> `{r['kind']}` {short(r['details'].splitlines()[-1] if r['details'] else '', 100)}"
                 for r in rows]
        e = discord.Embed(title="\U0001f6e0\ufe0f Erros e reconexões", description="\n".join(lines) or "Nada registrado.",
                          color=0xC0392B)
        await i.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Logs(bot))
