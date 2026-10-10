import time

import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import cut

COOLDOWN_SECONDS = 15  # aynı tetikleyici aynı kanalda bu süre içinde tekrar yanıtlanmaz


class FAQ(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: dict[int, list[tuple[str, str]]] = {}
        self.last_trigger: dict[tuple[int, str], float] = {}

    sss = app_commands.Group(
        name="sss", description="Sık sorulan sorular (otomatik cevap)", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @sss.command(name="ekle", description="Bir tetikleyici kelimeye otomatik cevap ekler")
    @app_commands.describe(tetikleyici="Mesajda geçince tetiklenecek kelime/kelime öbeği", cevap="Bot'un vereceği cevap")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ekle(self, interaction: discord.Interaction, tetikleyici: app_commands.Range[str, 2, 50], cevap: app_commands.Range[str, 1, 1000]):
        await db.add_faq(interaction.guild.id, tetikleyici.lower().strip(), cevap)
        self.cache.pop(interaction.guild.id, None)
        await interaction.response.send_message(f"✅ **{tetikleyici}** geçince bot artık otomatik cevap verecek.")

    @sss.command(name="sil", description="Bir SSS kaydını siler")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sil(self, interaction: discord.Interaction, tetikleyici: str):
        ok = await db.remove_faq(interaction.guild.id, tetikleyici.lower().strip())
        self.cache.pop(interaction.guild.id, None)
        if ok:
            await interaction.response.send_message(f"🗑️ **{tetikleyici}** kaydı silindi.")
        else:
            await interaction.response.send_message("❌ Bu tetikleyici bulunamadı.", ephemeral=True)

    @sss.command(name="liste", description="Tüm SSS kayıtlarını gösterir")
    async def liste(self, interaction: discord.Interaction):
        rows = await db.get_faqs(interaction.guild.id)
        if not rows:
            return await interaction.response.send_message("📭 Henüz SSS kaydı yok.", ephemeral=True)
        lines = [f"• **{trig}** → {cut(ans, 80)}" for trig, ans in rows[:25]]
        await interaction.response.send_message(
            embed=discord.Embed(title="❓ Sık Sorulan Sorular", description="\n".join(lines), color=discord.Color.blurple())
        )

    async def _entries(self, guild_id: int):
        if guild_id not in self.cache:
            self.cache[guild_id] = await db.get_faqs(guild_id)
        return self.cache[guild_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot or not message.content:
            return
        entries = await self._entries(message.guild.id)
        if not entries:
            return
        low = message.content.lower()
        for trigger, answer in entries:
            if trigger in low:
                key = (message.channel.id, trigger)
                now = time.monotonic()
                if now - self.last_trigger.get(key, 0) < COOLDOWN_SECONDS:
                    return
                self.last_trigger[key] = now
                try:
                    await message.reply(answer, mention_author=False)
                except discord.HTTPException:
                    pass
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(FAQ(bot))
