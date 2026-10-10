import discord
from discord import app_commands
from discord.ext import commands

import db

DEFAULT_WELCOME = "🎉 {kullanici}, **{sunucu}** sunucusuna hoş geldin! Artık {sayac}. üyemizsin."
DEFAULT_LEAVE = "👋 **{kullanici}** sunucudan ayrıldı. Artık {sayac} üyemiz var."

PLACEHOLDER_HELP = "Kullanabileceğin yerler: `{kullanici}` (etiket), `{kullanici_adi}` (sade isim), `{sunucu}`, `{sayac}` (üye sayısı)"


def fmt(template: str, member: discord.Member) -> str:
    return (
        template.replace("{kullanici}", member.mention)
        .replace("{kullanici_adi}", member.display_name)
        .replace("{sunucu}", member.guild.name)
        .replace("{sayac}", str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    hosgeldin = app_commands.Group(
        name="hosgeldin", description="Hoş geldin mesajı ayarları", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )
    veda = app_commands.Group(
        name="veda", description="Ayrılma (güle güle) mesajı ayarları", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @hosgeldin.command(name="ayarla", description="Hoş geldin mesajını açar/ayarlar")
    @app_commands.describe(kanal="Mesajın gönderileceği kanal", mesaj=f"Özel mesaj (boş bırakırsan varsayılan kullanılır). {PLACEHOLDER_HELP}")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hosgeldin_ayarla(self, interaction: discord.Interaction, kanal: discord.TextChannel, mesaj: str | None = None):
        perms = kanal.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            return await interaction.response.send_message("❌ Bu kanala mesaj/embed gönderme yetkim yok.", ephemeral=True)
        await db.set_welcome(interaction.guild.id, kanal.id, mesaj)
        await interaction.response.send_message(
            f"✅ Hoş geldin mesajı {kanal.mention} kanalına gönderilecek.\n{PLACEHOLDER_HELP}"
        )

    @hosgeldin.command(name="kapat", description="Hoş geldin mesajını kapatır")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hosgeldin_kapat(self, interaction: discord.Interaction):
        await db.set_welcome(interaction.guild.id, None, None)
        await interaction.response.send_message("✅ Hoş geldin mesajı kapatıldı.")

    @hosgeldin.command(name="test", description="Hoş geldin mesajını şimdi dener")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hosgeldin_test(self, interaction: discord.Interaction):
        channel_id, template = await db.get_welcome(interaction.guild.id)
        if not channel_id:
            return await interaction.response.send_message("❌ Hoş geldin mesajı ayarlı değil.", ephemeral=True)
        await interaction.response.send_message(
            embed=self._embed(template or DEFAULT_WELCOME, interaction.user, discord.Color.green(), "👋 Hoş geldin!")
        )

    @veda.command(name="ayarla", description="Ayrılma mesajını açar/ayarlar")
    @app_commands.describe(kanal="Mesajın gönderileceği kanal", mesaj=f"Özel mesaj (boş bırakırsan varsayılan kullanılır). {PLACEHOLDER_HELP}")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def veda_ayarla(self, interaction: discord.Interaction, kanal: discord.TextChannel, mesaj: str | None = None):
        perms = kanal.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            return await interaction.response.send_message("❌ Bu kanala mesaj/embed gönderme yetkim yok.", ephemeral=True)
        await db.set_leave(interaction.guild.id, kanal.id, mesaj)
        await interaction.response.send_message(f"✅ Ayrılma mesajı {kanal.mention} kanalına gönderilecek.\n{PLACEHOLDER_HELP}")

    @veda.command(name="kapat", description="Ayrılma mesajını kapatır")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def veda_kapat(self, interaction: discord.Interaction):
        await db.set_leave(interaction.guild.id, None, None)
        await interaction.response.send_message("✅ Ayrılma mesajı kapatıldı.")

    def _embed(self, template: str, member: discord.Member, color: discord.Color, title: str) -> discord.Embed:
        e = discord.Embed(description=fmt(template, member), color=color)
        e.set_author(name=title)
        e.set_thumbnail(url=member.display_avatar.url)
        return e

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        channel_id, template = await db.get_welcome(member.guild.id)
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return
        try:
            await channel.send(embed=self._embed(template or DEFAULT_WELCOME, member, discord.Color.green(), "👋 Hoş geldin!"))
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        channel_id, template = await db.get_leave(member.guild.id)
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return
        try:
            await channel.send(embed=self._embed(template or DEFAULT_LEAVE, member, discord.Color.red(), "👋 Güle güle"))
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
