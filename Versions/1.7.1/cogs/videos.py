import asyncio
import logging
import re
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger("videos")

# URLs de vídeos/publicações, não links de páginas iniciais dos serviços.
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
PLATFORMS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
    "instagram.com": "Instagram",
}


def video_platform(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        platform = next((name for domain, name in PLATFORMS.items()
                         if host == domain or host.endswith("." + domain)), None)
        if not platform:
            return None
        path = urlparse(url).path.lower()
        if platform == "YouTube":
            return platform if (host == "youtu.be" or path in ("/watch", "/live")
                                or path.startswith(("/shorts/", "/embed/", "/live/"))) else None
        if platform == "TikTok":
            return platform if re.search(r"/@[^/]+/video/\d+", path) else None
        if platform == "Instagram":
            return platform if re.match(r"/(reel|reels|p|tv)/[^/]+", path) else None
    except ValueError:
        return None
    return None


def clean_url(url: str) -> str:
    return url.rstrip(".,!?;:)]}")


def profile_matches(profile: str, author_name: str, author_url: str) -> bool:
    profile = profile.strip().lower().rstrip("/")
    name = (author_name or "").strip().lower()
    url = (author_url or "").strip().lower().rstrip("/")
    if not profile:
        return False
    if profile.startswith("http://") or profile.startswith("https://"):
        return url == profile or url.startswith(profile + "/")
    handle = profile.removeprefix("@")
    url_handle = urlparse(url).path.rstrip("/").split("/")[-1].lower().removeprefix("@")
    return handle == url_handle or handle == name.removeprefix("@") or profile == name


async def get_creator(url: str) -> tuple[str, str]:
    # Os endpoints oEmbed são públicos e não exigem token da Julinha.
    platform = video_platform(url)
    endpoints = {
        "YouTube": "https://www.youtube.com/oembed",
        "TikTok": "https://www.tiktok.com/oembed",
        "Instagram": "https://www.instagram.com/api/v1/oembed/",
    }
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "JulinhaChan/1.5"}) as session:
        async with session.get(endpoints[platform], params={"url": url, "format": "json"}) as response:
            if response.status != 200:
                raise RuntimeError(f"oEmbed respondeu HTTP {response.status}")
            data = await response.json(content_type=None)
            return str(data.get("author_name", "")), str(data.get("author_url", ""))


class VideoWatch(commands.Cog):
    """Detecta links de vídeos em canais configurados no server_settings.json."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not message.content:
            return

        guild_cfg = self.bot.db.file_settings.get(str(message.guild.id), {})
        channels = {str(value).strip() for value in guild_cfg.get("video_channels", [])}
        if not channels or str(message.channel.id) not in channels:
            return

        urls = []
        seen = set()
        for match in URL_RE.findall(message.content):
            url = clean_url(match)
            if video_platform(url) and url not in seen:
                seen.add(url)
                urls.append(url)
        if not urls:
            return

        profiles = guild_cfg.get("video_profiles", [])
        if isinstance(profiles, str):
            profiles = [profiles]
        accepted = []
        for url in urls[:5]:
            platform = video_platform(url)
            creator_name = ""
            creator_url = ""
            if profiles:
                try:
                    creator_name, creator_url = await asyncio.wait_for(get_creator(url), timeout=6)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError) as exc:
                    log.info("Não foi possível verificar o perfil de %s: %s", url, exc)
                    continue
                if not any(profile_matches(str(p), creator_name, creator_url) for p in profiles):
                    continue
            accepted.append((url, platform, creator_name))

        if not accepted:
            return

        embed = discord.Embed(
            title="\U0001f3ac Vídeo detectado",
            description=f"Publicado por {message.author.mention} em {message.channel.mention}.",
            color=0x5865F2,
        )
        for index, (url, platform, creator) in enumerate(accepted, start=1):
            label = f"{platform}" + (f" · {creator}" if creator else "")
            embed.add_field(name=label[:256], value=f"[Abrir vídeo]({url})", inline=False)
        embed.add_field(name="Mensagem original", value=f"[Ver publicação]({message.jump_url})", inline=False)
        embed.set_footer(text="Julinha Chan • detector de vídeos v1.5")

        try:
            await message.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none(),
                                        reference=message, mention_author=False)
        except discord.HTTPException as exc:
            log.warning("Não foi possível publicar detecção de vídeo: %s", exc)


async def setup(bot):
    await bot.add_cog(VideoWatch(bot))
