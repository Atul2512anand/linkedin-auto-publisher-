import argparse
import os
import sys
from datetime import datetime

import linkedin_client
from generate import generate_post
from common import DRAFTS_DIR, LOGS_DIR, POSTED_LOG, ensure_dirs, load_env


def _force_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def maybe_build_visual(text, tag=None):
    load_env()
    mode = os.environ.get("VISUAL_MODE", "off").strip().lower()
    if mode not in ("image", "carousel"):
        return None
    try:
        import visuals
        if mode == "carousel":
            pdf_path, _ = visuals.build_carousel(text, tag=tag)
            return pdf_path
        return visuals.build_hero(text)
    except Exception as exc:
        print(f"WARNING: visual generation failed ({exc}). Posting text only.")
        return None


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
    topic, text, source_link = generate_post(args.topic)
    draft_path = save_draft(topic, text)
    print(f"Topic: {topic}")
    print(f"Draft saved: {draft_path}")

    media_path = maybe_build_visual(text, tag=os.path.splitext(os.path.basename(draft_path))[0])
    if media_path:
        print(f"Visual ready: {media_path}")
        doc_title = topic.split("] ", 1)[-1][:90] if "]" in topic else topic[:90]
        print(f"Carousel title: {doc_title}")

    if args.dry_run:
        print("--- DRY RUN ---")
        print(text)
        return

    ok, message, post_urn = linkedin_client.create_post(
        text, media_path=media_path, media_title=doc_title if media_path else None
    )
    log_result("POSTED" if ok else "FAILED", topic)
    if ok:
        print(f"SUCCESS: {message}")
        if source_link and post_urn:
            c_ok, c_msg = linkedin_client.create_comment(
                post_urn, f"🔗 Source article: {source_link}"
            )
            print("Source link in first comment:", c_msg)
    else:
        print(f"FAILED: {message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
