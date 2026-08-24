# AGENTS.md — Project Context for AI Agents

Read this before working in this repo. It explains what this project does, how it fits together, and the non-obvious lessons learned while building it.

## What this project is

An event-driven LinkedIn content automation that runs 100% on free tiers:

```
scraper.py            generate.py                linkedin_client.py
RSS from 15 sources → picks freshest/best-scored  →  posts via official
(TechCrunch, Wired,   tech event → builds prompt    LinkedIn API
 THN, Verge, Ars...)  from persona.txt + rules   (w_member_social,
                      → sends via STDIN to a     personal profile,
                      CLI AI agent               urn:li:person:<id>)
                      (opencode OR claude code)
                              ↓
                      run_once.py orchestrates all of it, saves drafts/,
                      logs to logs/posted.log
```

Scheduled twice weekly (Tue/Fri 10:00 IST) via Windows Task Scheduler task
named `LinkedInAutoPost` (registered with `Register-ScheduledTask`, NOT schtasks).

## File map

| File | Purpose |
|---|---|
| `common.py` | Paths, `.env` loader, dir creation |
| `scraper.py` | RSS collection, keyword filtering, freshness/event scoring, daily JSON cache |
| `generate.py` | Prompt building, agent invocation, output cleaning, length retry |
| `persona.txt` | **User-editable** writer identity/niche. Delete → generic default |
| `topics.txt` | Evergreen backup topics (lines end with `#`) |
| `auth_linkedin.py` | One-time OAuth (local callback server on port 8913) |
| `linkedin_client.py` | Token refresh + post creation (`/rest/posts` with `/v2/ugcPosts` fallback) |
| `run_once.py` | Orchestrator (`--dry-run`, `--topic`) |
| `.env` | Secrets + config (git-ignored, never commit) |
| `tokens.json` | OAuth tokens (git-ignored) |

## Commands

```bash
python generate.py             # preview only - scrape + generate, NO posting
python run_once.py --dry-run   # full pipeline, saves draft, no posting
python run_once.py             # generate AND publish
python auth_linkedin.py        # re-auth when tokens expire (~every 60 days)
```

Model/agent is chosen entirely by `.env`:
- `OPENCODE_CMD=opencode` (or `claude`; `-p` flag auto-applied for claude)
- `OPENCODE_MODEL=provider/model` (omit line → CLI's default model)

## Critical implementation notes (do not regress these)

1. **Agent prompts MUST be piped via stdin**, not passed as argv. Multiline args get
   mangled through npm `.cmd` shims on Windows (agent receives truncated prompt).
2. **Prompts end with an OUTPUT CONTRACT** ("reply ONLY with raw post text, no
   preamble/questions/tools") because CLI agents otherwise act conversationally or
   try to use tools (file reads trigger permission prompts in non-interactive mode).
3. `generate.py` and anything printing content must call
   `sys.stdout.reconfigure(encoding="utf-8")` — Windows consoles default to cp1252
   and crash on emoji/arrows in generated text.
4. Resolve agent binaries with `shutil.which()` — plain names fail because of
   Windows PATHEXT (.cmd shims).
5. Scraper filters use **word-boundary regex**, not substring (`"ai"` must not match
   "said"/"actually"), plus NEGATIVE_KEYWORDS and price-pattern filters
   (`save $X`, `% off`, `lowest-ever`) to block shopping/deal spam.
6. Daily news cache lives in `cache/news_<date>.json`. **Delete it to force a fresh
   scrape** after changing KEYWORDS/filters.
7. Used stories tracked in `logs/used_links.txt`; posted history in
   `logs/posted.log` (format: `timestamp | status | topic`).
8. Expected harmless warnings: BleepingComputer/SecurityWeek/Krebs feeds return
   403 (Cloudflare blocks bots) — pipeline continues with remaining sources.

## Content rules (encoded in generate.py)

- Persona loaded from `persona.txt` (Atul: cybersecurity/AI/CS student-researcher voice,
  recruiter-magnet depth, light health-tech touches only)
- STRICTLY no gaming/consumer-gadget/entertainment content
- 280–450 words, hook → jargon-decoded explanation → lesson/takeaway → CTA question,
  4–5 hashtags, companies named, source link auto-appended by code
- Auto-retry once if output < 260 words

## Repo notes

- This is a NESTED git repo inside a larger OneDrive-folder repo; always run git
  commands from this directory.
- Remote: `https://github.com/Atul2512anand/linkedin-auto-publisher-.git` (main)
- Never commit `.env`, `tokens.json`, `drafts/`, `logs/`, `cache/`.
