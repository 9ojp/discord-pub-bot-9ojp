import re
import time
from collections import defaultdict, deque
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import send_log

INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)

SPAM_WINDOW = 6.0       # saniye
SPAM_COUNT = 5          # bu sürede bu kadar mesaj atarsa spam sayılır
DUPLICATE_LIMIT = 3     # aynı mesajı art arda bu kadar atarsa spam sayılır
CAPS_MIN_LEN = 10       # bu uzunluktan kısa mesajlarda büyük harf kontrolü yapılmaz
CAPS_RATIO = 0.7        # büyük harf oranı eşiği
MENTION_LIMIT = 5       # tek mesajda bu kadardan fazla kişi/rol etiketi
NOTICE_DELETE_AFTER = 6.0

FIELD_LABELS = {
    "words": "Yasaklı kelime filtresi",
    "spam": "Spam filtresi",
    "invites": "Davet linki engeli",
    "caps": "Büyük harf filtresi",
    "mentions": "Aşırı etiketleme filtresi",
}
FIELD_MAP = {
    "kufur": "words",
    "spam": "spam",
    "davet": "invites",
    "buyukharf": "caps",
    "bahsetme": "mentions",
}


def caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters)


class _UserHistory:
    __slots__ = ("times", "last_content", "repeat")

    def __init__(self):
        self.times: deque[float] = deque(maxlen=SPAM_COUNT)
        self.last_content = None
        self.repeat = 0


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.history: dict[tuple[int, int], _UserHistory] = defaultdict(_UserHistory)
        self.word_cache: dict[int, list[str]] = {}

    otomatik = app_commands.Group(
        name="otomatik",
        description="Otomatik moderasyon ayarları",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ---------- ayar komutları ----------

    @otomatik.command(name="ayarla", description="Bir otomatik moderasyon özelliğini açar/kapatır")
    @app_commands.describe(ozellik="Hangi özellik", durum="Aç ya da kapat")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ayarla(
        self,
        interaction: discord.Interaction,
        ozellik: Literal["kufur", "spam", "davet", "buyukharf", "bahsetme"],
        durum: Literal["ac", "kapat"],
    ):
        field = FIELD_MAP[ozellik]
        await db.set_automod_flag(interaction.guild.id, f"am_{field}", durum == "ac")
        durum_yazi = "açıldı" if durum == "ac" else "kapatıldı"
        await interaction.response.send_message(f"✅ **{FIELD_LABELS[field]}** {durum_yazi}.")

    @otomatik.command(name="bypass", description="Bu rolü otomatik moderasyondan muaf tutar")
    @app_commands.describe(rol="Muaf tutulacak rol (boş bırakırsan muafiyeti kaldırır)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bypass(self, interaction: discord.Interaction, rol: discord.Role | None = None):
        await db.set_automod_bypass(interaction.guild.id, rol.id if rol else None)
        if rol:
            await interaction.response.send_message(f"✅ {rol.mention} rolü artık otomatik moderasyondan muaf.")
        else:
            await interaction.response.send_message("✅ Muafiyet kaldırıldı.")

    @otomatik.command(name="durum", description="Otomatik moderasyon ayarlarını gösterir")
    async def durum(self, interaction: discord.Interaction):
        cfg = await db.get_automod_config(interaction.guild.id)
        lines = [f"{'✅' if cfg[k] else '❌'} {label}" for k, label in FIELD_LABELS.items()]
        bypass_role = interaction.guild.get_role(cfg["bypass_role_id"]) if cfg["bypass_role_id"] else None
        lines.append(f"🛡️ Muaf rol: {bypass_role.mention if bypass_role else 'yok'}")
        word_count = len(await db.get_banned_words(interaction.guild.id))
        lines.append(f"📝 Yasaklı kelime sayısı: {word_count}")
        await interaction.response.send_message(
            embed=discord.Embed(title="⚙️ Otomatik Moderasyon", description="\n".join(lines), color=discord.Color.blurple()),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    kelime = app_commands.Group(
        name="yasakikelime", description="Yasaklı kelime listesi", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True), parent=otomatik,
    )

    @kelime.command(name="ekle", description="Yasaklı kelime listesine ekler")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def kelime_ekle(self, interaction: discord.Interaction, kelime: app_commands.Range[str, 1, 50]):
        ok = await db.add_banned_word(interaction.guild.id, kelime.lower().strip())
        self.word_cache.pop(interaction.guild.id, None)
        if ok:
            await interaction.response.send_message(f"✅ **{kelime}** listeye eklendi.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bu kelime zaten listede.", ephemeral=True)

    @kelime.command(name="sil", description="Yasaklı kelime listesinden çıkarır")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def kelime_sil(self, interaction: discord.Interaction, kelime: str):
        ok = await db.remove_banned_word(interaction.guild.id, kelime.lower().strip())
        self.word_cache.pop(interaction.guild.id, None)
        if ok:
            await interaction.response.send_message(f"🗑️ **{kelime}** listeden çıkarıldı.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bu kelime listede yok.", ephemeral=True)

    @kelime.command(name="liste", description="Yasaklı kelimeleri gösterir")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def kelime_liste(self, interaction: discord.Interaction):
        words = await db.get_banned_words(interaction.guild.id)
        if not words:
            return await interaction.response.send_message("📭 Yasaklı kelime listesi boş.", ephemeral=True)
        await interaction.response.send_message(
            f"📝 Yasaklı kelimeler ({len(words)}): " + ", ".join(f"`{w}`" for w in words[:50]), ephemeral=True
        )

    # ---------- yardımcılar ----------

    async def _words(self, guild_id: int) -> list[str]:
        if guild_id not in self.word_cache:
            self.word_cache[guild_id] = await db.get_banned_words(guild_id)
        return self.word_cache[guild_id]

    def _match_word(self, content: str, words: list[str]) -> str | None:
        low = content.lower()
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", low):
                return w
        return None

    async def _notice(self, message: discord.Message, text: str):
        try:
            m = await message.channel.send(f"⚠️ {message.author.mention} {text}", allowed_mentions=discord.AllowedMentions(users=True))
            await m.delete(delay=NOTICE_DELETE_AFTER)
        except discord.HTTPException:
            pass

    async def _log(self, message: discord.Message, reason: str):
        embed = discord.Embed(title="🛡️ Otomatik moderasyon", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Kullanıcı", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="Kanal", value=message.channel.mention)
        embed.add_field(name="Sebep", value=reason, inline=False)
        if message.content:
            embed.add_field(name="İçerik", value=message.content[:500], inline=False)
        await send_log(self.bot, message.guild, embed)

    def _is_exempt(self, member: discord.Member, bypass_role_id: int | None) -> bool:
        if member.guild_permissions.manage_messages:
            return True
        if bypass_role_id and any(r.id == bypass_role_id for r in member.roles):
            return True
        return False

    # ---------- ana kontrol ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        cfg = await db.get_automod_config(message.guild.id)
        if not any(cfg[k] for k in FIELD_LABELS) or self._is_exempt(message.author, cfg["bypass_role_id"]):
            return

        content = message.content or ""

        if cfg["words"]:
            words = await self._words(message.guild.id)
            hit = self._match_word(content, words) if words else None
            if hit:
                await self._delete(message, f"Yasaklı kelime kullanıldı (`{hit}`).")
                return

        if cfg["invites"] and INVITE_RE.search(content):
            await self._delete(message, "Discord davet linki paylaşıldı.")
            return

        if cfg["caps"] and len(content) >= CAPS_MIN_LEN and caps_ratio(content) >= CAPS_RATIO:
            await self._delete(message, "Aşırı büyük harf kullanımı.")
            return

        if cfg["mentions"]:
            total = len(message.mentions) + len(message.role_mentions) + (1 if message.mention_everyone else 0)
            if total > MENTION_LIMIT:
                await self._delete(message, f"Tek mesajda {total} etiketleme (limit: {MENTION_LIMIT}).")
                return

        if cfg["spam"] and self._check_spam(message, content):
            await self._delete(message, "Spam (hızlı/tekrarlı mesaj) tespit edildi.")
            return

    def _check_spam(self, message: discord.Message, content: str) -> bool:
        key = (message.guild.id, message.author.id)
        hist = self.history[key]
        now = time.monotonic()
        hist.times.append(now)

        rate_hit = len(hist.times) >= SPAM_COUNT and (now - hist.times[0]) <= SPAM_WINDOW

        if content and content == hist.last_content:
            hist.repeat += 1
        else:
            hist.repeat = 0
            hist.last_content = content
        dup_hit = hist.repeat + 1 >= DUPLICATE_LIMIT

        return rate_hit or dup_hit

    async def _delete(self, message: discord.Message, reason: str):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await self._notice(message, "mesajın kaldırıldı: " + reason)
        await self._log(message, reason)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
