import os
import random
import re
import shutil
import subprocess
import sys

from common import BASE_DIR, POSTED_LOG, TOPICS_FILE, load_env
import scraper

STYLE_RULES = (
    "- Write like a young, energetic, extremely curious tech enthusiast - use questions, "
    "express excitement, stay positive and forward-looking. Never sound like a dry formal expert.\n"
    "- SYNTHESIZE the information in your own voice, never repeat or plagiarize it.\n"
    "- Start with a strong trending-topic hook built to go viral on LinkedIn.\n"
    "- LENGTH: at least 280 words, aim for 320-450. This is a meaty mini-article, not a blurb. "
    "Go deep: how it works technically, why it happened, real-world impact, and what the reader "
    "should do differently.\n"
    "- Use short paragraphs and bullet points or numbered steps for easy scanning.\n"
    "- Explain any technical jargon in one simple phrase the moment you use it.\n"
    "- Explicitly NAME the companies, products and people the story is about.\n"
    "- RECRUITER MAGNET: weave in at least one moment of genuine expertise - a sharp technical "
    "insight, a security principle applied correctly, an engineering trade-off explained - the "
    "kind of depth that makes hiring managers stop scrolling. Never beg for jobs; attract by "
    "demonstrating skill.\n"
    "- INFLUENCER VOICE: confident opinions are welcome ('here's my hot take', 'unpopular "
    "opinion'), but always earned through reasoning, not rage-bait.\n"
    "- End with a call-to-action or thought-provoking question that invites discussion.\n"
    "- Finish with exactly 4 to 5 relevant, specific hashtags - mix big ones (#Cybersecurity) "
    "with niche ones recruiters and practitioners follow (#ThreatIntel, #AppSec, #PrivacyEngineering).\n"
    "- IMPORTANT: this is a pure writing task. Do NOT use any tools, do NOT read files, "
    "do NOT search the web, do NOT ask clarifying questions."
)

DEFAULT_PERSONA = (
    "You are a young, energetic, and extremely curious tech content creator building authority "
    "on LinkedIn in cybersecurity, artificial intelligence and computer science. Your audience "
    "is global tech professionals, hiring managers and founders. You are not a distant expert - "
    "you are a fellow enthusiast eager to break down the latest breakthroughs and help readers "
    "learn something useful from every event.\n\n"
)


def load_persona():
    path = os.path.join(BASE_DIR, "persona.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content + "\n\n"
    return DEFAULT_PERSONA


PERSONA = load_persona()

TOPIC_PROMPT_TEMPLATE = (
    "TASK: Write one LinkedIn post in English about EXACTLY this topic - do not pick your own "
    "topic: {topic}\n\n"
    + PERSONA
    + "Guidelines:\n"
    + STYLE_RULES
    + "\n\nOUTPUT CONTRACT: Your entire reply must be ONLY the raw post text - no preamble like "
    "'Here is a draft', no explanations, no markdown headers, no offers to revise, no questions "
    "to me."
)

NEWS_PROMPT_TEMPLATE = (
    "TASK: A new tech event just happened. Write ONE LinkedIn post about EXACTLY this event "
    "(no other topic):\n"
    "Source: {source}\nHeadline: {title}\nSummary: {summary}\n\n"
    + PERSONA
    + "Structure the post in this order:\n"
    + "1. HOOK: one punchy line about the event itself.\n"
    + "2. WHAT HAPPENED: synthesize the story in simple words, naming the companies, products "
    + "and people involved. Explain jargon the moment it appears.\n"
    + "3. THE LESSON: one clear takeaway or insight the reader can learn from it - a technical "
    + "explanation, a security practice, or a career lesson. This is the most important part.\n"
    + "4. QUESTION: end with a thought-provoking question or call-to-action to spark comments.\n"
    + "Do NOT copy sentences from the summary; use it only as source material. Do NOT invent "
    + "fake companies, statistics or events beyond what the headline/summary states.\n"
    + "Guidelines:\n"
    + STYLE_RULES
    + "\n\nOUTPUT CONTRACT: Your entire reply must be ONLY the raw post text - no preamble like "
    "'Here is a draft', no explanations, no markdown headers, no offers to revise, no questions "
    "to me."
)


def load_topics():
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return [line.rstrip("#").strip() for line in lines]


def load_used_topics():
    if not os.path.exists(POSTED_LOG):
        return set()
    used = set()
    with open(POSTED_LOG, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(" | ")
            if len(parts) >= 3:
                used.add(parts[2])
    return used


def clean_output(raw):
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    segments = [seg.strip() for seg in re.split(r"\n\s*---+\s*\n", text)]
    if len(segments) > 1:
        text = max(segments, key=len)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)__([^_]+)__(?!\w)", r"\1", text)
    text = re.sub(
        r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2190-\u21FF\u2700-\u27bf\U0001F1E6-\U0001F1FF]",
        "",
        text,
    )
    text = re.sub(r"([?!.,])\1{2,}", r"\1\1", text)
    lines = text.splitlines()
    while lines and (not lines[0].strip() or re.match(
            r"^(here('s| is)|certainly|sure|below is|i've|i have)", lines[0].strip(), re.I)):
        lines.pop(0)
    while lines and (not lines[-1].strip() or re.match(
            r"^(want |need |let me |shall i|just say|feel free|\*\*why)", lines[-1].strip(), re.I)):
        lines.pop()
    return "\n".join(lines).strip()


def resolve_opencode():
    cmd = os.environ.get("OPENCODE_CMD", "opencode")
    resolved = shutil.which(cmd) or shutil.which(f"{cmd}.cmd") or shutil.which(f"{cmd}.exe")
    if not resolved:
        raise RuntimeError(
            f"'{cmd}' not found on PATH. Install opencode or set OPENCODE_CMD in .env to its full path."
        )
    return resolved


def run_opencode(prompt):
    model = os.environ.get("OPENCODE_MODEL")
    resolved = resolve_opencode()
    command = [resolved]
    if "claude" in os.path.basename(resolved).lower():
        command.append("-p")
    else:
        command.append("run")
        if model:
            command += ["--model", model]
    proc = subprocess.run(command, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", cwd=BASE_DIR)
    if proc.returncode != 0 or not proc.stdout.strip():
        err = (proc.stderr or proc.stdout or "no output").strip()
        raise RuntimeError(f"opencode run failed: {err[:500]}")
    post_text = clean_output(proc.stdout)
    if len(post_text) < 80:
        raise RuntimeError(f"Generated post too short ({len(post_text)} chars): {post_text[:200]}")
    return post_text


def pick_static_topic():
    topics = load_topics()
    used = load_used_topics()
    fresh = [t for t in topics if t not in used]
    pool = fresh if fresh else topics
    if not pool:
        raise RuntimeError(f"No topics found in {TOPICS_FILE}")
    return random.choice(pool)


def generate_post(topic=None):
    load_env()
    news_item = None
    if topic is None:
        news_item = scraper.pick_news_item()

    if news_item:
        label = f"[{news_item['source']}] {news_item['title']}"
        prompt = NEWS_PROMPT_TEMPLATE.format(
            source=news_item["source"],
            title=news_item["title"],
            summary=news_item["summary"] or "(no summary available)",
        )
    else:
        label = topic if topic else pick_static_topic()
        prompt = TOPIC_PROMPT_TEMPLATE.format(topic=label)

    post_text = run_opencode(prompt)
    if len(post_text.split()) < 260:
        post_text = run_opencode(
            prompt
            + "\n\nCRITICAL: your previous attempt was too short. Rewrite it with at least 300 "
            + "words: deeper technical explanation, concrete lesson, examples."
        )
    source_link = None
    if news_item:
        scraper.mark_used(news_item["link"])
        source_link = news_item["link"]
        post_text = post_text.rstrip() + f"\n\nSource: {news_item['source']}"
    return label, post_text, source_link


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    topic_arg = " ".join(sys.argv[1:]) or None
    chosen, text, _link = generate_post(topic_arg)
    print(f"TOPIC: {chosen}\n---\n{text}")
