import discord
from discord import app_commands
from discord.ext import commands

import db
from utils import cut, send_log

PENDING_TIMEOUT = 120  # sn: birden fazla sunucu varsa seçim bekleme süresi


class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Sohbeti Kapat", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="modmail:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog: ModMail = interaction.client.get_cog("ModMail")
        await cog.close_thread(interaction)


class GuildSelect(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption], message_content: str, attachments: list[str]):
        super().__init__(placeholder="Hangi sunucuyla ilgili yazmak istiyorsun?", options=options)
        self.message_content = message_content
        self.attachments = attachments

    async def callback(self, interaction: discord.Interaction):
        cog: ModMail = interaction.client.get_cog("ModMail")
        guild_id = int(self.values[0])
        await interaction.response.edit_message(content="✅ Mesajın iletildi.", view=None)
        await cog.open_or_forward(interaction.user, guild_id, self.message_content, self.attachments)


class GuildSelectView(discord.ui.View):
    def __init__(self, options, message_content, attachments):
        super().__init__(timeout=PENDING_TIMEOUT)
        self.add_item(GuildSelect(options, message_content, attachments))


class ModMail(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(CloseView())

    modmail = app_commands.Group(
        name="modmail", description="DM üzerinden destek (modmail) sistemi", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @modmail.command(name="ayarla", description="Modmail sistemini kurar")
    @app_commands.describe(kategori="Yazışma kanallarının açılacağı kategori", yetkili_rol="Mesajları görecek destek rolü")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ayarla(self, interaction: discord.Interaction, kategori: discord.CategoryChannel, yetkili_rol: discord.Role):
        if not interaction.guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message("❌ Bende **Kanalları Yönet** yetkisi yok.", ephemeral=True)
        await db.set_modmail_config(interaction.guild.id, kategori.id, yetkili_rol.id)
        await interaction.response.send_message(
            f"✅ Modmail kuruldu. Artık biri botuma özel mesaj (DM) attığında {kategori.mention} içinde "
            f"bir kanal açılacak ve {yetkili_rol.mention} etiketlenecek.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @modmail.command(name="kapat", description="Bu modmail sohbetini kapatır (kanalın içinde kullan)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def kapat_komutu(self, interaction: discord.Interaction):
        await self.close_thread(interaction)

    # ---------- kullanıcıdan gelen DM ----------

    def _eligible_guilds(self, user: discord.abc.User, guild_ids: list[int]) -> list[discord.Guild]:
        result = []
        for gid in guild_ids:
            guild = self.bot.get_guild(gid)
            if guild and guild.get_member(user.id):
                result.append(guild)
        return result

    async def handle_dm(self, message: discord.Message):
        user = message.author
        attachments = [a.url for a in message.attachments]

        existing = await db.get_open_modmail_thread_for_user(user.id)
        if existing:
            channel_id, guild_id = existing
            await self._forward_to_channel(channel_id, guild_id, user, message.content, attachments)
            return

        configured = await db.get_modmail_configured_guild_ids()
        guilds = self._eligible_guilds(user, configured)

        if not guilds:
            await user.send(
                "❌ Şu an bu bot üzerinden ulaşabileceğin aktif bir destek hattı yok. "
                "Mesajını ilgili sunucuda bir yetkiliye iletmeyi dene."
            )
            return

        if len(guilds) == 1:
            await self.open_or_forward(user, guilds[0].id, message.content, attachments)
            return

        options = [discord.SelectOption(label=g.name[:100], value=str(g.id)) for g in guilds[:25]]
        await user.send(
            "Birden fazla sunucuda destek hattına erişimin var. Mesajını hangisine iletmemi istersin?",
            view=GuildSelectView(options, message.content, attachments),
        )

    async def open_or_forward(self, user: discord.abc.User, guild_id: int, content: str, attachments: list[str]):
        again = await db.get_open_modmail_thread_for_user(user.id)
        if again:
            await self._forward_to_channel(again[0], again[1], user, content, attachments)
            return
        await self._create_thread(user, guild_id, content, attachments)

    async def _create_thread(self, user: discord.abc.User, guild_id: int, content: str, attachments: list[str]):
        guild = self.bot.get_guild(guild_id)
        category_id, staff_id = await db.get_modmail_config(guild_id)
        category = guild.get_channel(category_id) if category_id else None
        staff_role = guild.get_role(staff_id) if staff_id else None

        if category is None or not guild.me.guild_permissions.manage_channels:
            await user.send("❌ Bu sunucuda destek hattı şu an kullanılamıyor. Daha sonra tekrar dene.")
            return
        if len(category.channels) >= 50:
            await user.send("❌ Destek hattı şu an dolu, lütfen daha sonra tekrar dene.")
            return

        number = await db.next_modmail_number(guild_id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(
            name=f"dm-{number:04d}",
            category=category,
            overwrites=overwrites,
            reason=f"Modmail: {user}",
        )
        await db.create_modmail_thread(channel.id, guild.id, user.id, number)

        embed = discord.Embed(
            title=f"📩 Yeni DM Sohbeti #{number:04d}",
            description=f"**{user}** (`{user.id}`) botuma özel mesaj gönderdi.\n\n"
                        "Buraya yazdığın her şey (botun kendi mesajları hariç) otomatik olarak kullanıcıya DM olarak iletilir.",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await channel.send(
            content=staff_role.mention if staff_role else None,
            embed=embed,
            view=CloseView(),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        await self._send_message_block(channel, content, attachments)

        try:
            await user.send(f"✅ Mesajın **{guild.name}** destek ekibine iletildi. Cevap gelince burada göreceksin.")
        except discord.HTTPException:
            pass

        log = discord.Embed(title="📩 Modmail açıldı", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        log.add_field(name="Kullanıcı", value=f"{user} (`{user.id}`)")
        log.add_field(name="Kanal", value=channel.mention)
        await send_log(self.bot, guild, log)

    async def _forward_to_channel(self, channel_id: int, guild_id: int, user: discord.abc.User, content: str, attachments: list[str]):
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if channel is None:
            await db.close_modmail_thread(channel_id)
            await user.send("❌ Önceki sohbet kanalı artık yok. Yeni bir mesaj gönderirsen yeni bir sohbet açılır.")
            return
        await self._send_message_block(channel, content, attachments, prefix=f"**{user}:** ")

    async def _send_message_block(self, channel: discord.abc.Messageable, content: str, attachments: list[str], prefix: str = ""):
        text = prefix + (content or "*(boş mesaj)*")
        for url in attachments:
            text += f"\n📎 {url}"
        try:
            await channel.send(cut(text, 1900))
        except discord.HTTPException:
            pass

    # ---------- kanaldan gelen mesaj -> kullanıcıya DM ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            await self.handle_dm(message)
            return

        row = await db.get_modmail_thread_by_channel(message.channel.id)
        if not row:
            return
        guild_id, user_id, number, closed = row
        if closed:
            return

        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                return

        text = message.content or ""
        for a in message.attachments:
            text += f"\n📎 {a.url}"
        if not text.strip():
            return
        try:
            await user.send(f"📩 **{message.guild.name} destek ekibi:**\n{cut(text, 1900)}")
        except discord.HTTPException:
            await message.channel.send("⚠️ Bu mesaj kullanıcıya iletilemedi (DM'leri kapalı olabilir).")

    # ---------- kapatma ----------

    async def close_thread(self, interaction: discord.Interaction):
        row = await db.get_modmail_thread_by_channel(interaction.channel.id)
        if not row:
            return await interaction.response.send_message("❌ Bu kanal bir modmail sohbeti değil.", ephemeral=True)
        guild_id, user_id, number, closed = row
        if closed:
            return await interaction.response.send_message("❌ Bu sohbet zaten kapatılmış.", ephemeral=True)

        await interaction.response.send_message("🔒 Sohbet kapatılıyor...")
        await db.close_modmail_thread(interaction.channel.id)

        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                user = None
        if user:
            try:
                await user.send(f"🔒 **{interaction.guild.name}** ile olan destek sohbetin kapatıldı. "
                                 "Yeni bir mesaj gönderirsen yeni bir sohbet açılır.")
            except discord.HTTPException:
                pass

        await interaction.channel.send("🗑️ Bu kanal 10 saniye içinde silinecek.")
        await discord.utils.sleep_until(discord.utils.utcnow() + __import__("datetime").timedelta(seconds=10))
        try:
            await interaction.channel.delete(reason=f"Modmail kapatıldı: {interaction.user}")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ModMail(bot))
