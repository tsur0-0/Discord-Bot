import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlparse

import aiohttp
import discord
from discord.ext import commands, tasks

log = logging.getLogger("social_watch")
ATOM = "{http://www.w3.org/2005/Atom}"
POLL_SECONDS = 300


def _text(element, path):
    node = element.find(path)
    return (node.text or "").strip() if node is not None else ""


def parse_feed(xml_text):
    """Lê feeds Atom/RSS genéricos; retorna itens em ordem do feed."""
    root = ET.fromstring(xml_text)
    items = root.findall(f".//{ATOM}entry") or root.findall(".//item")
    results = []
    for item in items[:10]:
        title = _text(item, f"{ATOM}title") or _text(item, "title") or "Nova publicação"
        item_id = (_text(item, f"{ATOM}id") or _text(item, "guid")
                   or _text(item, f"{ATOM}link") or _text(item, "link"))
        link_node = item.find(f"{ATOM}link")
        link = (link_node.attrib.get("href", "") if link_node is not None else "") or _text(item, "link")
        if not link and item_id.startswith("http"):
            link = item_id
        if not item_id:
            item_id = link or hashlib.sha256((title + ET.tostring(item, encoding="unicode")).encode()).hexdigest()
        if link:
            results.append({"id": item_id, "title": title, "url": link})
    return results


class SocialWatch(commands.Cog):
    """Monitora feeds de criadores e envia publicações novas ao Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS social_watch_seen(
                guild_id INTEGER NOT NULL,
                profile_key TEXT NOT NULL,
                item_id TEXT NOT NULL,
                PRIMARY KEY(guild_id, profile_key, item_id)
            )
        """)
        self.poll.start()

    async def cog_unload(self):
        self.poll.cancel()
        if self.session and not self.session.closed:
            await self.session.close()

    async def _session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=20, connect=8)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "JulinhaChan/1.7 (+social feed monitor)"}
            )
        return self.session

    async def _youtube_channel_id(self, handle):
        """Resolve o ID UC de um canal pelo handle quando ele não foi informado."""
        username = handle.strip().lstrip("@").strip("/")
        if not username:
            return ""
        try:
            session = await self._session()
            async with session.get(f"https://www.youtube.com/@{quote(username, safe='._-')}") as response:
                if response.status != 200:
                    log.warning("Não foi possível resolver o canal YouTube %s: HTTP %s", handle, response.status)
                    return ""
                page = await response.text()
            match = re.search(r'"(?:channelId|externalId|browseId|channel_id)"\s*:\s*"(UC[^"]+)"', page)
            if not match:
                log.warning("A página do YouTube de %s não continha channelId.", handle)
                return ""
            return match.group(1)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("Falha ao resolver o canal YouTube %s: %r", handle, exc)
            return ""

    async def _candidate_feeds(self, profile, platform, handle):
        """Monta fontes primárias e alternativas conhecidas para cada plataforma."""
        configured = str(profile.get("feed_url", "")).strip()
        candidates = [configured] if configured else []
        name = handle.strip().lstrip("@").strip("/")
        encoded_name = quote(name, safe="._-@")

        if platform.lower() == "youtube":
            channel_id = str(profile.get("channel_id", "")).strip()
            if not channel_id:
                channel_id = await self._youtube_channel_id(handle)
            if channel_id.startswith("UC"):
                candidates.extend([
                    f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={quote(channel_id, safe='')}",
                    f"https://www.youtube.com/feeds/videos.xml?channel_id={quote(channel_id, safe='')}",
                    f"https://hub.slarker.me/youtube/channel/{quote(channel_id, safe='')}",
                ])
            elif name:
                candidates.append(f"https://hub.slarker.me/youtube/user/{encoded_name}")
        elif platform.lower() == "instagram" and name:
            # RSSHub documenta estas rotas alternativas; a disponibilidade depende
            # dos limites e das proteções atuais do Instagram.
            candidates.extend([
                f"https://hub.slarker.me/picuki/profile/{encoded_name}",
                f"https://hub.slarker.me/instagram/2/user/{encoded_name}",
            ])
        elif platform.lower() == "tiktok" and name:
            candidates.append(f"https://hub.slarker.me/tiktok/user/{encoded_name}/true")

        # Preserva a ordem e remove URLs duplicadas.
        return list(dict.fromkeys(url for url in candidates if url and urlparse(url).scheme == "https"))

    async def _fetch_entries(self, urls, handle):
        """Tenta as fontes em sequência e devolve a primeira que contenha um feed válido."""
        session = await self._session()
        errors = []
        for url in urls:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        errors.append(f"{url} -> HTTP {response.status}")
                        continue
                    xml_text = await response.text()
                entries = parse_feed(xml_text)
                if entries:
                    if url != urls[0]:
                        log.info("Feed alternativo funcionou para %s: %s", handle, url)
                    return entries
                errors.append(f"{url} -> feed vazio")
            except (aiohttp.ClientError, asyncio.TimeoutError, ET.ParseError, ValueError) as exc:
                errors.append(f"{url} -> {type(exc).__name__}: {exc!r}")
        if errors:
            log.warning("Nenhuma fonte funcionou para %s. Tentativas: %s", handle, " | ".join(errors))
        return []

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll(self):
        for guild in list(self.bot.guilds):
            # "default" permite iniciar sem criar server_settings.json.
            cfg = self.bot.db.file_settings.get(
                str(guild.id), self.bot.db.file_settings.get("default", {})
            )
            social = cfg.get("social_watch", {})
            channel_id = social.get("channel_id")
            profiles = social.get("profiles", [])
            if not channel_id or not isinstance(profiles, list):
                continue
            channel = guild.get_channel(int(channel_id)) if str(channel_id).isdigit() else None
            if channel is None:
                continue
            for profile in profiles:
                if not isinstance(profile, dict) or profile.get("enabled", True) is False:
                    continue
                platform = str(profile.get("platform", "Social")).strip()
                handle = str(profile.get("handle", "perfil")).strip()
                try:
                    candidates = await self._candidate_feeds(profile, platform, handle)
                    if not candidates:
                        log.warning("Nenhuma URL de feed configurada ou encontrada para %s (%s).", handle, platform)
                        continue
                    entries = await self._fetch_entries(candidates, handle)
                except (aiohttp.ClientError, asyncio.TimeoutError, ET.ParseError, ValueError) as exc:
                    log.warning("Falha ao consultar perfil %s (%s): %r", handle, platform, exc)
                    continue

                if not entries:
                    continue

                # A chave é estável mesmo quando uma fonte alternativa passa a funcionar.
                profile_key = f"{platform.lower()}:{handle.lower()}"
                row = await self.bot.db.one(
                    "SELECT 1 FROM social_watch_seen WHERE guild_id=? AND profile_key=? LIMIT 1",
                    (guild.id, profile_key)
                )
                if row is None:
                    for item in entries:
                        await self.bot.db.execute(
                            "INSERT OR IGNORE INTO social_watch_seen(guild_id,profile_key,item_id) VALUES(?,?,?)",
                            (guild.id, profile_key, item["id"])
                        )
                    log.info("Feed inicial registrado para %s (%s); avisos de novas publicações habilitados.", handle, platform)
                    continue

                fresh = []
                for item in reversed(entries):
                    existing = await self.bot.db.one(
                        "SELECT 1 FROM social_watch_seen WHERE guild_id=? AND profile_key=? AND item_id=?",
                        (guild.id, profile_key, item["id"])
                    )
                    if existing is None:
                        fresh.append(item)
                        await self.bot.db.execute(
                            "INSERT OR IGNORE INTO social_watch_seen(guild_id,profile_key,item_id) VALUES(?,?,?)",
                            (guild.id, profile_key, item["id"])
                        )
                for item in fresh[-5:]:
                    embed = discord.Embed(
                        title=f"\U0001f4e2 Nova publicação · {platform}",
                        description=f"**{handle}** publicou algo novo.\n\n[{item['title'][:200]}]({item['url']})",
                        color=0x5865F2,
                    )
                    embed.add_field(name="Abrir publicação", value=f"[Ver agora]({item['url']})", inline=False)
                    embed.set_footer(text="Julinha Chan • monitor de perfis v1.7")
                    try:
                        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                    except discord.HTTPException as exc:
                        log.warning("Não foi possível enviar aviso em %s: %s", channel_id, exc)

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(SocialWatch(bot))
