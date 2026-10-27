import os
import json
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  guild_id INTEGER, user_id INTEGER,
  xp INTEGER DEFAULT 0, messages INTEGER DEFAULT 0,
  bio TEXT DEFAULT '', title TEXT DEFAULT '',
  public INTEGER DEFAULT 1, accent TEXT DEFAULT 'verde',
  notify INTEGER DEFAULT 1, last_xp INTEGER DEFAULT 0, warns INTEGER DEFAULT 0,
  PRIMARY KEY(guild_id, user_id));
CREATE TABLE IF NOT EXISTS achievements(
  guild_id INTEGER, user_id INTEGER, key TEXT, ts INTEGER,
  PRIMARY KEY(guild_id, user_id, key));
CREATE TABLE IF NOT EXISTS affinity(
  guild_id INTEGER, a INTEGER, b INTEGER, points INTEGER DEFAULT 0, last INTEGER DEFAULT 0,
  PRIMARY KEY(guild_id, a, b));
CREATE TABLE IF NOT EXISTS settings(
  guild_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(guild_id, key));
CREATE TABLE IF NOT EXISTS level_roles(
  guild_id INTEGER, level INTEGER, role_id INTEGER, PRIMARY KEY(guild_id, role_id));
CREATE TABLE IF NOT EXISTS replies(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, word TEXT, response TEXT);
CREATE TABLE IF NOT EXISTS logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, ts INTEGER, type TEXT,
  actor_id INTEGER, target_id INTEGER, details TEXT);
CREATE INDEX IF NOT EXISTS idx_logs ON logs(guild_id, ts);
CREATE TABLE IF NOT EXISTS errors(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, kind TEXT, details TEXT);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        default_settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_settings.json")
        self.settings_path = os.getenv("SERVER_SETTINGS_PATH", default_settings_path)
        self.file_settings = {}

    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError:
            # Use the tracked example as a safe starter config when the local
            # server_settings.json has not been created yet.
            example_path = f"{self.settings_path}.example"
            try:
                with open(example_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except FileNotFoundError:
                payload = {}
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Não foi possível ler {self.settings_path}: {exc}") from exc
        self.file_settings = payload.get("guilds", {}) if isinstance(payload, dict) else {}

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def execute(self, sql, params=()):
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur

    async def one(self, sql, params=()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def all(self, sql, params=()):
        async with self.conn.execute(sql, params) as cur:
            return await cur.fetchall()

    # ---- usuários ----
    async def user(self, gid, uid):
        await self.execute("INSERT OR IGNORE INTO users(guild_id,user_id) VALUES(?,?)", (gid, uid))
        return await self.one("SELECT * FROM users WHERE guild_id=? AND user_id=?", (gid, uid))

    async def rank(self, gid, uid):
        r = await self.one(
            "SELECT COUNT(*)+1 AS r FROM users WHERE guild_id=? AND xp>"
            "(SELECT xp FROM users WHERE guild_id=? AND user_id=?)", (gid, gid, uid))
        return r["r"]

    async def top(self, gid, limit=10):
        return await self.all(
            "SELECT user_id,xp,messages FROM users WHERE guild_id=? AND xp>0 "
            "ORDER BY xp DESC LIMIT ?", (gid, limit))

    async def total_messages(self, gid):
        r = await self.one("SELECT COALESCE(SUM(messages),0) AS n FROM users WHERE guild_id=?", (gid,))
        return r["n"]

    # ---- configurações por servidor ----
    async def get(self, gid, key, default=None):
        # O arquivo de texto tem prioridade e é carregado ao iniciar o bot.
        guild_settings = self.file_settings.get(str(gid), {})
        if key in guild_settings:
            value = guild_settings[key]
            if isinstance(value, bool):
                return "1" if value else "0"
            return str(value)
        r = await self.one("SELECT value FROM settings WHERE guild_id=? AND key=?", (gid, key))
        return r["value"] if r else default

    async def set(self, gid, key, value):
        await self.execute(
            "INSERT INTO settings(guild_id,key,value) VALUES(?,?,?) "
            "ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value", (gid, key, str(value)))

    async def flag(self, gid, key, default=False):
        v = await self.get(gid, key)
        return default if v is None else v == "1"

    async def number(self, gid, key, default=0.0):
        v = await self.get(gid, key)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    # ---- logs ----
    async def add_log(self, gid, ts, type_, actor_id, target_id, details):
        await self.execute(
            "INSERT INTO logs(guild_id,ts,type,actor_id,target_id,details) VALUES(?,?,?,?,?,?)",
            (gid, ts, type_, actor_id, target_id, details))

    async def search_logs(self, gid, user_id=None, since=None, category=None, limit=15):
        sql, p = "SELECT * FROM logs WHERE guild_id=?", [gid]
        if user_id:
            sql += " AND (actor_id=? OR target_id=?)"
            p += [user_id, user_id]
        if since:
            sql += " AND ts>=?"
            p.append(since)
        if category:
            sql += " AND type LIKE ?"
            p.append(category + ":%")
        sql += " ORDER BY id DESC LIMIT ?"
        p.append(limit)
        return await self.all(sql, p)

    async def count_logs(self, gid, since, category=None):
        sql, p = "SELECT COUNT(*) AS n FROM logs WHERE guild_id=? AND ts>=?", [gid, since]
        if category:
            sql += " AND type LIKE ?"
            p.append(category + ":%")
        return (await self.one(sql, p))["n"]

    # ---- erros / reconexões (globais) ----
    async def log_error(self, kind, details, ts=None):
        import time
        await self.execute("INSERT INTO errors(ts,kind,details) VALUES(?,?,?)",
                           (ts or int(time.time()), kind, details[:1500]))

    async def recent_errors(self, limit=15):
        return await self.all("SELECT * FROM errors ORDER BY id DESC LIMIT ?", (limit,))

    async def count_errors(self, since):
        return (await self.one("SELECT COUNT(*) AS n FROM errors WHERE ts>=? AND kind NOT IN ('pronto','reconexao')", (since,)))["n"]
