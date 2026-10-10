import discord
from discord import app_commands
from discord.ext import commands

from utils import cut


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sunucubilgi", description="Sunucu hakkında bilgi verir")
    @app_commands.guild_only()
    async def sunucubilgi(self, interaction: discord.Interaction):
        g = interaction.guild
        bots = sum(1 for m in g.members if m.bot)
        toplam = g.member_count or len(g.members)

        e = discord.Embed(title=g.name, description=g.description, color=discord.Color.blurple())
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="Sahip", value=f"<@{g.owner_id}>")
        e.add_field(name="ID", value=f"`{g.id}`")
        e.add_field(name="Oluşturulma", value=discord.utils.format_dt(g.created_at, "D"))
        e.add_field(name="Üyeler", value=f"👥 {toplam - bots} kişi • 🤖 {bots} bot")
        e.add_field(
            name="Kanallar",
            value=f"💬 {len(g.text_channels)} yazı • 🔊 {len(g.voice_channels)} ses • 📁 {len(g.categories)} kategori",
        )
        e.add_field(name="Roller", value=str(len(g.roles) - 1))
        e.add_field(name="Boost", value=f"Seviye {g.premium_tier} ({g.premium_subscription_count} boost)")
        e.add_field(name="Emoji", value=f"{len(g.emojis)}/{g.emoji_limit}")
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="kullanicibilgi", description="Bir kullanıcı hakkında bilgi verir")
    @app_commands.describe(uye="Bilgisine bakılacak üye (boş bırakırsan kendin)")
    @app_commands.guild_only()
    async def kullanicibilgi(self, interaction: discord.Interaction, uye: discord.Member | None = None):
        m = uye or interaction.user

        e = discord.Embed(title=str(m), color=m.color if m.color.value else discord.Color.blurple())
        e.set_thumbnail(url=m.display_avatar.url)
        e.add_field(name="ID", value=f"`{m.id}`")
        e.add_field(name="Takma ad", value=m.nick or "-")
        e.add_field(name="Bot mu?", value="Evet" if m.bot else "Hayır")
        e.add_field(name="Hesap oluşturma", value=discord.utils.format_dt(m.created_at, "D"))
        if m.joined_at:
            e.add_field(name="Sunucuya katılma", value=discord.utils.format_dt(m.joined_at, "D"))
        e.add_field(name="En yüksek rol", value=m.top_role.mention if not m.top_role.is_default() else "-")

        roles = [r.mention for r in reversed(m.roles) if not r.is_default()]
        e.add_field(name=f"Roller ({len(roles)})", value=cut(" ".join(roles), 900) or "-", inline=False)

        if m.timed_out_until:
            e.add_field(name="Susturma", value=f"Bitiş: {discord.utils.format_dt(m.timed_out_until, 'R')}")
        await interaction.response.send_message(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
