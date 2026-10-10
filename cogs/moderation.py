import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import action_embed, can_act, send_log, try_dm

WARN_LIMIT = 3         # Her 3 uyarıda otomatik susturma (3, 6, 9...)
WARN_TIMEOUT_MIN = 60  # Otomatik susturma süresi (dakika)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- BAN / KICK ----------

    @app_commands.command(name="ban", description="Bir üyeyi sunucudan yasaklar")
    @app_commands.describe(uye="Yasaklanacak üye", sebep="Sebep")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, uye: discord.Member, sebep: str = "Sebep belirtilmedi"):
        if err := can_act(interaction, uye):
            return await interaction.response.send_message(err, ephemeral=True)

        await try_dm(uye, f"**{interaction.guild.name}** sunucusundan yasaklandın.\nSebep: {sebep}")
        await uye.ban(reason=f"{interaction.user}: {sebep}")

        embed = action_embed("🔨 Ban", discord.Color.red(), uye, interaction.user, sebep)
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, interaction.guild, embed)

    @app_commands.command(name="unban", description="Bir kullanıcının banını kaldırır")
    @app_commands.describe(kullanici_id="Banı kaldırılacak kullanıcının ID'si", sebep="Sebep")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, kullanici_id: str, sebep: str = "Sebep belirtilmedi"):
        if not kullanici_id.isdigit():
            return await interaction.response.send_message("❌ Geçerli bir kullanıcı ID'si gir.", ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(kullanici_id))
            await interaction.guild.unban(user, reason=f"{interaction.user}: {sebep}")
        except discord.NotFound:
            return await interaction.response.send_message("❌ Bu kullanıcı banlı değil ya da bulunamadı.", ephemeral=True)

        embed = action_embed("✅ Ban kaldırıldı", discord.Color.green(), user, interaction.user, sebep)
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, interaction.guild, embed)

    @app_commands.command(name="kick", description="Bir üyeyi sunucudan atar")
    @app_commands.describe(uye="Atılacak üye", sebep="Sebep")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, uye: discord.Member, sebep: str = "Sebep belirtilmedi"):
        if err := can_act(interaction, uye):
            return await interaction.response.send_message(err, ephemeral=True)

        await try_dm(uye, f"**{interaction.guild.name}** sunucusundan atıldın.\nSebep: {sebep}")
        await uye.kick(reason=f"{interaction.user}: {sebep}")

        embed = action_embed("👢 Kick", discord.Color.orange(), uye, interaction.user, sebep)
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, interaction.guild, embed)

    # ---------- MUTE (TIMEOUT) ----------

    @app_commands.command(name="mute", description="Bir üyeyi belirli süre susturur (timeout)")
    @app_commands.describe(uye="Susturulacak üye", dakika="Süre (dakika, en fazla 28 gün)", sebep="Sebep")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        uye: discord.Member,
        dakika: app_commands.Range[int, 1, 40320],
        sebep: str = "Sebep belirtilmedi",
    ):
        if err := can_act(interaction, uye):
            return await interaction.response.send_message(err, ephemeral=True)

        await uye.timeout(dt.timedelta(minutes=dakika), reason=f"{interaction.user}: {sebep}")

        embed = action_embed("🔇 Susturuldu", discord.Color.dark_orange(), uye, interaction.user, sebep)
        embed.add_field(name="Süre", value=f"{dakika} dakika")
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, interaction.guild, embed)

    @app_commands.command(name="unmute", description="Bir üyenin susturmasını kaldırır")
    @app_commands.describe(uye="Susturması kaldırılacak üye")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, uye: discord.Member):
        if err := can_act(interaction, uye):
            return await interaction.response.send_message(err, ephemeral=True)

        await uye.timeout(None, reason=f"{interaction.user}: susturma kaldırıldı")

        embed = action_embed("🔊 Susturma kaldırıldı", discord.Color.green(), uye, interaction.user, "-")
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, interaction.guild, embed)

    # ---------- UYARI SİSTEMİ ----------

    @app_commands.command(name="uyari", description="Bir üyeye uyarı verir")
    @app_commands.describe(uye="Uyarılacak üye", sebep="Sebep")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def uyari(self, interaction: discord.Interaction, uye: discord.Member, sebep: str):
        if err := can_act(interaction, uye):
            return await interaction.response.send_message(err, ephemeral=True)

        count = await db.add_warning(interaction.guild.id, uye.id, interaction.user.id, sebep)

        embed = action_embed("⚠️ Uyarı", discord.Color.gold(), uye, interaction.user, sebep)
        embed.add_field(name="Toplam uyarı", value=str(count))
        await try_dm(uye, f"**{interaction.guild.name}** sunucusunda uyarıldın.\nSebep: {sebep}\nToplam uyarın: {count}")
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, interaction.guild, embed)

        if count % WARN_LIMIT == 0:
            try:
                await uye.timeout(
                    dt.timedelta(minutes=WARN_TIMEOUT_MIN),
                    reason=f"{count} uyarıya ulaştı",
                )
                await interaction.followup.send(
                    f"🔇 {uye.mention} {count} uyarıya ulaştığı için {WARN_TIMEOUT_MIN} dakika susturuldu."
                )
            except discord.HTTPException:
                pass  # yetki yoksa otomatik susturma atlanır

    @app_commands.command(name="uyarilar", description="Bir üyenin uyarılarını listeler")
    @app_commands.describe(uye="Uyarıları görülecek üye")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def uyarilar(self, interaction: discord.Interaction, uye: discord.Member):
        rows = await db.get_warnings(interaction.guild.id, uye.id)
        if not rows:
            return await interaction.response.send_message(f"{uye.mention} kullanıcısının hiç uyarısı yok.", ephemeral=True)

        lines = []
        for wid, mod_id, reason, created_at in rows[:10]:
            when = discord.utils.format_dt(dt.datetime.fromisoformat(created_at), "d")
            lines.append(f"**#{wid}** • {when} • {reason} — <@{mod_id}>")

        embed = discord.Embed(
            title=f"⚠️ {uye.display_name} uyarıları ({len(rows)})",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        if len(rows) > 10:
            embed.set_footer(text=f"Son 10 uyarı gösteriliyor, toplam {len(rows)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="uyarisil", description="Bir üyenin tüm uyarılarını siler")
    @app_commands.describe(uye="Uyarıları silinecek üye")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def uyarisil(self, interaction: discord.Interaction, uye: discord.Member):
        n = await db.clear_warnings(interaction.guild.id, uye.id)
        await interaction.response.send_message(f"🧹 {uye.mention} kullanıcısının {n} uyarısı silindi.")

    # ---------- TOPLU MESAJ SİLME ----------

    @app_commands.command(name="temizle", description="Kanaldaki mesajları toplu siler")
    @app_commands.describe(sayi="Taranacak mesaj sayısı (1-100)", uye="Sadece bu üyenin mesajlarını sil (opsiyonel)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def temizle(
        self,
        interaction: discord.Interaction,
        sayi: app_commands.Range[int, 1, 100],
        uye: discord.Member | None = None,
    ):
        await interaction.response.defer(ephemeral=True)

        if uye:
            check = lambda m: m.author.id == uye.id
        else:
            check = lambda m: True
        deleted = await interaction.channel.purge(limit=sayi, check=check)

        await interaction.followup.send(f"🧹 {len(deleted)} mesaj silindi.", ephemeral=True)

        embed = discord.Embed(title="🧹 Toplu mesaj silme", color=discord.Color.dark_grey(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Yetkili", value=interaction.user.mention)
        embed.add_field(name="Kanal", value=interaction.channel.mention)
        embed.add_field(name="Silinen", value=str(len(deleted)))
        if uye:
            embed.add_field(name="Hedef üye", value=uye.mention)
        await send_log(self.bot, interaction.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
