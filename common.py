import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_FILE = os.path.join(BASE_DIR, "tokens.json")
DRAFTS_DIR = os.path.join(BASE_DIR, "drafts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
TOPICS_FILE = os.path.join(BASE_DIR, "topics.txt")
POSTED_LOG = os.path.join(LOGS_DIR, "posted.log")


def load_env(path=None):
    if path is None:
        path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def ensure_dirs():
    for d in (DRAFTS_DIR, LOGS_DIR):
        os.makedirs(d, exist_ok=True)
