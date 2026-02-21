"""
macro_context.py — Macro Intuition System
==========================================
Membaca semua file dari folder macro_knowledge/ dan membangun
ringkasan konteks makro yang akan digunakan Gemini saat menganalisis sinyal.

CARA UPDATE MACRO (Tanpa Push ke GitHub):
==========================================
Ada 2 cara update file macro knowledge:

CARA 1 — Upload via Railway Volume (DIREKOMENDASIKAN):
  1. Di Railway Dashboard → Project → Volumes
  2. Upload file .txt baru ke folder /data/macro_knowledge/
  3. Bot otomatis baca file baru dalam 1 jam (cache expires)
  4. TIDAK PERLU push ke GitHub sama sekali!

CARA 2 — Via GitHub Push (seperti biasa):
  1. Edit/tambah file di futures-agent/macro_knowledge/
  2. git add + git commit + git push
  3. Railway redeploy otomatis

Catatan: Cara 1 lebih direkomendasikan karena TIDAK menyebabkan redeploy
(dan tidak mereset balance/history).
"""

import os
import glob
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("macro_context")

# ── Dual-path: Railway Volume (persistent) → fallback ke local folder ──────
# Railway Volume path (set via RAILWAY_VOLUME_MOUNT_PATH env var)
_VOLUME_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
_LOCAL_DIR  = os.path.join(os.path.dirname(__file__), "macro_knowledge")

# Priority: Volume folder > Local folder
if _VOLUME_DIR:
    MACRO_KNOWLEDGE_DIR = os.path.join(_VOLUME_DIR, "macro_knowledge")
    os.makedirs(MACRO_KNOWLEDGE_DIR, exist_ok=True)
    logger.info(f"📂 Macro knowledge: Railway Volume → {MACRO_KNOWLEDGE_DIR}")
else:
    MACRO_KNOWLEDGE_DIR = _LOCAL_DIR
    logger.info(f"📂 Macro knowledge: Local folder → {MACRO_KNOWLEDGE_DIR}")

# ── Always also check local folder (merge both sources) ───────────────────
MACRO_DIRS = list(dict.fromkeys(filter(os.path.isdir, [
    MACRO_KNOWLEDGE_DIR,
    _LOCAL_DIR,
])))

# Cache: agar tidak baca ulang file setiap kali analisis
_macro_cache: Optional[str] = None
_cache_time: float = 0
CACHE_TTL = 3600  # Refresh cache setiap 1 jam


def load_macro_context() -> str:
    """
    Baca semua file dari folder macro_knowledge/ (Volume + local) dan gabungkan
    jadi satu string konteks yang siap dikirim ke Gemini.

    Membaca dari DUA sumber:
    1. Railway Volume /data/macro_knowledge/ (jika dikonfigurasi)
    2. Local macro_knowledge/ di dalam project (di-push via GitHub)

    Returns:
        str: Gabungan semua konteks makro, atau string kosong jika tidak ada file.
    """
    global _macro_cache, _cache_time

    now = datetime.now().timestamp()

    # Return cache jika belum expired
    if _macro_cache is not None and (now - _cache_time) < CACHE_TTL:
        return _macro_cache

    # Kumpulkan semua file dari semua sumber (Volume + local)
    all_files = {}  # filename → filepath (deduplicate by name, Volume wins)
    for macro_dir in MACRO_DIRS:
        if not os.path.isdir(macro_dir):
            continue
        for pattern in ["*.txt", "*.md"]:
            for filepath in glob.glob(os.path.join(macro_dir, pattern)):
                fname = os.path.basename(filepath)
                if "README" in fname.upper():
                    continue
                # Jika file sama ada di dua tempat, pakai yang lebih baru
                if fname not in all_files:
                    all_files[fname] = filepath
                else:
                    if os.path.getmtime(filepath) > os.path.getmtime(all_files[fname]):
                        all_files[fname] = filepath

    if not all_files:
        logger.info("Tidak ada file macro knowledge ditemukan.")
        _macro_cache = ""
        _cache_time = now
        return ""

    # Sort by modification time (terbaru duluan)
    sorted_files = sorted(all_files.values(), key=os.path.getmtime, reverse=True)

    context_parts = []
    for filepath in sorted_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                fname = os.path.basename(filepath)
                source = "Volume" if _VOLUME_DIR and _VOLUME_DIR in filepath else "Local"
                context_parts.append(f"[FILE: {fname} | Source: {source}]\n{content}")
                logger.debug(f"Loaded macro: {fname} ({len(content)} chars) [{source}]")
        except Exception as e:
            logger.error(f"Error membaca {filepath}: {e}")

    if not context_parts:
        _macro_cache = ""
        _cache_time = now
        return ""

    combined = "\n\n".join(context_parts)

    # Trim ke max 8000 karakter agar tidak overflow token Gemini
    MAX_CHARS = 8000
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS] + "\n... [MACRO CONTEXT TRUNCATED]"

    _macro_cache = combined
    _cache_time = now

    logger.info(
        f"Macro context loaded: {len(sorted_files)} file(s) from "
        f"{len(MACRO_DIRS)} source(s), {len(combined)} chars total"
    )
    return combined


def get_macro_system_prompt() -> str:
    """
    Buat system prompt tambahan berisi instruksi Intuisi Makro untuk Gemini.
    Dipanggil setiap kali Gemini akan menganalisis sinyal.

    Returns:
        str: System prompt makro yang sudah diformat, atau string kosong jika tidak ada data.
    """
    macro_ctx = load_macro_context()

    if not macro_ctx:
        return ""

    prompt = f"""
=== MACRO MARKET CONTEXT (INTUISI MAKRO) ===
Berikut adalah konteks makro terkini yang HARUS kamu pertimbangkan dalam analisis.
Gunakan ini sebagai "filter kebijaksanaan" — jangan hanya bergantung pada sinyal teknikal.

{macro_ctx}

=== INSTRUKSI PENGGUNAAN KONTEKS MAKRO ===
1. JANGAN langsung entry hanya berdasarkan sinyal Telegram atau chart.
2. Cocokkan sinyal dengan kondisi makro di atas:
   - Jika makro BEARISH dan sinyal LONG altcoin → SKIP atau kurangi confidence
   - Jika ada catalyst bullish (Clarity Act, QE, rate cuts) + sinyal teknikal → tingkatkan confidence
   - Jika ada berita perang/konflik → BEARISH untuk semua kecuali emas
3. Leverage HARUS disesuaikan:
   - Bear market: MAX leverage 5x-10x
   - Kondisi ekstrem/berita negatif: MAX leverage 3x atau SKIP
4. Window trading terbatas — ikuti proyeksi siklus yang tertera di konteks makro.
=== END MACRO CONTEXT ===
""".strip()

    return prompt


def invalidate_cache():
    """Force refresh cache pada siklus berikutnya."""
    global _macro_cache
    _macro_cache = None
    logger.info("Macro context cache invalidated.")


def get_macro_summary() -> dict:
    """Buat ringkasan singkat status makro (untuk logging/monitoring)."""
    all_files = {}
    for macro_dir in MACRO_DIRS:
        if not os.path.isdir(macro_dir):
            continue
        for pattern in ["*.txt", "*.md"]:
            for filepath in glob.glob(os.path.join(macro_dir, pattern)):
                fname = os.path.basename(filepath)
                if "README" not in fname.upper():
                    all_files[fname] = filepath

    if not all_files:
        return {"status": "NO_DATA", "files": 0, "chars": 0, "sources": MACRO_DIRS}

    ctx = load_macro_context()
    latest = max(all_files.values(), key=os.path.getmtime) if all_files else "none"

    return {
        "status": "LOADED",
        "files": len(all_files),
        "chars": len(ctx),
        "latest_file": os.path.basename(latest),
        "sources": MACRO_DIRS,
        "volume_active": bool(_VOLUME_DIR),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = get_macro_summary()
    print(f"\n{'='*60}")
    print(f"MACRO CONTEXT STATUS:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"{'='*60}\n")
    ctx = load_macro_context()
    if ctx:
        print(f"PREVIEW (500 char pertama):\n{ctx[:500]}\n...")
    else:
        print("Tidak ada macro context.")
