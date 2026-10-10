import datetime as dt
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

import db

PARTY_EMOJI = "🎉"


def parse_duration(text: str) -> int | None:
    """'10d', '2s', '30dk', '1g' gibi bir metni saniyeye çevirir. Geçersizse None döner."""
    text = text.strip().lower().replace(" ", "")
    units = {
        "s": 1, "sn": 1, "saniye": 1,
        "dk": 60, "d": 60, "dakika": 60,
        "sa": 3600, "saat": 3600, "h": 3600,
        "g": 86400, "gun": 86400, "gün": 86400,
    }
    import re
    m = re.fullmatch(r"(\d+)([a-zçğıöşü]+)", text)
    if not m:
        return None
    n, unit = m.groups()
    if unit not in units:
        return None
    return int(n) * units[unit]


def build_embed(prize: str, winners: int, host: discord.abc.User, end_at: dt.datetime, ended: bool = False) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 Çekiliş Bitti!" if ended else "🎉 Çekiliş!",
        description=f"**Ödül:** {prize}\n\nKatılmak için {PARTY_EMOJI} tepkisi bırak!",
        color=discord.Color.gold() if not ended else discord.Color.dark_grey(),
    )
    embed.add_field(name="Kazanan sayısı", value=str(winners))
    embed.add_field(name="Başlatan", value=host.mention)
    if not ended:
        embed.add_field(name="Bitiş", value=discord.utils.format_dt(end_at, "R"), inline=False)
    return embed


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.checker.start()

    def cog_unload(self):
        self.checker.cancel()

    cekilis = app_commands.Group(
        name="cekilis", description="Çekiliş sistemi", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @cekilis.command(name="baslat", description="Yeni bir çekiliş başlatır")
    @app_commands.describe(
        odul="Çekilişte verilecek ödül",
        sure="Süre: ör. 30dk, 2sa, 1g",
        kazanan_sayisi="Kaç kişi kazanacak",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def baslat(
        self,
        interaction: discord.Interaction,
        odul: app_commands.Range[str, 1, 200],
        sure: str,
        kazanan_sayisi: app_commands.Range[int, 1, 20] = 1,
    ):
        seconds = parse_duration(sure)
        if not seconds or seconds < 10 or seconds > 60 * 60 * 24 * 30:
            return await interaction.response.send_message(
                "❌ Geçersiz süre. Örnek: `30dk`, `2sa`, `1g` (en az 10 saniye, en fazla 30 gün).", ephemeral=True
            )
        if not interaction.guild.me.guild_permissions.add_reactions:
            return await interaction.response.send_message("❌ Bende **Tepki Ekle** yetkisi yok.", ephemeral=True)

        end_at = discord.utils.utcnow() + dt.timedelta(seconds=seconds)
        embed = build_embed(odul, kazanan_sayisi, interaction.user, end_at)
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction(PARTY_EMOJI)

        await db.create_giveaway(
            msg.id, msg.channel.id, interaction.guild.id, interaction.user.id,
            odul, kazanan_sayisi, end_at.isoformat(),
        )

    @cekilis.command(name="bitir", description="Bir çekilişi hemen bitirir")
    @app_commands.describe(mesaj_id="Çekiliş mesajının ID'si")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bitir(self, interaction: discord.Interaction, mesaj_id: str):
        if not mesaj_id.isdigit():
            return await interaction.response.send_message("❌ Geçerli bir mesaj ID'si gir.", ephemeral=True)
        row = await db.get_giveaway(int(mesaj_id))
        if not row or row[5]:
            return await interaction.response.send_message("❌ Bu ID'de aktif bir çekiliş yok.", ephemeral=True)
        await interaction.response.send_message("⏳ Çekiliş sonuçlandırılıyor...", ephemeral=True)
        await self.finish_giveaway(int(mesaj_id))

    @cekilis.command(name="listele", description="Aktif çekilişleri gösterir")
    async def listele(self, interaction: discord.Interaction):
        rows = await db.get_active_giveaways(interaction.guild.id)
        if not rows:
            return await interaction.response.send_message("📭 Aktif çekiliş yok.", ephemeral=True)
        lines = [
            f"🎉 **{prize}** — <#{cid}> — bitiş: {discord.utils.format_dt(dt.datetime.fromisoformat(end), 'R')} (`{mid}`)"
            for mid, cid, prize, winners, end in rows
        ]
        await interaction.response.send_message(
            embed=discord.Embed(title="🎉 Aktif çekilişler", description="\n".join(lines), color=discord.Color.gold())
        )

    # ---------- bitirme mantığı ----------

    async def finish_giveaway(self, message_id: int):
        row = await db.get_giveaway(message_id)
        if not row:
            return
        channel_id, guild_id, host_id, prize, winners_count, ended = row
        if ended:
            return
        await db.end_giveaway(message_id)

        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if channel is None:
            return
        try:
            message = await channel.fetch_message(message_id)
        except discord.HTTPException:
            return

        entrants = []
        for reaction in message.reactions:
            if str(reaction.emoji) == PARTY_EMOJI:
                async for user in reaction.users():
                    if not user.bot:
                        entrants.append(user)
                break

        host = guild.get_member(host_id) or discord.Object(id=host_id)
        try:
            await message.edit(embed=build_embed(prize, winners_count, host, discord.utils.utcnow(), ended=True))
        except discord.HTTPException:
            pass

        if not entrants:
            await channel.send(f"🎉 **{prize}** çekilişine kimse katılmadığı için kazanan seçilemedi.")
            return

        winners = random.sample(entrants, k=min(winners_count, len(entrants)))
        mentions = ", ".join(w.mention for w in winners)
        await channel.send(
            f"🎉 Tebrikler {mentions}! **{prize}** ödülünü kazandınız!",
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @tasks.loop(seconds=30)
    async def checker(self):
        now_iso = discord.utils.utcnow().isoformat()
        for message_id, *_ in await db.get_due_giveaways(now_iso):
            try:
                await self.finish_giveaway(message_id)
            except Exception as e:  # noqa: BLE001
                print(f"[çekiliş] bitirme hatası: {e}")

    @checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
