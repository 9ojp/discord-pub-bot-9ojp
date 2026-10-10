import discord

import db


def cut(text: str | None, limit: int = 1000) -> str:
    """Embed alanlarına sığması için metni kısaltır."""
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def send_log(bot, guild: discord.Guild, embed: discord.Embed):
    """Sunucunun log kanalı ayarlıysa embed'i oraya gönderir."""
    channel_id = await db.get_log_channel(guild.id)
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def try_dm(user: discord.abc.User, text: str):
    """Kullanıcıya DM atmayı dener (DM'leri kapalıysa sessizce geçer)."""
    try:
        await user.send(text)
    except discord.HTTPException:
        pass


def can_act(interaction: discord.Interaction, target: discord.Member) -> str | None:
    """Moderasyon işlemi yapılabiliyorsa None, yapılamıyorsa sebep mesajı döndürür."""
    guild = interaction.guild
    if target.id == interaction.user.id:
        return "❌ Bu işlemi kendine uygulayamazsın."
    if target.id == guild.me.id:
        return "❌ Bu işlemi bana uygulayamazsın."
    if target.id == guild.owner_id:
        return "❌ Sunucu sahibine bu işlem uygulanamaz."
    if interaction.user.id != guild.owner_id and target.top_role >= interaction.user.top_role:
        return "❌ Rolü seninkine eşit veya senden yüksek olan birine bu işlemi uygulayamazsın."
    if target.top_role >= guild.me.top_role:
        return "❌ Bu üyenin rolü benimkinden yüksek ya da eşit. Bot rolünü yukarı taşı."
    return None


def action_embed(title: str, color: discord.Color, target, moderator, reason: str) -> discord.Embed:
    e = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    e.add_field(name="Kullanıcı", value=f"{target} (`{target.id}`)", inline=False)
    e.add_field(name="Yetkili", value=moderator.mention)
    e.add_field(name="Sebep", value=cut(reason, 500))
    return e
