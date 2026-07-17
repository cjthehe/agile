import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

url = os.getenv("SUPABASE_URL", "").strip()
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

if not url or not key:
    raise ValueError(
        "Missing Supabase environment variables. Add them to the project root .env file."
    )

try:
    supabase: Client = create_client(url, key)
except Exception as exc:
    raise RuntimeError(f"Could not initialize Supabase client: {exc}") from exc
