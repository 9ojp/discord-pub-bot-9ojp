import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import db

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

EXTENSIONS = [
    "cogs.moderation",
    "cogs.logs",
    "cogs.polls",
    "cogs.music",
    "cogs.info",
    "cogs.dm",
    "cogs.autorole",
    "cogs.tickets",
    "cogs.automod",
    "cogs.giveaway",
    "cogs.faq",
    "cogs.welcome",
    "cogs.reactionrole",
    "cogs.stats",
    "cogs.modmail",
]


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # giriş/çıkış logları, üye bilgisi
        intents.message_content = True  # silinen/düzenlenen mesaj içeriği
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self):
        await db.init()
        for ext in EXTENSIONS:
            await self.load_extension(ext)

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        print(f"✅ {self.user} olarak giriş yapıldı ({len(self.guilds)} sunucu)")

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Bu komutu kullanmak için yetkin yok."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "❌ Bunu yapmak için bende gerekli yetki yok."
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "❌ Bu komut sadece sunucularda kullanılabilir."
        else:
            logging.getLogger("bot").exception("Komut hatası", exc_info=error)
            msg = "❌ Beklenmeyen bir hata oluştu."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN bulunamadı. .env dosyasını kontrol et.")
    logging.basicConfig(level=logging.INFO)
    MyBot().run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
