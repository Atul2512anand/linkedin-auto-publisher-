import argparse
import os
import sys
from datetime import datetime

import linkedin_client
from generate import generate_post
from common import DRAFTS_DIR, LOGS_DIR, POSTED_LOG, ensure_dirs


def _force_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def save_draft(topic, text):
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.join(DRAFTS_DIR, f"{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Topic: {topic}\n\n{text}\n")
    return path


def log_result(status, topic):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(POSTED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {status} | {topic}\n")


def main():
    _force_utf8_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="generate draft only, do not post")
    parser.add_argument("--topic", help="override topic from topics.txt")
    args = parser.parse_args()

    ensure_dirs()
    print("Generating post via opencode...")
    topic, text = generate_post(args.topic)
    draft_path = save_draft(topic, text)
    print(f"Topic: {topic}")
    print(f"Draft saved: {draft_path}")

    if args.dry_run:
        print("--- DRY RUN ---")
        print(text)
        return

    ok, message = linkedin_client.create_post(text)
    log_result("POSTED" if ok else "FAILED", topic)
    if ok:
        print(f"SUCCESS: {message}")
    else:
        print(f"FAILED: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
