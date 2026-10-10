import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import send_log

# Yeni gelen HERKESE verilirse tehlikeli olacak yetkiler
DANGEROUS = {
    "administrator": "Yönetici",
    "manage_guild": "Sunucuyu Yönet",
    "manage_roles": "Rolleri Yönet",
    "manage_channels": "Kanalları Yönet",
    "manage_messages": "Mesajları Yönet",
    "manage_webhooks": "Webhook'ları Yönet",
    "kick_members": "Üyeleri At",
    "ban_members": "Üyeleri Yasakla",
    "moderate_members": "Üyeleri Susturma",
    "mention_everyone": "@everyone Etiketleme",
}


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    otorol = app_commands.Group(
        name="otorol",
        description="Yeni gelen üyelere otomatik rol verme",
        guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True),
    )

    @otorol.command(name="ayarla", description="Yeni gelen üyelere verilecek rolü ayarlar")
    @app_commands.describe(rol="Yeni üyelere otomatik verilecek rol")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def ayarla(self, interaction: discord.Interaction, rol: discord.Role):
        guild = interaction.guild

        if rol.is_default():
            return await interaction.response.send_message("❌ @everyone rolü seçilemez.", ephemeral=True)
        if rol.managed:
            return await interaction.response.send_message(
                "❌ Bu rol bir bot ya da entegrasyona ait, üyelere verilemez.", ephemeral=True
            )
        if not guild.me.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "❌ Bende **Rolleri Yönet** yetkisi yok. Bot rolüne bu yetkiyi ver.", ephemeral=True
            )
        if rol >= guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Bu rol benim rolümden yüksek ya da eşit. Sunucu Ayarları → Roller'de "
                "bot rolünü bu rolün **üstüne** sürükle.",
                ephemeral=True,
            )
        if interaction.user.id != guild.owner_id and rol >= interaction.user.top_role:
            return await interaction.response.send_message(
                "❌ Kendi en yüksek rolünden yüksek ya da eşit bir rolü ayarlayamazsın.", ephemeral=True
            )

        tehlikeli = [label for perm, label in DANGEROUS.items() if getattr(rol.permissions, perm)]
        if tehlikeli:
            return await interaction.response.send_message(
                "❌ Bu rol tehlikeli yetkiler içeriyor (" + ", ".join(tehlikeli) + "). "
                "Yeni gelen herkese verilmesi güvenli değil. Yetkisiz bir rol seç.",
                ephemeral=True,
            )

        await db.set_autorole(guild.id, rol.id)
        await interaction.response.send_message(
            f"✅ Yeni gelen üyelere otomatik olarak {rol.mention} rolü verilecek.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @otorol.command(name="kapat", description="Otomatik rol vermeyi kapatır")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def kapat(self, interaction: discord.Interaction):
        await db.set_autorole(interaction.guild.id, None)
        await interaction.response.send_message("✅ Otomatik rol verme kapatıldı.")

    @otorol.command(name="goster", description="Ayarlı otomatik rolü gösterir")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def goster(self, interaction: discord.Interaction):
        role_id = await db.get_autorole(interaction.guild.id)
        if not role_id:
            return await interaction.response.send_message("ℹ️ Otomatik rol şu an **kapalı**.", ephemeral=True)
        role = interaction.guild.get_role(role_id)
        if role is None:
            return await interaction.response.send_message(
                "⚠️ Ayarlı rol silinmiş. `/otorol ayarla` ile yeni bir rol seç.", ephemeral=True
            )
        await interaction.response.send_message(
            f"ℹ️ Yeni üyelere verilen rol: {role.mention}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ---------- olaylar ----------

    async def give_role(self, member: discord.Member):
        if member.bot:
            return
        guild = member.guild
        role_id = await db.get_autorole(guild.id)
        if not role_id:
            return
        role = guild.get_role(role_id)
        if role is None or role in member.roles:
            return
        try:
            await member.add_roles(role, reason="Otomatik rol (yeni üye)")
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="⚠️ Otomatik rol verilemedi",
                description=f"{member.mention} kullanıcısına {role.mention} verilemedi.\n"
                            f"Bot rolünün bu rolün üstünde olduğundan ve **Rolleri Yönet** yetkisi olduğundan emin ol.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text=f"Hata: {str(e)[:100]}")
            await send_log(self.bot, guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Kural ekranı (Membership Screening) açıksa onay verene kadar bekle
        if not member.pending:
            await self.give_role(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.pending and not after.pending:
            await self.give_role(after)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
