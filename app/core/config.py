import os
from dotenv import load_dotenv

# Load environmental variables from root .env
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.abspath(os.path.join(current_dir, "..", "..", ".env"))
load_dotenv(env_path)

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
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://localhost:8000").strip()

