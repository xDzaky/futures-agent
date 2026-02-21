# 📋 Cara Update Macro Knowledge (Tanpa Reset Balance)

## ❓ Mengapa Balance Bisa Reset?

Setiap kali kamu push ke GitHub → Railway redeploy → Container baru dibuat.
File yang tidak disimpan di **Railway Volume** akan **hilang**.

**Yang Aman (sudah dikonfigurasi):**
- ✅ Database SQLite (`futures_trades.db`) → disimpan di Railway Volume
- ✅ AI Accuracy history → disimpan di Railway Volume
- ✅ Balance, posisi, trade history → semua di Railway Volume

---

## 🔧 Setup Railway Volume (WAJIB — Lakukan Sekali Saja)

### Langkah 1: Buat Volume di Railway

1. Buka [Railway Dashboard](https://railway.app) → Project `futures-agent`
2. Klik **"New"** → **"Volume"**
3. **Mount Path:** `/data`
4. Klik **"Deploy"**

### Langkah 2: Set Environment Variable

Di Railway → Project → Variables, tambahkan:
```
RAILWAY_VOLUME_MOUNT_PATH=/data
```

Setelah ini **push ke GitHub TIDAK RESET balance/history** ✅

---

## 📝 Cara Update Macro Knowledge (2 Pilihan)

### ✅ PILIHAN 1: Via Railway Volume (Direkomendasikan)
**Tidak perlu push ke GitHub sama sekali!**

1. Buat file `.txt` baru (misal: `update_maret_2026.txt`)
2. Isi dengan ringkasan analisis makro terbaru
3. Upload ke Railway Volume:
   - Railway Dashboard → Project → Volume → **File Manager**
   - Browse ke `/data/macro_knowledge/`
   - Upload file `.txt` kamu
4. Bot otomatis baca file baru dalam **maksimal 1 jam** (cache TTL)
5. Balance/history **TIDAK RESET** ✅

### 🔄 PILIHAN 2: Via GitHub Push (Menyebabkan Redeploy)
Balance tetap aman selama Volume sudah dikonfigurasi.

1. Tambah file di folder ini
2. `git add macro_knowledge/namafile.txt`
3. `git commit -m "update: macro knowledge maret 2026"`
4. `git push origin main`

---

## 📅 Jadwal Update (Rekomendasi)

| Frekuensi | Kapan |
|-----------|-------|
| **Mingguan** | Setiap ada live stream analisis baru |
| **Event besar** | FOMC meeting, CPI data, breaking news |
| **Catalyst** | Clarity Act update, konflik geopolitik baru |

---

## 📁 Format File

Nama file bebas, ekstensi `.txt` atau `.md`:
- `update_maret_2026.txt` ✅
- `fomc_maret_2026.md` ✅

**Bot otomatis baca semua file** — file terbaru diprioritaskan.
