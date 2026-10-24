import os
from dotenv import load_dotenv

# Load environmental variables from root .env
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.abspath(os.path.join(current_dir, "..", "..", ".env"))
load_dotenv(env_path, override=True)

RAW_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test_saas.db")
# Strip pgbouncer query param which causes psycopg2 DSN parser errors
if RAW_DATABASE_URL:
    RAW_DATABASE_URL = RAW_DATABASE_URL.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")
    
DIRECT_URL = os.getenv("DIRECT_URL", "")

# Smart Fallback to SQLite if Supabase credentials are not yet filled with a real password
if "YOUR-PASSWORD" in RAW_DATABASE_URL or not RAW_DATABASE_URL.strip():
    DATABASE_URL = "sqlite:///./test_saas.db"
    IS_SQLITE = True
else:
    DATABASE_URL = RAW_DATABASE_URL
    IS_SQLITE = False

JWT_SECRET = os.getenv("JWT_SECRET", "demo_secret_key_change_me_in_production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# CORS Origins Configuration
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]

# WhiteNet Payment Integration variables
CLIENT_ID = os.getenv("CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "").strip()
APP_ID = os.getenv("APP_ID", "").strip()
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "https://api.wytnet.com").strip()

# WytNet / WytPass Identity Provider variables
WYTPASS_CLIENT_ID = os.getenv("WYTPASS_CLIENT_ID", os.getenv("WHITEPASS_CLIENT_ID", "wn_live_c7f8ce9b13ee5a8f7a3d9222fce39fd0")).strip()
WYTPASS_CLIENT_SECRET = os.getenv("WYTPASS_CLIENT_SECRET", os.getenv("WHITEPASS_CLIENT_SECRET", "wn_secret_abe21f6bf5db981f57799e7f015fd4bd33d60fd55a7a3ee1")).strip()
WYTNET_ISSUER_URL = os.getenv("WYTNET_ISSUER_URL", "https://api.wytnet.com").strip().rstrip("/")
WYTNET_AUTH_URL = os.getenv("WYTNET_AUTH_URL", "https://wytnet.com/oauth/authorize").strip()
WYTNET_TOKEN_URL = os.getenv("WYTNET_TOKEN_URL", f"{WYTNET_ISSUER_URL}/oauth/token").strip()
WYTNET_JWKS_URL = os.getenv("WYTNET_JWKS_URL", f"{WYTNET_ISSUER_URL}/.well-known/jwks.json").strip()
WYTNET_OPENID_CONFIG_URL = os.getenv("WYTNET_OPENID_CONFIG_URL", f"{WYTNET_ISSUER_URL}/.well-known/openid-configuration").strip()
WYTNET_REDIRECT_URI = os.getenv("WYTNET_REDIRECT_URI", "http://localhost:5173/api/auth/callback/whitenet").strip()

# Backward-compatibility aliases
WHITEPASS_CLIENT_ID = WYTPASS_CLIENT_ID
WHITEPASS_CLIENT_SECRET = WYTPASS_CLIENT_SECRET
WHITEPASS_TOKEN_URL = WYTNET_TOKEN_URL

