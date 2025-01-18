import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

# Model settings
MODEL_TYPE = os.getenv("SWIFEY_MODEL_TYPE", "api")  

# API model settings
API_URL = os.getenv("HYPERBOLIC_API_URL")
API_MODEL = os.getenv("SWIFEY_API_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))

# System settings
FLUSH_INTERVAL = int(os.getenv("SWIFEY_FLUSH_INTERVAL", "300"))
BUFFER_SIZE = int(os.getenv("SWIFEY_BUFFER_SIZE", "1000"))

# Logging settings
LOG_LEVEL = os.getenv("SWIFEY_LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv(
    "SWIFEY_LOG_FORMAT",
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Supabase settings
SUPABASE_URL = os.getenv("SWIFEY_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SWIFEY_SUPABASE_KEY")

# Telegram settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "2185680092/10101"  # Hardcoded specific chat ID

# Validate required settings
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and key must be provided in environment variables")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Telegram bot token must be provided in environment variables")

# LLM configuration
LLM_CONFIG = {
    "type": MODEL_TYPE,
    "model": API_MODEL,
    "api_url": API_URL,
    "api_key": os.getenv("HYPERBOLIC_API_KEY")
}

JWT_SECRET = os.getenv("JWT_SECRET")

# Turnkey API Settings
TURNKEY_API_PUBLIC_KEY = os.getenv("TURNKEY_API_PUBLIC_KEY")
if not TURNKEY_API_PUBLIC_KEY:
    raise ValueError("TURNKEY_API_PUBLIC_KEY environment variable is not set")

TURNKEY_API_PRIVATE_KEY = os.getenv("TURNKEY_API_PRIVATE_KEY")
if not TURNKEY_API_PRIVATE_KEY:
    raise ValueError("TURNKEY_API_PRIVATE_KEY environment variable is not set")

TURNKEY_ORGANIZATION_ID = os.getenv("TURNKEY_ORGANIZATION_ID")
if not TURNKEY_ORGANIZATION_ID:
    raise ValueError("TURNKEY_ORGANIZATION_ID environment variable is not set")

# Firebase
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
if not FIREBASE_PROJECT_ID:
    raise ValueError("FIREBASE_PROJECT_ID environment variable is not set")
