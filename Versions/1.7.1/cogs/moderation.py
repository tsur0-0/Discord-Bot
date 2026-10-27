from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.GroupCog, name="moderar", description="Ferramentas de moderação"):
    def __init__(self, bot):
        self.bot = bot

    async def _target_check(self, i: discord.Interaction, member: discord.Member, permission: str):
        actor = i.user
        guild = i.guild
        if not getattr(actor.guild_permissions, permission):
            await i.response.send_message("Você não tem permissão para essa ação.", ephemeral=True)
            return False
        if member.id == actor.id or member.id == guild.owner_id:
            await i.response.send_message("Não é possível aplicar essa ação a esse membro.", ephemeral=True)
            return False
        if actor.id != guild.owner_id and member.top_role >= actor.top_role:
            await i.response.send_message("O cargo do membro é igual ou superior ao seu.", ephemeral=True)
            return False
        if member.top_role >= guild.me.top_role:
            await i.response.send_message("O cargo da Julinha precisa estar acima do cargo do membro.", ephemeral=True)
            return False
        if not getattr(guild.me.guild_permissions, permission):
            await i.response.send_message("A Julinha não tem a permissão necessária.", ephemeral=True)
            return False
        return True

    async def _record(self, i, kind, member, reason):
        await self.bot.logs.record(i.guild, kind, actor=i.user, target=member,
                                   details=f"Motivo: {reason or 'não informado'}")

    @app_commands.command(name="advertir", description="Registra um aviso para um membro")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def advertir(self, i: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        if not await self._target_check(i, membro, "moderate_members"):
            return
        await self.bot.db.user(i.guild_id, membro.id)
        await self.bot.db.execute("UPDATE users SET warns=warns+1 WHERE guild_id=? AND user_id=?", (i.guild_id, membro.id))
        await self._record(i, "punicao:aviso", membro, motivo)
        try:
            await membro.send(f"Você recebeu um aviso em **{i.guild.name}**. Motivo: {motivo}")
        except discord.HTTPException:
            pass
        await i.response.send_message(f"Aviso registrado para {membro.mention}.", ephemeral=True)

    @app_commands.command(name="timeout", description="Silencia temporariamente um membro")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(self, i: discord.Interaction, membro: discord.Member,
                      minutos: app_commands.Range[int, 1, 40320] = 10, motivo: str = "Não informado"):
        if not await self._target_check(i, membro, "moderate_members"):
            return
        try:
            await membro.timeout(timedelta(minutes=minutos), reason=f"[por {i.user.id}] {motivo}")
        except discord.Forbidden:
            return await i.response.send_message("O Discord recusou a ação. Verifique as permissões e os cargos.", ephemeral=True)
        await self._record(i, "punicao:timeout", membro, motivo)
        await i.response.send_message(f"{membro.mention} recebeu timeout por {minutos} minuto(s).", ephemeral=True)

    @app_commands.command(name="retirar_timeout", description="Remove o timeout de um membro")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def retirar_timeout(self, i: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        if not await self._target_check(i, membro, "moderate_members"):
            return
        try:
            await membro.timeout(None, reason=f"[por {i.user.id}] {motivo}")
        except discord.Forbidden:
            return await i.response.send_message("O Discord recusou a ação. Verifique as permissões e os cargos.", ephemeral=True)
        await self._record(i, "punicao:timeout_removido", membro, motivo)
        await i.response.send_message(f"Timeout removido de {membro.mention}.", ephemeral=True)

    @app_commands.command(name="expulsar", description="Expulsa um membro do servidor")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def expulsar(self, i: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        if not await self._target_check(i, membro, "kick_members"):
            return
        try:
            await membro.kick(reason=f"[por {i.user.id}] {motivo}")
        except discord.Forbidden:
            return await i.response.send_message("O Discord recusou a ação. Verifique as permissões e os cargos.", ephemeral=True)
        await self._record(i, "punicao:expulsao", membro, motivo)
        await i.response.send_message(f"{membro} foi expulso do servidor.", ephemeral=True)

    @app_commands.command(name="banir", description="Bane um membro do servidor")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def banir(self, i: discord.Interaction, membro: discord.Member, motivo: str = "Não informado"):
        if not await self._target_check(i, membro, "ban_members"):
            return
        try:
            await i.guild.ban(membro, reason=f"[por {i.user.id}] {motivo}", delete_message_seconds=0)
        except discord.Forbidden:
            return await i.response.send_message("O Discord recusou a ação. Verifique as permissões e os cargos.", ephemeral=True)
        await self._record(i, "punicao:banimento", membro, motivo)
        await i.response.send_message(f"{membro} foi banido do servidor.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
