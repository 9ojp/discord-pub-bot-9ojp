import discord
from discord import app_commands
from discord.ext import commands

import db


class ReactionRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    tepkirol = app_commands.Group(
        name="tepkirol", description="Tepki (reaksiyon) ile rol verme", guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @tepkirol.command(name="ekle", description="Bir mesaja tepki-rol bağlantısı ekler")
    @app_commands.describe(
        mesaj_id="Tepki eklenecek mesajın ID'si (aynı kanalda olmalı)",
        emoji="Kullanılacak emoji (standart ya da sunucu emojisi)",
        rol="Tepki verince alınacak rol",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def ekle(self, interaction: discord.Interaction, mesaj_id: str, emoji: str, rol: discord.Role):
        if not mesaj_id.isdigit():
            return await interaction.response.send_message("❌ Geçerli bir mesaj ID'si gir.", ephemeral=True)
        guild = interaction.guild

        if rol.managed:
            return await interaction.response.send_message("❌ Bu rol bir bota ait, verilemez.", ephemeral=True)
        if not guild.me.guild_permissions.manage_roles:
            return await interaction.response.send_message("❌ Bende **Rolleri Yönet** yetkisi yok.", ephemeral=True)
        if rol >= guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Bu rol benim rolümden yüksek/eşit. Bot rolünü yukarı taşı.", ephemeral=True
            )

        try:
            message = await interaction.channel.fetch_message(int(mesaj_id))
        except discord.NotFound:
            return await interaction.response.send_message(
                "❌ Bu mesaj bulunamadı. Komutu, mesajın bulunduğu kanalda kullanmalısın.", ephemeral=True
            )
        except discord.HTTPException as e:
            return await interaction.response.send_message(f"❌ Mesaj alınamadı: {e}", ephemeral=True)

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await interaction.response.send_message(
                "❌ Bu emojiyi kullanamadım. Standart bir emoji ya da bu sunucuya ait bir emoji kullan.", ephemeral=True
            )

        key = str(discord.PartialEmoji.from_str(emoji))
        ok = await db.add_reaction_role(guild.id, message.id, key, rol.id)
        if not ok:
            return await interaction.response.send_message("❌ Bu mesaj + emoji kombinasyonu zaten tanımlı.", ephemeral=True)

        await interaction.response.send_message(f"✅ Bu mesaja {emoji} tepkisi verenler artık {rol.mention} rolünü alacak.")

    @tepkirol.command(name="sil", description="Bir tepki-rol bağlantısını kaldırır")
    @app_commands.describe(mesaj_id="Mesaj ID'si", emoji="Kaldırılacak emoji")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def sil(self, interaction: discord.Interaction, mesaj_id: str, emoji: str):
        if not mesaj_id.isdigit():
            return await interaction.response.send_message("❌ Geçerli bir mesaj ID'si gir.", ephemeral=True)
        key = str(discord.PartialEmoji.from_str(emoji))
        ok = await db.remove_reaction_role(int(mesaj_id), key)
        if ok:
            await interaction.response.send_message("🗑️ Bağlantı kaldırıldı.")
        else:
            await interaction.response.send_message("❌ Böyle bir bağlantı bulunamadı.", ephemeral=True)

    @tepkirol.command(name="liste", description="Bir mesajdaki tüm tepki-rol bağlantılarını gösterir")
    @app_commands.describe(mesaj_id="Mesaj ID'si")
    async def liste(self, interaction: discord.Interaction, mesaj_id: str):
        if not mesaj_id.isdigit():
            return await interaction.response.send_message("❌ Geçerli bir mesaj ID'si gir.", ephemeral=True)
        rows = await db.get_reaction_roles_for_message(int(mesaj_id))
        if not rows:
            return await interaction.response.send_message("📭 Bu mesaj için tanımlı tepki-rol yok.", ephemeral=True)
        lines = [f"{emoji} → <@&{role_id}>" for emoji, role_id in rows]
        await interaction.response.send_message(
            "\n".join(lines), allowed_mentions=discord.AllowedMentions.none()
        )

    # ---------- olaylar (raw: mesaj cache'de olmasa da çalışsın diye) ----------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or (payload.member and payload.member.bot):
            return
        role_id = await db.get_reaction_role(payload.message_id, str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        member = payload.member or guild.get_member(payload.user_id)
        if role is None or member is None:
            return
        try:
            await member.add_roles(role, reason="Tepki ile rol")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        role_id = await db.get_reaction_role(payload.message_id, str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        if role is None or member is None or member.bot:
            return
        try:
            await member.remove_roles(role, reason="Tepki kaldırıldı")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRole(bot))
