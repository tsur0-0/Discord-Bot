import asyncio
import time
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
from logservice import fmt_log
from utils import images
from utils.data import LOG_CATEGORIES, PAGES
from utils.leveling import level_from_xp

PERMS = {
    "mod": ("kick_members", "ban_members", "moderate_members"),
    "roles": ("manage_roles",),
    "logs": ("view_audit_log",),
    "config": ("manage_guild",),
}
ACTION_PERM = {"warn": "moderate_members", "timeout": "moderate_members", "untimeout": "moderate_members",
               "kick": "kick_members", "ban": "ban_members"}
ACTION_TITLE = {"warn": "Avisar membro", "timeout": "Silenciar membro", "kick": "Expulsar membro",
                "ban": "Banir membro"}


def allowed(member: discord.Member, key: str) -> bool:
    need = PERMS.get(key)
    return True if not need else any(getattr(member.guild_permissions, p) for p in need)


def check_target(actor: discord.Member, target: discord.Member, guild: discord.Guild, action: str):
    """Retorna uma mensagem de erro, ou None se a ação é permitida."""
    perm = ACTION_PERM[action]
    if not getattr(actor.guild_permissions, perm):
        return "Você não tem permissão para isso."
    if target.id == actor.id:
        return "Você não pode agir sobre si mesmo."
    if target.id == guild.owner_id:
        return "Não é possível agir sobre o dono do servidor."
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return "O cargo do alvo é igual ou maior que o seu."
    if action != "warn":
        me = guild.me
        if not getattr(me.guild_permissions, perm):
            return "Eu não tenho a permissão necessária."
        if target.top_role >= me.top_role:
            return "Meu cargo é igual ou menor que o do alvo."
    return None


# ------------------------------------------------------------------ modais
class ActionModal(discord.ui.Modal):
    def __init__(self, pv, action):
        super().__init__(title=ACTION_TITLE[action])
        self.pv, self.action, self.minutes = pv, action, None
        if action == "timeout":
            self.minutes = discord.ui.TextInput(label="Duração (minutos)", default="10", max_length=5)
            self.add_item(self.minutes)
        self.reason = discord.ui.TextInput(label="Motivo", required=False, max_length=200,
                                           style=discord.TextStyle.paragraph)
        self.add_item(self.reason)

    async def on_submit(self, i: discord.Interaction):
        mins = 10
        if self.minutes:
            try:
                mins = max(1, min(40320, int(str(self.minutes))))
            except ValueError:
                return await i.response.send_message("Duração inválida.", ephemeral=True)
        await self.pv.do_action(i, self.action, str(self.reason), mins)


class LevelModal(discord.ui.Modal, title="Vincular cargo a um nível"):
    level = discord.ui.TextInput(label="Nível (1 a 200)", max_length=3)

    def __init__(self, pv):
        super().__init__()
        self.pv = pv

    async def on_submit(self, i: discord.Interaction):
        try:
            lv = int(str(self.level))
            assert 1 <= lv <= 200
        except (ValueError, AssertionError):
            return await i.response.send_message("Nível inválido.", ephemeral=True)
        await self.pv.bind_role(i, lv)


# ------------------------------------------------------------------ itens
class NavButton(discord.ui.Button):
    def __init__(self, label, delta=0, home=False):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, row=0)
        self.delta, self.home = delta, home

    async def callback(self, i):
        v = self.view
        v.page = 0 if self.home else (v.page + self.delta) % len(PAGES)
        await v.refresh(i)


class PageSelect(discord.ui.Select):
    def __init__(self, page):
        opts = [discord.SelectOption(label=n, value=str(idx), emoji=e, default=idx == page)
                for idx, (_, n, e) in enumerate(PAGES)]
        super().__init__(placeholder="Categorias", options=opts, row=1)

    async def callback(self, i):
        self.view.page = int(self.values[0])
        await self.view.refresh(i)


class CardButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Gerar meu cartão", style=discord.ButtonStyle.success, emoji="\U0001faaa", row=2)

    async def callback(self, i):
        await i.response.defer(ephemeral=True, thinking=True)
        cog = self.view.bot.get_cog("Profile")
        file, embed = await cog.build_profile(i.user, i.user)
        await i.followup.send(file=file, embed=embed, ephemeral=True)


class MemberSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione um membro", row=2)

    async def callback(self, i):
        self.view.member_id = self.values[0].id
        await self.view.refresh(i)


class ActionButton(discord.ui.Button):
    STYLES = {"warn": discord.ButtonStyle.primary, "timeout": discord.ButtonStyle.primary,
              "untimeout": discord.ButtonStyle.secondary, "kick": discord.ButtonStyle.danger,
              "ban": discord.ButtonStyle.danger}
    LABELS = {"warn": "Avisar", "timeout": "Silenciar", "untimeout": "Tirar silêncio",
              "kick": "Expulsar", "ban": "Banir"}

    def __init__(self, action):
        super().__init__(label=self.LABELS[action], style=self.STYLES[action], row=3)
        self.action = action

    async def callback(self, i):
        v = self.view
        if not allowed(i.user, "mod"):
            return await i.response.send_message("\U0001f512 Sem permissão de moderação.", ephemeral=True)
        if not v.member_id:
            return await i.response.send_message("Selecione um membro primeiro.", ephemeral=True)
        if self.action == "untimeout":
            return await v.do_action(i, "untimeout", "", 0)
        await i.response.send_modal(ActionModal(v, self.action))


class RoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione um cargo", row=2)

    async def callback(self, i):
        self.view.role_id = self.values[0].id
        await self.view.refresh(i)


class BindButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Vincular a um nível…", style=discord.ButtonStyle.success, row=3)

    async def callback(self, i):
        v = self.view
        if not v.require(i, "roles"):
            return await i.response.send_message("\U0001f512 Requer **Gerenciar Cargos**.", ephemeral=True)
        if not v.role_id:
            return await i.response.send_message("Selecione um cargo primeiro.", ephemeral=True)
        await i.response.send_modal(LevelModal(v))


class UnbindButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Remover vínculo", style=discord.ButtonStyle.danger, row=3)

    async def callback(self, i):
        v = self.view
        if not v.require(i, "roles"):
            return await i.response.send_message("\U0001f512 Requer **Gerenciar Cargos**.", ephemeral=True)
        if not v.role_id:
            return await i.response.send_message("Selecione um cargo primeiro.", ephemeral=True)
        await v.bot.db.execute("DELETE FROM level_roles WHERE guild_id=? AND role_id=?", (v.guild.id, v.role_id))
        await v.bot.logs.record(v.guild, "config:cargo_nivel", actor=i.user,
                                details=f"Vínculo do cargo <@&{v.role_id}> removido")
        await v.refresh(i)


class FilterSelect(discord.ui.Select):
    def __init__(self, current):
        opts = [discord.SelectOption(label="Todos", value="all", default=current is None)] + [
            discord.SelectOption(label=n, value=k, default=k == current) for k, n in LOG_CATEGORIES.items()]
        super().__init__(placeholder="Filtrar por tipo", options=opts, row=2)

    async def callback(self, i):
        if not self.view.require(i, "logs"):
            return await i.response.send_message("\U0001f512 Sem permissão.", ephemeral=True)
        self.view.log_filter = None if self.values[0] == "all" else self.values[0]
        await self.view.refresh(i)


class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Atualizar", emoji="\U0001f504", style=discord.ButtonStyle.secondary, row=3)

    async def callback(self, i):
        await self.view.refresh(i)


class ConfigChannel(discord.ui.ChannelSelect):
    def __init__(self, key, placeholder, row):
        super().__init__(channel_types=[discord.ChannelType.text], placeholder=placeholder, row=row)
        self.key = key

    async def callback(self, i):
        v = self.view
        if not v.require(i, "config"):
            return await i.response.send_message("\U0001f512 Requer **Gerenciar Servidor**.", ephemeral=True)
        ch = self.values[0]
        await v.bot.db.set(v.guild.id, self.key, ch.id)
        await v.bot.logs.record(v.guild, "config:alterada", actor=i.user, details=f"{self.key} = <#{ch.id}>")
        await v.refresh(i)


class ToggleSelect(discord.ui.Select):
    OPTS = [("xp_enabled", "Sistema de XP", True), ("affinity_enabled", "Afinidade e amizade", False),
            ("fun_enabled", "Diversão e easter eggs", True)]

    def __init__(self, state):
        opts = [discord.SelectOption(label=l, value=k, default=state[k]) for k, l, _ in self.OPTS]
        super().__init__(placeholder="Recursos ativos", min_values=0, max_values=len(opts), options=opts, row=4)

    async def callback(self, i):
        v = self.view
        if not v.require(i, "config"):
            return await i.response.send_message("\U0001f512 Requer **Gerenciar Servidor**.", ephemeral=True)
        for k, _, _ in self.OPTS:
            await v.bot.db.set(v.guild.id, k, int(k in self.values))
        await v.bot.logs.record(v.guild, "config:alterada", actor=i.user,
                                details="Recursos ativos: " + (", ".join(self.values) or "nenhum"))
        await v.refresh(i)


# ------------------------------------------------------------------ view principal
class PanelView(discord.ui.View):
    def __init__(self, bot, owner: discord.Member, guild: discord.Guild, page=0):
        super().__init__(timeout=300)
        self.bot, self.owner, self.guild, self.page = bot, owner, guild, page
        self.member_id = self.role_id = self.log_filter = None
        self.message = None

    @property
    def key(self):
        return PAGES[self.page][0]

    def require(self, i, key):
        return allowed(i.user, key)

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.owner.id:
            await i.response.send_message("Esse painel é de outra pessoa. Use **/menu** para abrir o seu.",
                                          ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_error(self, i, error, item):
        await self.bot.db.log_error("painel", f"{item}: {error!r}")
        msg = "\U0001f4a5 Algo deu errado no painel."
        if i.response.is_done():
            await i.followup.send(msg, ephemeral=True)
        else:
            await i.response.send_message(msg, ephemeral=True)

    # ---- montagem ----
    async def build_items(self):
        self.clear_items()
        self.add_item(NavButton("◀ Voltar", -1))
        self.add_item(NavButton("\U0001f3e0 Início", home=True))
        self.add_item(NavButton("Avançar ▶", +1))
        self.add_item(PageSelect(self.page))
        key = self.key
        if key == "profile":
            self.add_item(CardButton())
        elif key == "mod" and allowed(self.owner, "mod"):
            self.add_item(MemberSelect())
            for a in ("warn", "timeout", "untimeout", "kick", "ban"):
                self.add_item(ActionButton(a))
        elif key == "roles" and allowed(self.owner, "roles"):
            self.add_item(RoleSelect())
            self.add_item(BindButton())
            self.add_item(UnbindButton())
        elif key == "logs" and allowed(self.owner, "logs"):
            self.add_item(FilterSelect(self.log_filter))
            self.add_item(RefreshButton())
        elif key == "config" and allowed(self.owner, "config"):
            self.add_item(ConfigChannel("log_channel", "Canal de logs", 2))
            self.add_item(ConfigChannel("welcome_channel", "Canal de boas-vindas", 3))
            db, gid = self.bot.db, self.guild.id
            self.add_item(ToggleSelect({k: await db.flag(gid, k, d) for k, _, d in ToggleSelect.OPTS}))

    def base_slots(self):
        return [{"icon": k, "label": n} for k, n, _ in PAGES]

    async def render(self):
        key, name, _ = PAGES[self.page]
        slots = self.base_slots()
        if key in PERMS and not allowed(self.owner, key):
            embed = discord.Embed(title=f"{name}", description="\U0001f512 Você não tem permissão para usar esta área.")
        else:
            embed, extra = await getattr(self, f"page_{key}")()
            if extra:
                slots += [None, None] + extra
        embed.color = config.BRAND_COLOR
        buf = await asyncio.to_thread(images.render_inventory, f"{self.guild.name} — {name}", slots, self.page)
        embed.set_image(url="attachment://panel.png")
        embed.set_footer(text=f"{config.BOT_NAME} v{config.BOT_VERSION}")
        return embed, discord.File(buf, "panel.png")

    async def refresh(self, i: discord.Interaction):
        await i.response.defer()
        await self.build_items()
        embed, file = await self.render()
        await i.edit_original_response(embed=embed, attachments=[file], view=self)

    # ---- páginas ----
    async def page_home(self):
        lines = "\n".join(f"{e} **{n}**" for _, n, e in PAGES[1:])
        return discord.Embed(title="Menu principal",
                             description=f"Escolha uma categoria nos botões ou no menu abaixo.\n\n{lines}"), None

    async def page_profile(self):
        db, gid, uid = self.bot.db, self.guild.id, self.owner.id
        row = await db.user(gid, uid)
        lvl, prog, need = level_from_xp(row["xp"])
        e = discord.Embed(title="Seu perfil", description=(
            f"**Nível {lvl}** — {prog}/{need} XP\n**Ranking:** #{await db.rank(gid, uid)}\n"
            f"**Visibilidade:** {'público' if row['public'] else 'privado'}\n"
            f"**XP total:** {row['xp']}\n\n"
            "Comandos: `/perfil` `/bio` `/privacidade` `/preferencias`"))
        return e, [{"icon": "member", "label": "Nível", "count": lvl},
                   {"icon": "logs", "label": "Mensagens", "count": row["messages"]},
                   {"icon": "logs", "label": "XP total", "count": row["xp"]}]

    async def page_mod(self):
        e = discord.Embed(title="Moderação de membros")
        m = self.guild.get_member(self.member_id) if self.member_id else None
        if m:
            row = await self.bot.db.user(self.guild.id, m.id)
            until = f"\nSilenciado até <t:{int(m.timed_out_until.timestamp())}:R>" if m.timed_out_until else ""
            e.description = (f"**Alvo:** {m.mention} (`{m.id}`)\n**Avisos:** {row['warns']}\n"
                             f"**Entrou:** <t:{int(m.joined_at.timestamp())}:R>{until}")
            e.set_thumbnail(url=m.display_avatar.url)
        else:
            e.description = "Selecione um membro no menu e escolha uma ação.\nTodas as ações respeitam a hierarquia de cargos."
        return e, None

    async def page_roles(self):
        rows = await self.bot.db.all("SELECT level,role_id FROM level_roles WHERE guild_id=? ORDER BY level",
                                     (self.guild.id,))
        lines = [f"Nível **{r['level']}** → <@&{r['role_id']}>" for r in rows]
        sel = f"\n\n**Selecionado:** <@&{self.role_id}>" if self.role_id else ""
        return discord.Embed(title="Cargos por nível", description=(
            "\n".join(lines) or "Nenhum cargo vinculado a níveis ainda.") + sel), None

    async def page_logs(self):
        db, gid, day = self.bot.db, self.guild.id, int(time.time()) - 86400
        rows = await db.search_logs(gid, category=self.log_filter, limit=10)
        text = "\n".join(fmt_log(r) for r in rows) or "Nenhum registro."
        e = discord.Embed(title="Logs recentes" + (f" — {LOG_CATEGORIES[self.log_filter]}" if self.log_filter else ""),
                          description=text[:3500])
        return e, [{"icon": "member", "label": "Membros", "count": self.guild.member_count},
                   {"icon": "logs", "label": "Mensagens contadas", "count": await db.total_messages(gid)},
                   {"icon": "config", "label": "Eventos em 24h", "count": await db.count_logs(gid, day)},
                   {"icon": "mod", "label": "Punições em 24h", "count": await db.count_logs(gid, day, "punicao")},
                   {"icon": "tnt", "label": "Erros em 24h", "count": await db.count_errors(day)}]

    async def page_config(self):
        db, gid = self.bot.db, self.guild.id

        def ch(v):
            return f"<#{v}>" if v else "não definido"
        onoff = lambda b: "ligado" if b else "desligado"
        e = discord.Embed(title="Configurações do servidor", description=(
            f"**Canal de logs:** {ch(await db.get(gid, 'log_channel'))}\n"
            f"**Boas-vindas:** {ch(await db.get(gid, 'welcome_channel'))}\n"
            f"**XP:** {onoff(await db.flag(gid, 'xp_enabled', True))} "
            f"(x{await db.number(gid, 'xp_mult', 1.0)})\n"
            f"**Afinidade:** {onoff(await db.flag(gid, 'affinity_enabled', False))}\n"
            f"**Diversão:** {onoff(await db.flag(gid, 'fun_enabled', True))}\n"
            f"**Mensagens aleatórias:** {int(await db.number(gid, 'random_chance', 0))}%\n\n"
            "Mais opções: `/config` (mensagens, respostas, multiplicador)."))
        return e, None

    async def page_fun(self):
        return discord.Embed(title="Diversão", description=(
            "`/meme` `/piada` `/bola8` `/dado` `/abraco`\n`/afinidade` `/amigos` (se ligado)\n\n"
            "Dizem que este servidor esconde segredos... \U0001f440")), None

    # ---- ações ----
    async def do_action(self, i: discord.Interaction, action, reason, minutes=10):
        guild = self.guild
        member = guild.get_member(self.member_id)
        if member is None:
            return await i.response.send_message("Membro não encontrado no servidor.", ephemeral=True)
        err = check_target(i.user, member, guild, action)
        if err:
            return await i.response.send_message(f"\U0001f6ab {err}", ephemeral=True)
        tag = f"[por {i.user.id}] {reason or 'sem motivo'}"
        try:
            if action == "kick":
                await member.kick(reason=tag)
                msg = f"\U0001f462 {member} foi expulso."
            elif action == "ban":
                await guild.ban(member, reason=tag, delete_message_seconds=0)
                msg = f"\U0001f528 {member} foi banido."
            elif action == "timeout":
                await member.timeout(timedelta(minutes=minutes), reason=tag)
                msg = f"\U0001f507 {member} silenciado por {minutes} min."
            elif action == "untimeout":
                await member.timeout(None, reason=tag)
                msg = f"\U0001f50a Silêncio de {member} removido."
            else:  # warn (não aparece na auditoria do Discord, então registramos direto)
                await self.bot.db.user(guild.id, member.id)
                await self.bot.db.execute("UPDATE users SET warns=warns+1 WHERE guild_id=? AND user_id=?",
                                          (guild.id, member.id))
                await self.bot.logs.record(guild, "punicao:aviso", actor=i.user, target=member,
                                           details=f"Motivo: {reason or 'sem motivo'}", title="Aviso")
                try:
                    await member.send(f"\u26a0\ufe0f Você recebeu um aviso em **{guild.name}**: {reason or 'sem motivo'}")
                except discord.HTTPException:
                    pass
                msg = f"\u26a0\ufe0f {member} avisado."
        except discord.Forbidden:
            return await i.response.send_message("\U0001f6ab O Discord recusou a ação (permissões/hierarquia).",
                                                 ephemeral=True)
        await i.response.send_message(msg, ephemeral=True)

    async def bind_role(self, i: discord.Interaction, level: int):
        if not allowed(i.user, "roles"):
            return await i.response.send_message("\U0001f512 Requer **Gerenciar Cargos**.", ephemeral=True)
        role = self.guild.get_role(self.role_id)
        me = self.guild.me
        if role is None or role.is_default() or role.managed:
            return await i.response.send_message("Esse cargo não pode ser usado.", ephemeral=True)
        if i.user.id != self.guild.owner_id and role >= i.user.top_role:
            return await i.response.send_message("O cargo é igual ou maior que o seu.", ephemeral=True)
        if role >= me.top_role:
            return await i.response.send_message("Meu cargo precisa estar acima desse cargo.", ephemeral=True)
        await self.bot.db.execute(
            "INSERT INTO level_roles(guild_id,level,role_id) VALUES(?,?,?) "
            "ON CONFLICT(guild_id,role_id) DO UPDATE SET level=excluded.level", (self.guild.id, level, role.id))
        await self.bot.logs.record(self.guild, "config:cargo_nivel", actor=i.user,
                                   details=f"{role.mention} vinculado ao nível {level}")
        await i.response.send_message(f"\U0001f6e1\ufe0f {role.mention} será dado no nível **{level}**.", ephemeral=True,
                                      allowed_mentions=discord.AllowedMentions.none())


class Panels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="menu", description="Abre o painel principal")
    @app_commands.guild_only()
    async def menu(self, i: discord.Interaction):
        await i.response.defer()
        view = PanelView(self.bot, i.user, i.guild)
        await view.build_items()
        embed, file = await view.render()
        view.message = await i.followup.send(embed=embed, file=file, view=view)


async def setup(bot):
    await bot.add_cog(Panels(bot))
