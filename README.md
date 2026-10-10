# Discord Botu

Moderasyon, log, anket, müzik ve bilgi komutları olan discord.py botu.

## Komutlar

| Kategori | Komutlar |
|---|---|
| Moderasyon | `/ban` `/unban` `/kick` `/mute` `/unmute` `/temizle` |
| Uyarı sistemi | `/uyari` `/uyarilar` `/uyarisil` (her 3 uyarıda otomatik 60 dk susturma) |
| Log | `/logkanal` `/logkapat` (silinen/düzenlenen mesaj, giriş, çıkış, moderasyon işlemleri) |
| Anket | `/anket` (Discord'un yerleşik anketi) `/oylama` (👍/👎) |
| Müzik | `/cal` `/atla` `/dur` `/duraklat` `/devam` `/kuyruk` `/calan` |
| Otomatik moderasyon | `/otomatik ayarla` `/otomatik bypass` `/otomatik durum` `/otomatik yasakikelime ekle/sil/liste` (küfür, spam, davet linki, büyük harf, aşırı etiketleme filtreleri) |
| Çekiliş | `/cekilis baslat` `/cekilis bitir` `/cekilis listele` |
| SSS botu | `/sss ekle` `/sss sil` `/sss liste` (kelime geçince otomatik cevap) |
| Hoş geldin/veda | `/hosgeldin ayarla/kapat/test` `/veda ayarla/kapat` (kişiselleştirilebilir mesaj) |
| Tepki ile rol | `/tepkirol ekle/sil/liste` |
| Sunucu istatistiği | `/istatistik ekle/kapat` (canlı üye/bot/toplam sayacı gösteren ses kanalı) |
| Modmail (DM destek) | `/modmail ayarla` `/modmail kapat` (botun DM'ine yazan kişiye özel kanal açar, yetkili cevabı otomatik DM'e gider) |
| Ticket | `/ticket ayarla` `/ticket panel` (butonla destek kanalı açma/kapatma, transkript log'a düşer) |
| Bilgi | `/sunucubilgi` `/kullanicibilgi` |
| Otomatik rol | `/otorol ayarla` `/otorol kapat` `/otorol goster` (yeni gelenlere rol verir) |
| Toplu DM | `/rolmesaj` (sadece yöneticiler; role sahip üyelere özel mesaj) |

## Kurulum

1. **Bot oluştur:** https://discord.com/developers/applications → New Application → Bot sekmesi → Token'ı kopyala.
2. **Intent'leri aç** (Bot sekmesi → Privileged Gateway Intents): `Server Members Intent` ve `Message Content Intent`.
3. **Botu sunucuna ekle:** OAuth2 → URL Generator → scope: `bot` + `applications.commands`.
   Yetkiler: View Channels, Send Messages, Embed Links, Read Message History, Manage Messages,
   Kick Members, Ban Members, Moderate Members, Manage Roles, Manage Channels, Connect, Speak, Add Reactions, Send Polls.
4. **Gereksinimler:** Python 3.10+ ve **FFmpeg** (müzik için)
   - Windows: `winget install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`
5. **Kütüphaneleri kur:**
   ```
   pip install -r requirements.txt
   ```
6. `.env.example` dosyasını `.env` olarak kopyala, `DISCORD_TOKEN` alanını doldur.
   Geliştirirken `GUILD_ID` alanına test sunucunun ID'sini yazarsan komutlar anında görünür.
7. Çalıştır:
   ```
   python bot.py
   ```

## Railway'de 7/24 çalıştırma

1. Bu klasördeki dosyaları (`.env` hariç) bir **özel (private) GitHub deposuna** yükle.
2. https://railway.com → **New Project → Deploy from GitHub repo** → depoyu seç. `Dockerfile` otomatik algılanır.
3. Servisin **Variables** sekmesine `DISCORD_TOKEN` ekle (isteğe bağlı: `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`).
4. Servisin üzerinde sağ tıkla → **Volume** ekle, mount path olarak `/data` yaz (uyarılar ve log ayarı silinmesin diye).
5. Deploy bitince **Deployments → View Logs** içinde `giriş yapıldı` yazısını görürsün.

## Önemli notlar

- **Bot rolü:** Moderasyon komutlarının çalışması için sunucu ayarlarında botun rolünü, yönetmesi gereken rollerin **üstüne** taşı.
- **Log sistemi:** `/logkanal #kanal` ile açılır. Bot açılmadan önce gönderilmiş mesajların düzenleme/silme logları düşmeyebilir (cache'de olmadıkları için).
- **Spotify:** Spotify'dan ses akıtılamaz. Bot, Spotify linkindeki şarkı adlarını okuyup YouTube'da arar.
  Bunun için https://developer.spotify.com/dashboard adresinden bir uygulama oluşturup
  `SPOTIPY_CLIENT_ID` ve `SPOTIPY_CLIENT_SECRET` değerlerini `.env`'e yazmalısın (opsiyonel; boşsa sadece YouTube çalışır).
- **YouTube:** YouTube sık sık değişir. Müzik bir gün çalışmazsa önce `pip install -U yt-dlp` dene.
  yt-dlp'nin güncel sürümleri bazı durumlarda bir JavaScript çalışma zamanı (ör. Deno) da isteyebilir.
  Bulut sunucularının IP'leri de zaman zaman YouTube tarafından engellenir.
- **Veriler:** Uyarılar ve log ayarları `bot.db` (SQLite) dosyasında tutulur.

## Dosya yapısı

```
bot.py            Başlangıç noktası
db.py             SQLite işlemleri (uyarılar, log ayarı)
utils.py          Ortak yardımcılar (log gönderme, yetki hiyerarşisi kontrolü)
cogs/
  moderation.py   ban, kick, mute, uyarı, temizle
  logs.py         log sistemi
  polls.py        anket / oylama
  music.py        müzik
  info.py         sunucu / kullanıcı bilgisi
```
