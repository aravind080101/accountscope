"""Runtime configuration, read from environment variables (or a .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

# Which LLM to use: "anthropic" or "openai". Left empty, it picks whichever key is set
# (Anthropic first if both are).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")          # used with Anthropic
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")          # used with OpenAI
DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "accountscope.db"))

BUILTWITH_API_KEY = os.getenv("BUILTWITH_API_KEY", "")   # optional: website tech stack
BUILTWITH_URL = os.getenv("BUILTWITH_URL", "https://api.builtwith.com/v21/api.json")

# Caching: re-research within this window re-uses stored sources instead of searching again.
SOURCE_CACHE_HOURS = float(os.getenv("SOURCE_CACHE_HOURS", "24"))
PEOPLE_CACHE_DAYS = float(os.getenv("PEOPLE_CACHE_DAYS", "30"))

# Watchlists: watched accounts are re-researched this often while the app is running.
WATCH_INTERVAL_DAYS = float(os.getenv("WATCH_INTERVAL_DAYS", "7"))
WATCH_SCHEDULER = os.getenv("WATCH_SCHEDULER", "on").lower() not in ("off", "0", "false", "no")

# Login. Off only for single-user use on your own machine (and tests); always on in the cloud.
RUNNING_IN_CLOUD = os.getenv("RUNNING_IN_CLOUD", "").lower() in ("1", "true", "yes")
REQUIRE_LOGIN = RUNNING_IN_CLOUD or os.getenv("REQUIRE_LOGIN", "on").lower() not in ("off", "0", "false", "no")
SESSION_DAYS = float(os.getenv("SESSION_DAYS", "14"))
# The platform owner, created on first start if no users exist (set these as secrets in the cloud).
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
# Lets the very first visitor create the owner account in the browser. Off in the cloud.
ALLOW_SETUP = not RUNNING_IN_CLOUD and os.getenv("ALLOW_SETUP", "on").lower() not in ("off", "0", "false", "no")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")   # lets the Cloudflare scheduler trigger watch runs
# Free hosting (Render): the app's own address is public, so only answer requests that came through the
# Cloudflare Worker, which adds x-proxy-token. /health stays open for Render's health check.
PROXY_ONLY = os.getenv("PROXY_ONLY", "").lower() in ("1", "true", "yes", "on")

# Your own services. Used to score how well each initiative fits what you sell.
OFFERINGS = [
    o.strip().lower()
    for o in os.getenv(
        "OFFERINGS",
        "test automation, quality engineering, performance testing, security testing, "
        "AI testing, mobile app testing, API testing, DevOps",
    ).split(",")
    if o.strip()
]

# How far back to look for signals, and how many search results per query.
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "365"))
RESULTS_PER_QUERY = int(os.getenv("RESULTS_PER_QUERY", "6"))
MAX_CONTACTS_PER_INITIATIVE = int(os.getenv("MAX_CONTACTS_PER_INITIATIVE", "5"))


def llm_provider() -> str | None:
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return "openai"
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return "anthropic"
    if ANTHROPIC_API_KEY:
        return "anthropic"
    if OPENAI_API_KEY:
        return "openai"
    return None


def configured() -> bool:
    """Research needs an LLM key (Anthropic or OpenAI) and a search key. Apollo is optional."""
    return bool(llm_provider() and TAVILY_API_KEY)
