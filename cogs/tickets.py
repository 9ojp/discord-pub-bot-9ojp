import io

import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import cut, send_log

PANEL_TITLE = "🎫 Destek Talebi"
PANEL_DESC = "Yardıma mı ihtiyacın var? Aşağıdaki butona basarak sana özel bir destek kanalı açabilirsin."


class TicketPanelView(discord.ui.View):
    """Kalıcı panel: bot yeniden başlasa da buton çalışmaya devam eder."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket Aç", style=discord.ButtonStyle.green, emoji="🎫", custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("Tickets")
        await cog.create_ticket_channel(interaction)


class CloseView(discord.ui.View):
    """Ticket kanalının içindeki kapatma butonu."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket'ı Kapat", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: Tickets = interaction.client.get_cog("Tickets")
        await cog.close_ticket_channel(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Butonlar bot yeniden başlasa da çalışsın diye kalıcı view'ları burada kaydediyoruz.
        bot.add_view(TicketPanelView())
        bot.add_view(CloseView())

    ticket = app_commands.Group(
        name="ticket",
        description="Destek talebi (ticket) sistemi ayarları",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ---------- ayarlar ----------

    @ticket.command(name="ayarla", description="Ticket sistemini kurar")
    @app_commands.describe(kategori="Ticket kanallarının açılacağı kategori", yetkili_rol="Ticket'ları görecek destek rolü")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ayarla(self, interaction: discord.Interaction, kategori: discord.CategoryChannel, yetkili_rol: discord.Role):
        guild = interaction.guild
        if not guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "❌ Bende **Kanalları Yönet** yetkisi yok. Bot rolüne bu yetkiyi ver.", ephemeral=True
            )
        await db.set_ticket_config(guild.id, kategori.id, yetkili_rol.id)
        await interaction.response.send_message(
            f"✅ Ticket sistemi kuruldu.\n📁 Kategori: {kategori.mention}\n👮 Destek rolü: {yetkili_rol.mention}\n\n"
            "Şimdi `/ticket panel` ile bir kanala buton panelini gönder.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ticket.command(name="panel", description="Bu kanala 'Ticket Aç' butonunu gönderir")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction):
        category_id, staff_id = await db.get_ticket_config(interaction.guild.id)
        if not category_id or not staff_id:
            return await interaction.response.send_message(
                "❌ Önce `/ticket ayarla` ile kategori ve destek rolünü ayarla.", ephemeral=True
            )
        embed = discord.Embed(title=PANEL_TITLE, description=PANEL_DESC, color=discord.Color.blurple())
        await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message("✅ Panel gönderildi.", ephemeral=True)

    # ---------- ticket açma / kapatma ----------

    async def create_ticket_channel(self, interaction: discord.Interaction):
        guild = interaction.guild
        category_id, staff_id = await db.get_ticket_config(guild.id)
        if not category_id:
            return await interaction.response.send_message(
                "❌ Ticket sistemi henüz kurulmamış. Bir yetkiliye haber ver.", ephemeral=True
            )
        category = guild.get_channel(category_id)
        staff_role = guild.get_role(staff_id)
        if category is None:
            return await interaction.response.send_message(
                "❌ Ayarlı kategori silinmiş. Bir yetkilinin `/ticket ayarla` ile yeniden kurması gerekiyor.", ephemeral=True
            )

        existing = await db.has_open_ticket(guild.id, interaction.user.id)
        if existing and guild.get_channel(existing):
            return await interaction.response.send_message(
                f"❌ Zaten açık bir ticket'ın var: <#{existing}>", ephemeral=True
            )

        if not guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "❌ Bende **Kanalları Yönet** yetkisi yok, kanal oluşturamıyorum.", ephemeral=True
            )
        if len(category.channels) >= 50:
            return await interaction.response.send_message(
                "❌ Ticket kategorisi dolu (Discord limiti: 50 kanal). Bir yetkilinin eski ticket'ları kapatması gerekiyor.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)
        number = await db.next_ticket_number(guild.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{number:04d}",
            category=category,
            overwrites=overwrites,
            reason=f"Ticket açıldı: {interaction.user}",
        )
        await db.create_ticket(channel.id, guild.id, interaction.user.id, number)

        embed = discord.Embed(
            title=f"🎫 Ticket #{number:04d}",
            description=f"Merhaba {interaction.user.mention}! Sorununu buraya yazabilirsin, "
                         f"{staff_role.mention if staff_role else 'yetkili ekip'} en kısa sürede yardımcı olacak.",
            color=discord.Color.green(),
        )
        await channel.send(
            content=f"{interaction.user.mention}" + (f" {staff_role.mention}" if staff_role else ""),
            embed=embed,
            view=CloseView(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )

        await interaction.followup.send(f"✅ Ticket'ın açıldı: {channel.mention}", ephemeral=True)

        log = discord.Embed(title="🎫 Ticket açıldı", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        log.add_field(name="Kullanıcı", value=interaction.user.mention)
        log.add_field(name="Kanal", value=channel.mention)
        log.add_field(name="Numara", value=f"#{number:04d}")
        await send_log(self.bot, guild, log)

    async def close_ticket_channel(self, interaction: discord.Interaction):
        row = await db.get_ticket(interaction.channel.id)
        if not row:
            return await interaction.response.send_message("❌ Bu kanal bir ticket değil.", ephemeral=True)
        guild_id, opener_id, number, closed = row
        if closed:
            return await interaction.response.send_message("❌ Bu ticket zaten kapatılmış.", ephemeral=True)

        _, staff_id = await db.get_ticket_config(guild_id)
        staff_role = interaction.guild.get_role(staff_id) if staff_id else None
        is_staff = staff_role in interaction.user.roles if staff_role else False
        if not (is_staff or interaction.user.guild_permissions.manage_guild or interaction.user.id == opener_id):
            return await interaction.response.send_message("❌ Bu ticket'ı kapatma yetkin yok.", ephemeral=True)

        await interaction.response.send_message("🔒 Ticket kapatılıyor, transkript hazırlanıyor...")
        await db.close_ticket(interaction.channel.id)

        transcript_lines = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            when = msg.created_at.strftime("%Y-%m-%d %H:%M")
            transcript_lines.append(f"[{when}] {msg.author}: {msg.content}")
            for a in msg.attachments:
                transcript_lines.append(f"    📎 {a.filename}: {a.url}")
        transcript = "\n".join(transcript_lines) or "(mesaj yok)"

        opener = interaction.guild.get_member(opener_id)
        log = discord.Embed(
            title="🔒 Ticket kapatıldı",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        log.add_field(name="Numara", value=f"#{number:04d}")
        log.add_field(name="Açan", value=opener.mention if opener else f"`{opener_id}`")
        log.add_field(name="Kapatan", value=interaction.user.mention)

        channel_id_for_log = await db.get_log_channel(guild_id)
        if channel_id_for_log:
            log_channel = interaction.guild.get_channel(channel_id_for_log)
            if log_channel:
                file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"ticket-{number:04d}.txt")
                try:
                    await log_channel.send(embed=log, file=file)
                except discord.HTTPException:
                    pass

        await interaction.channel.send("🗑️ Bu kanal 10 saniye içinde silinecek.")
        await discord.utils.sleep_until(discord.utils.utcnow() + __import__("datetime").timedelta(seconds=10))
        try:
            await interaction.channel.delete(reason=f"Ticket kapatıldı: {interaction.user}")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
