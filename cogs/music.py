import asyncio
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque
from dataclasses import dataclass

import discord
import spotipy
import yt_dlp
from discord import app_commands
from discord.ext import commands
from spotipy.oauth2 import SpotifyClientCredentials

class _YTLogger:
    """yt-dlp uyarı ve hatalarını Railway loglarına yazar (teşhis için)."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        print(f"[yt-dlp uyarı] {msg}")

    def error(self, msg):
        print(f"[yt-dlp hata] {msg}")


print(f"[müzik] deno: {shutil.which('deno')} | yt-dlp: {yt_dlp.version.__version__}")

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "default_search": "ytsearch",
    "logger": _YTLogger(),
    # YouTube "n challenge" çözümü için JS runtime + çözücü script
    "js_runtimes": {"deno": {}},
    "remote_components": ["ejs:github"],
}
# Railway Variables ile ayarlanabilir: YT_CLIENTS=android_vr,web_safari  |  YT_USE_COOKIES=0
_clients = [c.strip() for c in os.getenv("YT_CLIENTS", "").split(",") if c.strip()]
if _clients:
    YTDL_OPTS["extractor_args"] = {"youtube": {"player_client": _clients}}
USE_COOKIES = os.getenv("YT_USE_COOKIES", "1") != "0"

# YouTube "bot değilsin" doğrulaması isterse çerez kullanılır.
# ÖNERİLEN: cookies.txt içeriğini Railway > Variables > YT_COOKIES olarak yapıştır (GitHub'a koyma!).
# Yedek: proje klasöründe cookies.txt varsa o kullanılır.
# yt-dlp dosyayı geri yazmak isteyebildiği için yazılabilir bir kopya (/tmp) kullanıyoruz.
_COOKIES_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt")
_COOKIES_COPY = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
COOKIES_LOADED = False
COOKIES_INFO = "çerez YOK (YT_COOKIES ya da cookies.txt yok)"
if USE_COOKIES:
    try:
        _text = os.getenv("YT_COOKIES", "").replace("\\n", "\n")
        _from = "YT_COOKIES değişkeni"
        if not _text.strip() and os.path.exists(_COOKIES_SRC):
            _text = open(_COOKIES_SRC, encoding="utf-8", errors="ignore").read()
            _from = "cookies.txt"
        if _text.strip():
            with open(_COOKIES_COPY, "w", encoding="utf-8") as _f:
                _f.write(_text)
            YTDL_OPTS["cookiefile"] = _COOKIES_COPY
            _lines = [l for l in _text.splitlines() if l.strip() and not l.startswith("#")]
            _has_login = "SAPISID" in _text or "__Secure-3PSID" in _text
            COOKIES_LOADED = True
            COOKIES_INFO = f"çerez BULUNDU ({_from}, {len(_lines)} çerez, giriş çerezi: {'var' if _has_login else 'YOK'})"
    except Exception as _e:  # noqa: BLE001
        COOKIES_INFO = f"çerez okunamadı: {_e}"

BOT_CHECK_HINTS = ("not a bot", "sign in to confirm")


def is_bot_check(error: Exception) -> bool:
    return any(h in str(error).lower() for h in BOT_CHECK_HINTS)


def bot_check_message() -> str:
    msg = "⚠️ **YouTube şarkıyı vermedi.** Botun çalıştığı sunucunun IP'sini bot sanıp doğrulama istiyor."
    if COOKIES_LOADED:
        msg += " Sunucuda `cookies.txt` var ama YouTube onu kabul etmedi (geçersiz olmuş ya da engellenmiş olabilir)."
    else:
        msg += " Sunucuda `cookies.txt` bulunamadı (GitHub'a doğru yere yüklenmemiş olabilir)."
    return msg


_HDR_KEYS = ("user-agent", "accept", "accept-language", "referer", "origin")


def ffmpeg_opts(headers: dict | None = None) -> dict:
    """yt-dlp'nin kullandığı header'ları ffmpeg'e de verir (googlevideo 403'ü önler)."""
    before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    if headers:
        hdr = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() in _HDR_KEYS)
        if hdr:
            before = f'-headers "{hdr}" ' + before
    return {"before_options": before, "options": "-vn"}

# ---------- yt-dlp -> ffmpeg pipe (403'ü aşmak için) ----------
# Linki doğrudan ffmpeg'e vermek googlevideo'da 403 verebiliyor. Bunun yerine sesi yt-dlp indirir
# (kendi istemci/PO token/parçalı indirme mantığıyla) ve ffmpeg'e stdin üzerinden aktarır.
# YT_MODE=url yaparsan eski yönteme (linki doğrudan ffmpeg'e verme) döner.
YT_MODE = os.getenv("YT_MODE", "pipe").lower()
PIPE_START_TIMEOUT = 30  # saniye: ilk ses verisi bu sürede gelmezse sıradaki istemciyi dene


def _client_attempts() -> list[list[str] | None]:
    if _clients:
        return [_clients]
    return [None, ["android_vr"], ["tv"]]  # None = yt-dlp varsayılanı


def _ytdlp_cmd(url: str, clients: list[str] | None) -> list[str]:
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio/best", "-o", "-", "-q", "--no-warnings",
        "--no-playlist", "--retries", "3", "--fragment-retries", "3",
        "--js-runtimes", "deno", "--remote-components", "ejs:github",
    ]
    if "cookiefile" in YTDL_OPTS:
        cmd += ["--cookies", YTDL_OPTS["cookiefile"]]
    if clients:
        cmd += ["--extractor-args", f"youtube:player_client={','.join(clients)}"]
    cmd.append(url)
    return cmd


class PipeSource(discord.FFmpegPCMAudio):
    """yt-dlp çıktısını ffmpeg'e aktaran ses kaynağı; bitince yt-dlp sürecini de kapatır."""

    def __init__(self, proc: subprocess.Popen):
        self._ytproc = proc
        super().__init__(proc.stdout, pipe=True, options="-vn")

    def cleanup(self):
        super().cleanup()
        try:
            self._ytproc.kill()
            self._ytproc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=self._ytproc.wait, daemon=True).start()


def _start_pipe(url: str, clients: list[str] | None) -> tuple[subprocess.Popen | None, str]:
    """yt-dlp'yi başlatır, ilk veri gelene kadar bekler. Başarısızsa (None, hata metni) döner."""
    proc = subprocess.Popen(_ytdlp_cmd(url, clients), stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    err_lines: list[str] = []

    def drain():
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", "ignore").strip()
            if line:
                err_lines.append(line)
                print(f"[yt-dlp pipe] {line}")

    threading.Thread(target=drain, daemon=True).start()

    # stdout okunabilir olana (veri ya da EOF) kadar bekle; veriyi tüketmeden (peek yok) kontrol et
    ready, _, _ = select.select([proc.stdout], [], [], PIPE_START_TIMEOUT)
    if ready:
        try:
            proc.wait(timeout=0.5)  # hemen çıktıysa hata mı bitiş mi anla
            failed = proc.returncode != 0
        except subprocess.TimeoutExpired:
            failed = False  # hâlâ çalışıyor ve veri geliyor: başarılı
        if not failed:
            return proc, ""
    proc.kill()
    proc.wait()
    return None, (err_lines[-1] if err_lines else "yt-dlp ses verisi vermedi (zaman aşımı)")


async def open_pipe_source(url: str) -> discord.AudioSource:
    loop = asyncio.get_running_loop()
    last_err = ""
    for clients in _client_attempts():
        proc, err = await loop.run_in_executor(None, _start_pipe, url, clients)
        if proc:
            print(f"[müzik] pipe modu OK (istemci: {','.join(clients) if clients else 'varsayılan'})")
            return PipeSource(proc)
        last_err = err
        print(f"[müzik] pipe başarısız (istemci: {clients or 'varsayılan'}): {err[:200]}")
        if is_bot_check(RuntimeError(err)):
            break  # bot kontrolünde diğer istemcileri denemek engeli sertleştirir
    raise RuntimeError(last_err or "Ses alınamadı.")

SPOTIFY_RE = re.compile(
    r"https?://open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|playlist)/([A-Za-z0-9]+)"
)
MAX_QUEUE = 100
MAX_SPOTIFY_TRACKS = 50
IDLE_LEAVE_SECONDS = 60


# ---------- yardımcılar ----------

def fmt_duration(sec) -> str:
    if not sec:
        return "?"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


async def extract(query: str) -> dict:
    """yt-dlp ile bir link ya da arama sorgusunu çözer (bloklamaması için thread'de çalışır)."""

    def run(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
        if info and "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise RuntimeError("Sonuç bulunamadı.")
            info = entries[0]
        if not info:
            raise RuntimeError("Sonuç bulunamadı.")
        return info

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, run, YTDL_OPTS)
    except Exception as e:  # noqa: BLE001
        # Çerez bozulduysa çerezsiz bir kez daha dene
        if "needs to be reloaded" in str(e) and "cookiefile" in YTDL_OPTS:
            opts = {k: v for k, v in YTDL_OPTS.items() if k != "cookiefile"}
            return await loop.run_in_executor(None, run, opts)
        raise


def make_spotify():
    if not (os.getenv("SPOTIPY_CLIENT_ID") and os.getenv("SPOTIPY_CLIENT_SECRET")):
        return None
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials())


def _name(track: dict) -> str:
    artist = track["artists"][0]["name"] if track.get("artists") else ""
    return f"{artist} - {track['name']}".strip(" -")


def spotify_queries(sp, kind: str, sid: str) -> list[str]:
    """Spotify bağlantısını 'Sanatçı - Şarkı' arama metinlerine çevirir."""
    if kind == "track":
        return [_name(sp.track(sid))]
    if kind == "album":
        items = sp.album_tracks(sid, limit=MAX_SPOTIFY_TRACKS)["items"]
        return [_name(t) for t in items]
    result = []
    for item in sp.playlist_items(sid, limit=MAX_SPOTIFY_TRACKS)["items"]:
        t = item.get("track") or item.get("item")
        if t:
            result.append(_name(t))
    return result


@dataclass
class Track:
    title: str
    query: str                      # yt-dlp'ye verilecek link ya da "ytsearch1:..." metni
    requester: discord.abc.User
    stream_url: str | None = None   # çalma anında çözülür (linkler süreli olduğu için)
    webpage_url: str | None = None
    duration: int | None = None
    http_headers: dict | None = None


class GuildState:
    def __init__(self):
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.text_channel: discord.abc.Messageable | None = None


# ---------- cog ----------

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: dict[int, GuildState] = {}
        self.sp = make_spotify()
        print(f"[müzik] {COOKIES_INFO} | Spotify: {'açık' if self.sp else 'kapalı'}")

    def state(self, guild_id: int) -> GuildState:
        return self.states.setdefault(guild_id, GuildState())

    async def notify(self, state: GuildState, content: str | None = None, embed: discord.Embed | None = None):
        if state.text_channel:
            try:
                await state.text_channel.send(content=content, embed=embed)
            except discord.HTTPException:
                pass

    async def resolve(self, query: str, requester) -> list[Track]:
        m = SPOTIFY_RE.search(query)
        if m:
            if not self.sp:
                raise RuntimeError("Spotify desteği kapalı (.env içinde Spotify anahtarları yok).")
            names = await asyncio.get_running_loop().run_in_executor(None, spotify_queries, self.sp, *m.groups())
            if not names:
                raise RuntimeError("Spotify bağlantısında şarkı bulunamadı.")
            return [Track(title=n, query=f"ytsearch1:{n}", requester=requester) for n in names]

        info = await extract(query)
        return [
            Track(
                title=info.get("title", "Bilinmeyen şarkı"),
                query=info.get("webpage_url") or query,
                requester=requester,
                stream_url=info.get("url"),
                webpage_url=info.get("webpage_url"),
                duration=info.get("duration"),
                http_headers=info.get("http_headers"),
            )
        ]

    async def play_next(self, guild: discord.Guild):
        state = self.state(guild.id)
        vc = guild.voice_client

        while vc and state.queue:
            track = state.queue.popleft()
            state.current = track
            try:
                if not track.stream_url:
                    info = await extract(track.query)
                    track.stream_url = info["url"]
                    track.title = info.get("title", track.title)
                    track.webpage_url = info.get("webpage_url")
                    track.duration = info.get("duration")
                    track.http_headers = info.get("http_headers")
                m = re.search(r"[?&]c=([A-Z_0-9]+)", track.stream_url or "")
                print(f"[müzik] istemci: {m.group(1) if m else '?'} | header: {'var' if track.http_headers else 'yok'}")
                if YT_MODE == "pipe":
                    source = await open_pipe_source(track.webpage_url or track.query)
                else:
                    source = discord.FFmpegPCMAudio(track.stream_url, **ffmpeg_opts(track.http_headers))
            except Exception as e:  # noqa: BLE001
                if is_bot_check(e):
                    # Kalan şarkıları denemek işe yaramaz ve engeli sertleştirir: tek mesajla bırak.
                    skipped = len(state.queue)
                    state.queue.clear()
                    state.current = None
                    await self.notify(state, f"{bot_check_message()}\nKuyruk temizlendi ({skipped + 1} şarkı atlandı).")
                    return
                await self.notify(state, f"⚠️ **{track.title}** çalınamadı: {str(e)[:150]}")
                continue

            vc.play(source, after=lambda err, g=guild: self._after(g, err))
            await self.notify(state, embed=self.now_playing_embed(track))
            return

        state.current = None

    def _after(self, guild: discord.Guild, error: Exception | None):
        # Bu fonksiyon ses thread'inde çalışır, bu yüzden event loop'a devrediyoruz.
        if error:
            print(f"Oynatma hatası: {error}")
        asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)

    @staticmethod
    def now_playing_embed(track: Track) -> discord.Embed:
        e = discord.Embed(
            title="🎶 Şimdi çalıyor",
            description=f"[{track.title}]({track.webpage_url})" if track.webpage_url else track.title,
            color=discord.Color.blurple(),
        )
        e.add_field(name="Süre", value=fmt_duration(track.duration))
        e.add_field(name="İsteyen", value=track.requester.mention)
        return e

    async def _get_vc(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        vc = interaction.guild.voice_client
        if vc is None:
            await interaction.response.send_message("❌ Bot şu an bir ses kanalında değil.", ephemeral=True)
            return None
        if not interaction.user.voice or interaction.user.voice.channel != vc.channel:
            await interaction.response.send_message("❌ Bu komut için botla aynı ses kanalında olmalısın.", ephemeral=True)
            return None
        return vc

    # ---------- komutlar ----------

    async def enqueue(self, interaction: discord.Interaction, tracks: list[Track], kaynak: str | None = None):
        """Şarkıları kuyruğa ekler, gerekirse ses kanalına bağlanır ve çalmaya başlar.
        Not: interaction daha önce defer() edilmiş olmalı ve kullanıcı bir ses kanalında olmalı."""
        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        if vc is None:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        state = self.state(interaction.guild.id)
        state.text_channel = interaction.channel

        room = MAX_QUEUE - len(state.queue)
        if room <= 0:
            return await interaction.followup.send("❌ Kuyruk dolu.")
        added = tracks[:room]
        state.queue.extend(added)

        if len(added) == 1:
            msg = f"✅ Kuyruğa eklendi: **{added[0].title}**"
        else:
            msg = f"✅ **{len(added)}** şarkı kuyruğa eklendi." + (f" ({kaynak})" if kaynak else "")
        if len(added) < len(tracks):
            msg += f"\n⚠️ Kuyruk dolduğu için {len(tracks) - len(added)} şarkı eklenemedi."
        await interaction.followup.send(msg)

        if state.current is None and not (vc.is_playing() or vc.is_paused()):
            await self.play_next(interaction.guild)

    @app_commands.command(name="cal", description="Şarkı çalar (isim, YouTube veya Spotify linki)")
    @app_commands.describe(sorgu="Şarkı adı, YouTube linki ya da Spotify linki")
    @app_commands.guild_only()
    async def cal(self, interaction: discord.Interaction, sorgu: str):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ Önce bir ses kanalına girmelisin.", ephemeral=True)

        await interaction.response.defer()
        try:
            tracks = await self.resolve(sorgu, interaction.user)
        except Exception as e:  # noqa: BLE001
            if is_bot_check(e):
                return await interaction.followup.send(bot_check_message())
            return await interaction.followup.send(f"❌ Şarkı bulunamadı: {str(e)[:200]}")

        await self.enqueue(interaction, tracks)

    @app_commands.command(name="atla", description="Çalan şarkıyı atlar")
    @app_commands.guild_only()
    async def atla(self, interaction: discord.Interaction):
        vc = await self._get_vc(interaction)
        if not vc:
            return
        if not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.send_message("❌ Şu an çalan şarkı yok.", ephemeral=True)
        vc.stop()  # after callback sıradaki şarkıyı başlatır
        await interaction.response.send_message("⏭️ Şarkı atlandı.")

    @app_commands.command(name="dur", description="Müziği durdurur, kuyruğu temizler ve kanaldan ayrılır")
    @app_commands.guild_only()
    async def dur(self, interaction: discord.Interaction):
        vc = await self._get_vc(interaction)
        if not vc:
            return
        self.state(interaction.guild.id).queue.clear()
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("⏹️ Müzik durduruldu, kuyruk temizlendi.")

    @app_commands.command(name="duraklat", description="Müziği duraklatır")
    @app_commands.guild_only()
    async def duraklat(self, interaction: discord.Interaction):
        vc = await self._get_vc(interaction)
        if not vc:
            return
        if not vc.is_playing():
            return await interaction.response.send_message("❌ Şu an çalan şarkı yok.", ephemeral=True)
        vc.pause()
        await interaction.response.send_message("⏸️ Duraklatıldı.")

    @app_commands.command(name="devam", description="Duraklatılan müziği devam ettirir")
    @app_commands.guild_only()
    async def devam(self, interaction: discord.Interaction):
        vc = await self._get_vc(interaction)
        if not vc:
            return
        if not vc.is_paused():
            return await interaction.response.send_message("❌ Müzik zaten duraklatılmış değil.", ephemeral=True)
        vc.resume()
        await interaction.response.send_message("▶️ Devam ediyor.")

    @app_commands.command(name="kuyruk", description="Şarkı kuyruğunu gösterir")
    @app_commands.guild_only()
    async def kuyruk(self, interaction: discord.Interaction):
        state = self.state(interaction.guild.id)
        if not state.current and not state.queue:
            return await interaction.response.send_message("📭 Kuyruk boş.", ephemeral=True)

        lines = []
        if state.current:
            lines.append(f"**Şimdi:** {state.current.title}")
        for i, t in enumerate(list(state.queue)[:10], start=1):
            lines.append(f"`{i}.` {t.title}")
        if len(state.queue) > 10:
            lines.append(f"… ve {len(state.queue) - 10} şarkı daha")

        await interaction.response.send_message(
            embed=discord.Embed(title="🎵 Kuyruk", description="\n".join(lines), color=discord.Color.blurple())
        )

    @app_commands.command(name="calan", description="Şu an çalan şarkıyı gösterir")
    @app_commands.guild_only()
    async def calan(self, interaction: discord.Interaction):
        state = self.state(interaction.guild.id)
        if not state.current:
            return await interaction.response.send_message("❌ Şu an çalan şarkı yok.", ephemeral=True)
        await interaction.response.send_message(embed=self.now_playing_embed(state.current))

    # ---------- ses kanalında yalnız kalınca ayrıl ----------

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        vc = member.guild.voice_client
        if not vc or not vc.channel:
            return
        if any(not m.bot for m in vc.channel.members):
            return

        await asyncio.sleep(IDLE_LEAVE_SECONDS)

        vc = member.guild.voice_client
        if vc and vc.channel and not any(not m.bot for m in vc.channel.members):
            self.state(member.guild.id).queue.clear()
            await vc.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
