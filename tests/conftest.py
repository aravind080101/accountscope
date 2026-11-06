"""Every test session gets its own empty database, before the app is imported."""
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY", "APOLLO_API_KEY", "BUILTWITH_API_KEY"):
    os.environ[k] = ""
os.environ["WATCH_SCHEDULER"] = "off"
os.environ["REQUIRE_LOGIN"] = "off"
