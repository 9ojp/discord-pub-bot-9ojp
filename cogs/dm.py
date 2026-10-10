import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from utils import send_log

MAX_RECIPIENTS = 200   # Tek seferde en fazla kişi (Discord'un spam korumasına takılmamak için)
DELAY_SECONDS = 2.0    # Her mesaj arasında bekleme


class MesajModal(discord.ui.Modal, title="Role özel mesaj"):
    mesaj = discord.ui.TextInput(
        label="Göndermek istediğin mesaj",
        style=discord.TextStyle.paragraph,
        placeholder="Mesajını buraya yaz. Alt satıra geçebilirsin.",
        min_length=1,
        max_length=1800,
    )

    def __init__(self, cog: "DM", role: discord.Role):
        super().__init__()
        self.cog = cog
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        recipients = [m for m in self.role.members if not m.bot]
        text = str(self.mesaj)

        preview = discord.Embed(
            title="📨 Göndermeden önce kontrol et",
            description=text,
            color=discord.Color.orange(),
        )
        preview.add_field(name="Rol", value=self.role.mention)
        preview.add_field(name="Alıcı sayısı", value=f"{len(recipients)} kişi")
        preview.set_footer(text="Onaylarsan mesaj bu kişilere özel mesaj (DM) olarak gönderilir.")

        view = ConfirmView(self.cog, interaction.user, self.role, text, recipients)
        await interaction.response.send_message(embed=preview, view=view, ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, cog: "DM", author, role, text, recipients):
        super().__init__(timeout=180)
        self.cog, self.author, self.role, self.text, self.recipients = cog, author, role, text, recipients

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Gönder", style=discord.ButtonStyle.success, emoji="📨")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild.id in self.cog.sending:
            return await interaction.response.send_message("❌ Bu sunucuda zaten bir gönderim sürüyor.", ephemeral=True)

        self.cog.sending.add(guild.id)
        await interaction.response.edit_message(content="📨 Gönderim başladı...", embed=None, view=None)
        try:
            await self.cog.broadcast(interaction, self.role, self.text, self.recipients)
        finally:
            self.cog.sending.discard(guild.id)

    @discord.ui.button(label="İptal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ İptal edildi, hiçbir mesaj gönderilmedi.", embed=None, view=None)


class DM(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sending: set[int] = set()

    @app_commands.command(name="rolmesaj", description="Belirli role sahip üyelere özel mesaj (DM) gönderir")
    @app_commands.describe(rol="Mesajın gönderileceği rol")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def rolmesaj(self, interaction: discord.Interaction, rol: discord.Role):
        if rol.is_default():
            return await interaction.response.send_message(
                "❌ @everyone rolüne toplu mesaj gönderemem. Belirli bir rol seç.", ephemeral=True
            )
        recipients = [m for m in rol.members if not m.bot]
        if not recipients:
            return await interaction.response.send_message("❌ Bu role sahip (bot olmayan) üye yok.", ephemeral=True)
        if len(recipients) > MAX_RECIPIENTS:
            return await interaction.response.send_message(
                f"❌ Bu rolde {len(recipients)} kişi var. Tek seferde en fazla {MAX_RECIPIENTS} kişiye "
                "gönderebilirim. Daha küçük bir rol seç.",
                ephemeral=True,
            )
        if interaction.guild.id in self.sending:
            return await interaction.response.send_message("❌ Bu sunucuda zaten bir gönderim sürüyor.", ephemeral=True)

        await interaction.response.send_modal(MesajModal(self, rol))

    async def broadcast(self, interaction: discord.Interaction, role: discord.Role, text: str, recipients: list):
        guild = interaction.guild

        embed = discord.Embed(
            title=f"📢 {guild.name} sunucusundan mesaj",
            description=text,
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Bu mesaj, {guild.name} sunucusunda «{role.name}» rolüne sahip olduğun için gönderildi.")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        ok = closed = failed = 0
        total = len(recipients)
        for i, member in enumerate(recipients, start=1):
            try:
                await member.send(embed=embed)
                ok += 1
            except discord.Forbidden:
                closed += 1  # DM'leri kapalı
            except discord.HTTPException:
                failed += 1

            if i % 10 == 0 and i < total:
                try:
                    await interaction.edit_original_response(content=f"📨 Gönderiliyor... {i}/{total}")
                except discord.HTTPException:
                    pass
            await asyncio.sleep(DELAY_SECONDS)

        summary = (
            f"✅ **Gönderim bitti.**\n"
            f"• Ulaşan: **{ok}** kişi\n"
            f"• DM'leri kapalı olduğu için ulaşılamayan: **{closed}** kişi\n"
            f"• Hata: **{failed}** kişi"
        )
        try:
            await interaction.edit_original_response(content=summary)
        except discord.HTTPException:
            pass

        log = discord.Embed(title="📨 Role toplu mesaj gönderildi", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        log.add_field(name="Yetkili", value=interaction.user.mention)
        log.add_field(name="Rol", value=role.mention)
        log.add_field(name="Sonuç", value=f"{ok} ulaştı / {closed} DM kapalı / {failed} hata")
        await send_log(self.bot, guild, log)


async def setup(bot: commands.Bot):
    await bot.add_cog(DM(bot))
