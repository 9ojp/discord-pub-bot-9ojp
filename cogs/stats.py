from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

import db

KIND_LABELS = {"uye": "👥 Üye", "bot": "🤖 Bot", "toplam": "📊 Toplam"}
UPDATE_MINUTES = 10  # Discord kanal adı değişikliğini sınırlıyor, bu yüzden sık güncellemiyoruz


def count_for(guild: discord.Guild, kind: str) -> int:
    if kind == "bot":
        return sum(1 for m in guild.members if m.bot)
    if kind == "toplam":
        return guild.member_count or len(guild.members)
    return sum(1 for m in guild.members if not m.bot)  # uye


def channel_name(kind: str, count: int) -> str:
    return f"{KIND_LABELS[kind]}: {count}"


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.updater.start()

    def cog_unload(self):
        self.updater.cancel()

    istatistik = app_commands.Group(
        name="istatistik", description="Canlı üye sayısı gösteren ses kanalları", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @istatistik.command(name="ekle", description="Seçtiğin türde canlı sayaç kanalı oluşturur")
    @app_commands.describe(tur="Hangi sayı gösterilsin")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ekle(self, interaction: discord.Interaction, tur: Literal["uye", "bot", "toplam"]):
        guild = interaction.guild
        if not guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message("❌ Bende **Kanalları Yönet** yetkisi yok.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        count = count_for(guild, tur)
        channel = await guild.create_voice_channel(
            name=channel_name(tur, count),
            overwrites={guild.default_role: discord.PermissionOverwrite(connect=False)},
            reason="İstatistik kanalı oluşturuldu",
        )
        await db.set_stats_channel(guild.id, tur, channel.id)
        await interaction.followup.send(
            f"✅ {channel.mention} oluşturuldu. İsim her {UPDATE_MINUTES} dakikada bir güncellenir "
            "(Discord'un sınırı yüzünden anlık değil).",
            ephemeral=True,
        )

    @istatistik.command(name="kapat", description="Bir istatistik kanalını kaldırır")
    @app_commands.describe(tur="Hangi sayaç kaldırılsın")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def kapat(self, interaction: discord.Interaction, tur: Literal["uye", "bot", "toplam"]):
        channel_id = await db.remove_stats_channel(interaction.guild.id, tur)
        if not channel_id:
            return await interaction.response.send_message("❌ Bu türde ayarlı bir kanal yok.", ephemeral=True)
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            try:
                await channel.delete(reason="İstatistik kanalı kaldırıldı")
            except discord.HTTPException:
                pass
        await interaction.response.send_message("✅ Kaldırıldı.")

    @tasks.loop(minutes=UPDATE_MINUTES)
    async def updater(self):
        for guild_id, kind, channel_id in await db.get_stats_channels():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            channel = guild.get_channel(channel_id)
            if channel is None:
                continue
            new_name = channel_name(kind, count_for(guild, kind))
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name, reason="İstatistik güncellemesi")
                except discord.HTTPException as e:
                    print(f"[istatistik] kanal güncellenemedi ({guild_id}/{kind}): {e}")

    @updater.before_loop
    async def before_updater(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
