import datetime as dt
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

Secenek = Optional[app_commands.Range[str, 1, 55]]


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="anket", description="Discord'un yerleşik anket özelliğiyle anket başlatır")
    @app_commands.describe(
        soru="Anket sorusu",
        secenek1="1. seçenek",
        secenek2="2. seçenek",
        secenek3="3. seçenek (opsiyonel)",
        secenek4="4. seçenek (opsiyonel)",
        secenek5="5. seçenek (opsiyonel)",
        saat="Anket kaç saat açık kalsın? (varsayılan 24)",
        coklu="Birden fazla seçenek işaretlenebilsin mi?",
    )
    @app_commands.guild_only()
    async def anket(
        self,
        interaction: discord.Interaction,
        soru: app_commands.Range[str, 1, 300],
        secenek1: app_commands.Range[str, 1, 55],
        secenek2: app_commands.Range[str, 1, 55],
        secenek3: Secenek = None,
        secenek4: Secenek = None,
        secenek5: Secenek = None,
        saat: app_commands.Range[int, 1, 168] = 24,
        coklu: bool = False,
    ):
        poll = discord.Poll(question=soru, duration=dt.timedelta(hours=saat), multiple=coklu)
        for secenek in (secenek1, secenek2, secenek3, secenek4, secenek5):
            if secenek:
                poll.add_answer(text=secenek)
        await interaction.response.send_message(poll=poll)

    @app_commands.command(name="oylama", description="Evet/Hayır şeklinde hızlı oylama başlatır")
    @app_commands.describe(soru="Oylanacak konu")
    @app_commands.guild_only()
    async def oylama(self, interaction: discord.Interaction, soru: app_commands.Range[str, 1, 250]):
        embed = discord.Embed(title="🗳️ Oylama", description=soru, color=discord.Color.blurple())
        embed.set_footer(text=f"{interaction.user.display_name} başlattı • 👍 evet, 👎 hayır")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")


async def setup(bot: commands.Bot):
    await bot.add_cog(Polls(bot))
