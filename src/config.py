"""Centralised configuration — reads from environment variables."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Local storage ──────────────────────────────────────────────
LOCAL_HTML_OUTPUT_DIR = os.getenv("LOCAL_HTML_OUTPUT_DIR", "")

# ── Cloudflare R2 ─────────────────────────────────────────────
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "joy-audit")
R2_PUBLIC_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN", "")

# Auto-detect: use R2 when all three credential vars are set
USE_R2 = bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)
