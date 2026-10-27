import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()}
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID") or 0)
DB_PATH = os.getenv("DB_PATH", "data/bot.db")

BOT_NAME = "Julinha Chan"
BOT_VERSION = "1.8"
BRAND_COLOR = 0x5865F2  # azul discreto

# XP por mensagem (com cooldown por usuário)
XP_MIN, XP_MAX, XP_COOLDOWN = 15, 25, 60

# Rotação de status: (tipo, texto). Variáveis: {servers} e {members}
PRESENCES = [
    ("watching", "{servers} comunidades"),
    ("playing", "organizando a comunidade"),
    ("listening", "a comunidade"),
]
PRESENCE_MINUTES = 5
