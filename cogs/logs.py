import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import cut, send_log


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="logkanal", description="Log mesajlarının gönderileceği kanalı ayarlar")
    @app_commands.describe(kanal="Log kanalı")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logkanal(self, interaction: discord.Interaction, kanal: discord.TextChannel):
        perms = kanal.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            return await interaction.response.send_message(
                "❌ Bu kanala mesaj göndermek ve embed eklemek için yetkim yok.", ephemeral=True
            )
        await db.set_log_channel(interaction.guild.id, kanal.id)
        await interaction.response.send_message(f"✅ Log kanalı {kanal.mention} olarak ayarlandı.")

    @app_commands.command(name="logkapat", description="Log sistemini kapatır")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logkapat(self, interaction: discord.Interaction):
        await db.set_log_channel(interaction.guild.id, None)
        await interaction.response.send_message("✅ Log sistemi kapatıldı.")

    # ---------- OLAYLAR ----------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        e = discord.Embed(title="🗑️ Mesaj silindi", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        e.add_field(name="Yazar", value=f"{message.author.mention} (`{message.author.id}`)")
        e.add_field(name="Kanal", value=message.channel.mention)
        e.add_field(name="İçerik", value=cut(message.content) or "*(boş veya sadece dosya)*", inline=False)
        if message.attachments:
            e.add_field(name="Ekler", value=cut("\n".join(a.filename for a in message.attachments)), inline=False)
        await send_log(self.bot, message.guild, e)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        e = discord.Embed(
            title="✏️ Mesaj düzenlendi",
            description=f"[Mesaja git]({after.jump_url})",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        e.add_field(name="Yazar", value=f"{after.author.mention} (`{after.author.id}`)")
        e.add_field(name="Kanal", value=after.channel.mention)
        e.add_field(name="Önce", value=cut(before.content) or "*(boş)*", inline=False)
        e.add_field(name="Sonra", value=cut(after.content) or "*(boş)*", inline=False)
        await send_log(self.bot, after.guild, e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        e = discord.Embed(title="📥 Üye katıldı", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        e.add_field(name="Üye", value=f"{member.mention} (`{member.id}`)")
        e.add_field(name="Hesap oluşturma", value=discord.utils.format_dt(member.created_at, "R"))
        e.set_thumbnail(url=member.display_avatar.url)
        await send_log(self.bot, member.guild, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        e = discord.Embed(title="📤 Üye ayrıldı", color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
        e.add_field(name="Üye", value=f"{member} (`{member.id}`)")
        if member.joined_at:
            e.add_field(name="Katılma", value=discord.utils.format_dt(member.joined_at, "R"))
        roles = [r.mention for r in member.roles if not r.is_default()]
        if roles:
            e.add_field(name="Roller", value=cut(" ".join(roles)), inline=False)
        e.set_thumbnail(url=member.display_avatar.url)
        await send_log(self.bot, member.guild, e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
