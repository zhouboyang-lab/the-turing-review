import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'turing_review.db'}"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# OpenRouter 中转配置（用于从不支持的地区访问 Anthropic/OpenAI API）
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# 审稿人模型配置
LOGICIAN_MODEL = "google/gemini-2.0-flash-001"       # The Logician (via OpenRouter)
INNOVATOR_MODEL = "meta-llama/llama-3.3-70b-instruct" # The Innovator (via OpenRouter)
TECHNICIAN_MODEL = "deepseek-chat"                     # The Technician (direct)
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 主编模型（通过 OpenRouter 调用）
EDITOR_MODEL = "google/gemini-2.0-flash-001"

# 邮件配置（用于通知作者审稿结果）
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@turing-review.org")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# 社区审稿人配置
MAX_GUEST_REVIEWERS_PER_PAPER = int(os.getenv("MAX_GUEST_REVIEWERS_PER_PAPER", "2"))
MAX_PROMPT_MODE_PER_PAPER = int(os.getenv("MAX_PROMPT_MODE_PER_PAPER", "1"))
GUEST_API_TIMEOUT = int(os.getenv("GUEST_API_TIMEOUT", "120"))
GUEST_API_KEY_SECRET = os.getenv("GUEST_API_KEY_SECRET", "change-me-in-production")
PROMPT_MODE_MONTHLY_QUOTA = int(os.getenv("PROMPT_MODE_MONTHLY_QUOTA", "10"))

# 投稿频率限制
DAILY_SUBMIT_LIMIT = int(os.getenv("DAILY_SUBMIT_LIMIT", "2"))
MONTHLY_SUBMIT_LIMIT = int(os.getenv("MONTHLY_SUBMIT_LIMIT", "5"))
REQUIRE_EMAIL = os.getenv("REQUIRE_EMAIL", "true").lower() == "true"
