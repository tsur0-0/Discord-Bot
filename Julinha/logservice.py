import time
import discord

COLORS = {
    "mensagem": 0x3498DB, "membro": 0x2ECC71, "punicao": 0xE74C3C, "cargo": 0x9B59B6,
    "canal": 0xF1C40F, "config": 0x95A5A6, "comando": 0x1ABC9C, "auditoria": 0x7F8C8D,
}


def fmt_log(r) -> str:
    who = f" por <@{r['actor_id']}>" if r["actor_id"] else ""
    to = f" em <@{r['target_id']}>" if r["target_id"] else ""
    det = (r["details"] or "").replace("\n", " ")[:120]
    return f"<t:{r['ts']}:R> `{r['type']}`{who}{to} {det}"


class LogService:
    """Grava no banco e (se configurado) envia para o canal de logs do servidor."""

    def __init__(self, bot):
        self.bot = bot

    async def record(self, guild, type_, actor=None, target=None, details="", title=None):
        actor_id = getattr(actor, "id", actor)
        target_id = getattr(target, "id", target)
        details = (details or "")[:1500]
        await self.bot.db.add_log(guild.id, int(time.time()), type_, actor_id, target_id, details)

        cid = await self.bot.db.get(guild.id, "log_channel")
        ch = guild.get_channel(int(cid)) if cid else None
        if not ch or not ch.permissions_for(guild.me).send_messages:
            return
        cat = type_.split(":")[0]
        embed = discord.Embed(title=title or type_, description=details[:1800] or "—",
                              color=COLORS.get(cat, 0x95A5A6),
                              timestamp=discord.utils.utcnow())
        if actor_id:
            embed.add_field(name="Responsável", value=f"<@{actor_id}> (`{actor_id}`)")
        if target_id:
            embed.add_field(name="Alvo", value=f"<@{target_id}> (`{target_id}`)")
        embed.set_footer(text=type_)
        try:
            await ch.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
