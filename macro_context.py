"""
macro_context.py — Macro Intuition System
==========================================
Membaca semua file dari folder macro_knowledge/ dan membangun
ringkasan konteks makro yang akan digunakan Gemini saat menganalisis sinyal.

Cara pakai:
- Tambah file .txt atau .md baru ke folder macro_knowledge/
- Bot otomatis baca semua file saat startup dan saat analisis
- Tidak perlu ubah kode apapun
"""

import os
import glob
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("macro_context")

# Folder tempat menyimpan file macro knowledge
MACRO_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "macro_knowledge")

# Cache: agar tidak baca ulang file setiap kali analisis
_macro_cache: Optional[str] = None
_cache_time: float = 0
CACHE_TTL = 3600  # Refresh cache setiap 1 jam


def load_macro_context() -> str:
    """
    Baca semua file dari folder macro_knowledge/ dan gabungkan jadi
    satu string konteks yang siap dikirim ke Gemini.
    
    Returns:
        str: Gabungan semua konteks makro, atau string kosong jika tidak ada file.
    """
    global _macro_cache, _cache_time

    now = datetime.now().timestamp()

    # Return cache jika belum expired
    if _macro_cache is not None and (now - _cache_time) < CACHE_TTL:
        return _macro_cache

    if not os.path.isdir(MACRO_KNOWLEDGE_DIR):
        logger.warning(f"Macro knowledge dir tidak ditemukan: {MACRO_KNOWLEDGE_DIR}")
        return ""

    # Baca semua .txt dan .md (kecuali README)
    patterns = ["*.txt", "*.md"]
    files = []
    for pattern in patterns:
        matches = glob.glob(os.path.join(MACRO_KNOWLEDGE_DIR, pattern))
        for f in matches:
            if "README" not in os.path.basename(f).upper():
                files.append(f)

    if not files:
        logger.info("Tidak ada file macro knowledge ditemukan.")
        return ""

    # Sort by modification time (terbaru duluan)
    files.sort(key=os.path.getmtime, reverse=True)

    context_parts = []
    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                fname = os.path.basename(filepath)
                context_parts.append(f"[FILE: {fname}]\n{content}")
                logger.debug(f"Loaded macro file: {fname} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Error membaca {filepath}: {e}")

    if not context_parts:
        return ""

    combined = "\n\n".join(context_parts)

    # Trim ke max 8000 karakter (dari file terbaru) agar tidak overflow token Gemini
    MAX_CHARS = 8000
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS] + "\n... [MACRO CONTEXT TRUNCATED]"

    _macro_cache = combined
    _cache_time = now

    logger.info(f"Macro context loaded: {len(files)} file(s), {len(combined)} chars total")
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
    """
    Buat ringkasan singkat status makro (untuk logging/monitoring).
    """
    ctx = load_macro_context()
    if not ctx:
        return {"status": "NO_DATA", "files": 0, "chars": 0}

    files = glob.glob(os.path.join(MACRO_KNOWLEDGE_DIR, "*.txt")) + \
            glob.glob(os.path.join(MACRO_KNOWLEDGE_DIR, "*.md"))
    files = [f for f in files if "README" not in os.path.basename(f).upper()]

    return {
        "status": "LOADED",
        "files": len(files),
        "chars": len(ctx),
        "latest_file": os.path.basename(max(files, key=os.path.getmtime)) if files else "none"
    }


if __name__ == "__main__":
    # Test langsung
    logging.basicConfig(level=logging.INFO)
    summary = get_macro_summary()
    print(f"\n{'='*60}")
    print(f"MACRO CONTEXT STATUS: {summary}")
    print(f"{'='*60}\n")
    ctx = load_macro_context()
    if ctx:
        print(f"PREVIEW (500 char pertama):\n{ctx[:500]}\n...")
    else:
        print("Tidak ada macro context.")
