import os
from datetime import datetime, timezone

import aiosqlite

# Railway'de Volume bağlıysa veritabanı orada tutulur (yeniden başlatmada silinmez).
_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
DB_PATH = os.getenv("DB_PATH") or (os.path.join(_volume, "bot.db") if _volume else "bot.db")


async def init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                mod_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                autorole_id INTEGER,
                ticket_category_id INTEGER,
                ticket_staff_role_id INTEGER,
                ticket_panel_channel_id INTEGER,
                ticket_counter INTEGER NOT NULL DEFAULT 0,
                am_words INTEGER NOT NULL DEFAULT 0,
                am_spam INTEGER NOT NULL DEFAULT 0,
                am_invites INTEGER NOT NULL DEFAULT 0,
                am_caps INTEGER NOT NULL DEFAULT 0,
                am_mentions INTEGER NOT NULL DEFAULT 0,
                am_bypass_role_id INTEGER,
                welcome_channel_id INTEGER,
                welcome_message TEXT,
                leave_channel_id INTEGER,
                leave_message TEXT,
                modmail_category_id INTEGER,
                modmail_staff_role_id INTEGER,
                modmail_counter INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS banned_words (
                guild_id INTEGER NOT NULL,
                word TEXT NOT NULL COLLATE NOCASE,
                PRIMARY KEY (guild_id, word)
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners_count INTEGER NOT NULL,
                end_time TEXT NOT NULL,
                ended INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                trigger TEXT NOT NULL,
                answer TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (message_id, emoji)
            );
            CREATE TABLE IF NOT EXISTS modmail_threads (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                number INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS stats_channels (
                guild_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, kind)
            );
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                opener_id INTEGER NOT NULL,
                number INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        for col, coltype in (
            ("ticket_category_id", "INTEGER"),
            ("ticket_staff_role_id", "INTEGER"),
            ("ticket_panel_channel_id", "INTEGER"),
            ("ticket_counter", "INTEGER NOT NULL DEFAULT 0"),
            ("am_words", "INTEGER NOT NULL DEFAULT 0"),
            ("am_spam", "INTEGER NOT NULL DEFAULT 0"),
            ("am_invites", "INTEGER NOT NULL DEFAULT 0"),
            ("am_caps", "INTEGER NOT NULL DEFAULT 0"),
            ("am_mentions", "INTEGER NOT NULL DEFAULT 0"),
            ("am_bypass_role_id", "INTEGER"),
            ("welcome_channel_id", "INTEGER"),
            ("welcome_message", "TEXT"),
            ("leave_channel_id", "INTEGER"),
            ("leave_message", "TEXT"),
            ("modmail_category_id", "INTEGER"),
            ("modmail_staff_role_id", "INTEGER"),
            ("modmail_counter", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                await db.execute(f"ALTER TABLE settings ADD COLUMN {col} {coltype}")
            except aiosqlite.OperationalError:
                pass  # sütun zaten var
        # Eski veritabanlarında sütun yoksa ekle
        try:
            await db.execute("ALTER TABLE settings ADD COLUMN autorole_id INTEGER")
        except aiosqlite.OperationalError:
            pass  # sütun zaten var
        await db.commit()


async def add_warning(guild_id: int, user_id: int, mod_id: int, reason: str) -> int:
    """Uyarıyı ekler ve kullanıcının toplam uyarı sayısını döndürür."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (guild_id, user_id, mod_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, mod_id, reason, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        (count,) = await cur.fetchone()
    return count


async def get_warnings(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, mod_id, reason, created_at FROM warnings "
            "WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        )
        return await cur.fetchall()


async def clear_warnings(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return cur.rowcount


async def set_log_channel(guild_id: int, channel_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (guild_id, log_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id",
            (guild_id, channel_id),
        )
        await db.commit()


async def get_log_channel(guild_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT log_channel_id FROM settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def set_autorole(guild_id: int, role_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (guild_id, autorole_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET autorole_id = excluded.autorole_id",
            (guild_id, role_id),
        )
        await db.commit()


async def get_autorole(guild_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT autorole_id FROM settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None



# ---------- ticket sistemi ----------

async def set_ticket_config(guild_id: int, category_id: int | None, staff_role_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (guild_id, ticket_category_id, ticket_staff_role_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "ticket_category_id = excluded.ticket_category_id, "
            "ticket_staff_role_id = excluded.ticket_staff_role_id",
            (guild_id, category_id, staff_role_id),
        )
        await db.commit()


async def get_ticket_config(guild_id: int):
    """(kategori_id, yetkili_rol_id) döndürür, ikisi de None olabilir."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT ticket_category_id, ticket_staff_role_id FROM settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cur.fetchone()
    return row if row else (None, None)


async def next_ticket_number(guild_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (guild_id, ticket_counter) VALUES (?, 1) "
            "ON CONFLICT(guild_id) DO UPDATE SET ticket_counter = ticket_counter + 1",
            (guild_id,),
        )
        await db.commit()
        cur = await db.execute("SELECT ticket_counter FROM settings WHERE guild_id = ?", (guild_id,))
        (n,) = await cur.fetchone()
    return n


async def create_ticket(channel_id: int, guild_id: int, opener_id: int, number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets (channel_id, guild_id, opener_id, number, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel_id, guild_id, opener_id, number, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def get_ticket(channel_id: int):
    """(guild_id, opener_id, number, closed) ya da None."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT guild_id, opener_id, number, closed FROM tickets WHERE channel_id = ?",
            (channel_id,),
        )
        return await cur.fetchone()


async def has_open_ticket(guild_id: int, opener_id: int) -> int | None:
    """Kullanıcının açık ticket'ının kanal ID'sini döndürür, yoksa None."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel_id FROM tickets WHERE guild_id = ? AND opener_id = ? AND closed = 0",
            (guild_id, opener_id),
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def close_ticket(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET closed = 1 WHERE channel_id = ?", (channel_id,))
        await db.commit()


# ---------- otomatik moderasyon ----------

AM_FIELDS = ("am_words", "am_spam", "am_invites", "am_caps", "am_mentions")


async def _ensure_settings_row(conn, guild_id: int):
    await conn.execute("INSERT OR IGNORE INTO settings (guild_id) VALUES (?)", (guild_id,))


async def set_automod_flag(guild_id: int, field: str, enabled: bool):
    assert field in AM_FIELDS
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings_row(db, guild_id)
        await db.execute(f"UPDATE settings SET {field} = ? WHERE guild_id = ?", (1 if enabled else 0, guild_id))
        await db.commit()


async def set_automod_bypass(guild_id: int, role_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings_row(db, guild_id)
        await db.execute("UPDATE settings SET am_bypass_role_id = ? WHERE guild_id = ?", (role_id, guild_id))
        await db.commit()


async def get_automod_config(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT am_words, am_spam, am_invites, am_caps, am_mentions, am_bypass_role_id "
            "FROM settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cur.fetchone()
    if not row:
        return {"words": False, "spam": False, "invites": False, "caps": False, "mentions": False, "bypass_role_id": None}
    return {
        "words": bool(row[0]), "spam": bool(row[1]), "invites": bool(row[2]),
        "caps": bool(row[3]), "mentions": bool(row[4]), "bypass_role_id": row[5],
    }


async def add_banned_word(guild_id: int, word: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO banned_words (guild_id, word) VALUES (?, ?)", (guild_id, word))
        except aiosqlite.IntegrityError:
            return False
        await db.commit()
        return True


async def remove_banned_word(guild_id: int, word: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM banned_words WHERE guild_id = ? AND word = ?", (guild_id, word))
        await db.commit()
        return cur.rowcount > 0


async def get_banned_words(guild_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT word FROM banned_words WHERE guild_id = ? ORDER BY word", (guild_id,))
        return [r[0] for r in await cur.fetchall()]


# ---------- çekiliş ----------

async def create_giveaway(message_id, channel_id, guild_id, host_id, prize, winners_count, end_time_iso):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO giveaways (message_id, channel_id, guild_id, host_id, prize, winners_count, end_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, channel_id, guild_id, host_id, prize, winners_count, end_time_iso),
        )
        await db.commit()


async def get_due_giveaways(now_iso: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT message_id, channel_id, guild_id, host_id, prize, winners_count "
            "FROM giveaways WHERE ended = 0 AND end_time <= ?",
            (now_iso,),
        )
        return await cur.fetchall()


async def get_active_giveaways(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT message_id, channel_id, prize, winners_count, end_time FROM giveaways "
            "WHERE guild_id = ? AND ended = 0 ORDER BY end_time",
            (guild_id,),
        )
        return await cur.fetchall()


async def end_giveaway(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (message_id,))
        await db.commit()


async def get_giveaway(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel_id, guild_id, host_id, prize, winners_count, ended FROM giveaways WHERE message_id = ?",
            (message_id,),
        )
        return await cur.fetchone()


# ---------- SSS (FAQ) ----------

async def add_faq(guild_id: int, trigger: str, answer: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO faq (guild_id, trigger, answer) VALUES (?, ?, ?)", (guild_id, trigger, answer)
        )
        await db.commit()
        return cur.lastrowid


async def remove_faq(guild_id: int, trigger: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM faq WHERE guild_id = ? AND trigger = ? COLLATE NOCASE", (guild_id, trigger)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_faqs(guild_id: int):
    """[(trigger, answer), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT trigger, answer FROM faq WHERE guild_id = ? ORDER BY trigger", (guild_id,))
        return await cur.fetchall()


# ---------- hoş geldin / veda ----------

async def set_welcome(guild_id: int, channel_id: int | None, message: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings_row(db, guild_id)
        await db.execute(
            "UPDATE settings SET welcome_channel_id = ?, welcome_message = ? WHERE guild_id = ?",
            (channel_id, message, guild_id),
        )
        await db.commit()


async def get_welcome(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT welcome_channel_id, welcome_message FROM settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
    return row if row else (None, None)


async def set_leave(guild_id: int, channel_id: int | None, message: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings_row(db, guild_id)
        await db.execute(
            "UPDATE settings SET leave_channel_id = ?, leave_message = ? WHERE guild_id = ?",
            (channel_id, message, guild_id),
        )
        await db.commit()


async def get_leave(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT leave_channel_id, leave_message FROM settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
    return row if row else (None, None)


# ---------- reaksiyon rolü ----------

async def add_reaction_role(guild_id: int, message_id: int, emoji: str, role_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                (guild_id, message_id, emoji, role_id),
            )
        except aiosqlite.IntegrityError:
            return False
        await db.commit()
        return True


async def remove_reaction_role(message_id: int, emoji: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?", (message_id, emoji)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_reaction_role(message_id: int, emoji: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?", (message_id, emoji)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def get_reaction_roles_for_message(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT emoji, role_id FROM reaction_roles WHERE message_id = ?", (message_id,)
        )
        return await cur.fetchall()


# ---------- sunucu istatistik kanalları ----------

async def set_stats_channel(guild_id: int, kind: str, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO stats_channels (guild_id, kind, channel_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, kind) DO UPDATE SET channel_id = excluded.channel_id",
            (guild_id, kind, channel_id),
        )
        await db.commit()


async def remove_stats_channel(guild_id: int, kind: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel_id FROM stats_channels WHERE guild_id = ? AND kind = ?", (guild_id, kind)
        )
        row = await cur.fetchone()
        if not row:
            return None
        await db.execute("DELETE FROM stats_channels WHERE guild_id = ? AND kind = ?", (guild_id, kind))
        await db.commit()
        return row[0]


async def get_stats_channels(guild_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if guild_id is None:
            cur = await db.execute("SELECT guild_id, kind, channel_id FROM stats_channels")
        else:
            cur = await db.execute(
                "SELECT guild_id, kind, channel_id FROM stats_channels WHERE guild_id = ?", (guild_id,)
            )
        return await cur.fetchall()


# ---------- modmail (DM üzerinden destek) ----------

async def set_modmail_config(guild_id: int, category_id: int | None, staff_role_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings_row(db, guild_id)
        await db.execute(
            "UPDATE settings SET modmail_category_id = ?, modmail_staff_role_id = ? WHERE guild_id = ?",
            (category_id, staff_role_id, guild_id),
        )
        await db.commit()


async def get_modmail_config(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT modmail_category_id, modmail_staff_role_id FROM settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
    return row if row else (None, None)


async def get_modmail_configured_guild_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT guild_id FROM settings WHERE modmail_category_id IS NOT NULL AND modmail_staff_role_id IS NOT NULL"
        )
        return [r[0] for r in await cur.fetchall()]


async def next_modmail_number(guild_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_settings_row(db, guild_id)
        await db.execute(
            "UPDATE settings SET modmail_counter = modmail_counter + 1 WHERE guild_id = ?", (guild_id,)
        )
        await db.commit()
        cur = await db.execute("SELECT modmail_counter FROM settings WHERE guild_id = ?", (guild_id,))
        (n,) = await cur.fetchone()
    return n


async def create_modmail_thread(channel_id: int, guild_id: int, user_id: int, number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO modmail_threads (channel_id, guild_id, user_id, number, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel_id, guild_id, user_id, number, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def get_modmail_thread_by_channel(channel_id: int):
    """(guild_id, user_id, number, closed) ya da None."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT guild_id, user_id, number, closed FROM modmail_threads WHERE channel_id = ?", (channel_id,)
        )
        return await cur.fetchone()


async def get_open_modmail_thread_for_user(user_id: int):
    """(channel_id, guild_id) ya da None. Kullanıcının herhangi bir sunucuda açık thread'i var mı bakar."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT channel_id, guild_id FROM modmail_threads WHERE user_id = ? AND closed = 0", (user_id,)
        )
        return await cur.fetchone()


async def close_modmail_thread(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE modmail_threads SET closed = 1 WHERE channel_id = ?", (channel_id,))
        await db.commit()
