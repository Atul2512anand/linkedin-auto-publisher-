# 🤖 LinkedIn Auto Publisher

An open-source automation that **scrapes fresh tech news → writes LinkedIn posts in your voice using AI agents (OpenCode / Claude Code) → publishes to your personal LinkedIn profile** on a schedule.

Zero paid APIs required. Bring your own AI agent.

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────┐
│  RSS Scrape │ →  │  Pick Event  │ →  │ AI Agent writes │ →  │ LinkedIn │
│ 15+ sources │    │ score+filter │    │  your persona   │    │  Profile │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────┘
```

## Features

- 🔥 **Event-driven content** - ranks stories by freshness and "newsworthiness" (launches, breaches, lawsuits)
- 🎭 **Your persona, your niche** - fully configurable via `persona.txt` + `topics.txt`
- 🔄 **Model-agnostic** - works with OpenCode (any model), Claude Code, or any CLI agent
- 📰 **Reach-optimized attribution** - source name in the post, source **link auto-commented** below it (external links in the post body suppress LinkedIn reach)
- 🔐 **Official LinkedIn API** - posts via `w_member_social`, no ToS-violating scrapers
- ⏰ **Scheduler-ready** - Windows Task Scheduler / cron examples included

---

## Quick Start

### 1. Install

```bash
git clone <this-repo>
cd linkedin-auto-publisher
pip install -r requirements.txt
```

You also need one of these installed and on your PATH:
- [OpenCode](https://opencode.ai) (`npm i -g opencode-ai`) — recommended, has free models
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`npm i -g @anthropic-ai/claude-code`)
- Any other CLI agent (see [Advanced](#using-a-different-cli-agent))

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```ini
LINKEDIN_CLIENT_ID=xxx        # from step 3 below
LINKEDIN_CLIENT_SECRET=xxx
LINKEDIN_REDIRECT_URI=http://localhost:8913/callback
OPENCODE_CMD=opencode         # or: claude
OPENCODE_MODEL=opencode/x-preview-f-free   # any model; omit to use your CLI default
NEWS_MAX_AGE_HOURS=72         # only use stories newer than this
```

### 3. Create the LinkedIn app (one-time, ~10 min, free)

> **Note:** LinkedIn requires *some* company page to exist before you can create a developer app. This is purely administrative — create an empty page once and never post to it. All publishing happens on **your personal profile**.

1. Create a throwaway page at https://www.linkedin.com/company/setup/new/ (any name, Industry: Technology)
2. Go to https://developer.linkedin.com/apps → **Create app**
   - Attach the page you just made, upload any logo, accept terms
3. In the app → **Settings** tab → **Verify** the company page (confirm in LinkedIn)
4. **Products** tab → request access to BOTH (instant, self-serve):
   - ✅ **Share on LinkedIn**
   - ✅ **Sign In with LinkedIn using OpenID Connect**
5. **Auth** tab:
   - Copy **Client ID** and **Client Secret** into your `.env`
   - Add redirect URL: `http://localhost:8913/callback`

### 4. Connect your account

```bash
python auth_linkedin.py
```

Browser opens → approve access → done. Tokens are saved to `tokens.json` (auto-refreshed afterwards).

### 5. Test

```bash
python generate.py            # preview a generated post (does NOT post)
python run_once.py --dry-run  # full pipeline, draft saved, no posting
python run_once.py            # REAL post to your profile 🚀
```

---

## Posting to a Company Page (instead of / in addition to personal)

The same pipeline can publish to **any LinkedIn Company Page you admin**. The difference is entirely in LinkedIn's developer permissions:

| | Personal profile | Company Page |
|---|---|---|
| Author URN | `urn:li:person:<id>` | `urn:li:organization:<id>` |
| Scope needed | `w_member_social` | `w_organization_social` (+ `r_organization_social`) |
| Product needed | Share on LinkedIn (instant) | **Community Management API** (requires app review) |
| Setup time | ~10 minutes | 10 minutes + review wait (days–weeks) |

### Step-by-step company page setup

**Step 1 — App ownership.** Your developer app must be created by/attached to the
company whose page you want to post to, and your account must be an **admin
(Super Admin or Content Admin)** of that page. If someone else owns the page,
have a super admin create the app, or add you as a page admin first.

**Step 2 — Request the product.**
1. Open https://developer.linkedin.com/apps → your app
2. **Products** tab → find **Community Management API** → **Request access**
3. You'll fill a review form. Tips that get approvals:
   - Use case: *"Our app schedules and publishes original content to OUR OWN
     company page. We do not post on behalf of third parties."*
   - Be specific about what data you touch (post text only) and why API access
     is required (automation/scheduling)
   - Company page URL, app description and privacy policy should be consistent
4. Wait for approval email — typically days to a couple of weeks.

> While waiting, everything else below still applies — personal-profile posting
> keeps working in the meantime.

**Step 3 — Configure `.env`.**

```ini
LINKEDIN_AUTHOR_TYPE=organization
LINKEDIN_ORGANIZATION_ID=<your numeric page ID>
```

**Step 4 — Find your page's numeric ID.** After approval, re-run:

```bash
python auth_linkedin.py
```

The script now requests the extra scopes (`w_organization_social`,
`r_organization_social`) during consent, and afterwards prints every page you
admin with its URN:

```
Fetching company pages you admin...
  - My Company: urn:li:organization:123456789
Copy the urn:li:organization:<ID> of your page into .env:
```

(Re-auth is required because scopes changed — LinkedIn needs fresh consent.)

**Step 5 — Test.**

```bash
python run_once.py --dry-run    # draft only
python run_once.py              # publishes AS THE COMPANY PAGE
```

Verify on your page that the post shows the page identity as author.

### Notes & limitations

- The post payload is identical for pages; only the `author` URN differs.
- One tokens.json = one destination. To post to personal AND a page from the same
  machine, keep two copies of this repo (one per `.env`), or run auth twice and
  swap configs.
- Page posts appear as the **page**, not as you personally — reactions come from
  the page identity.
- If you get `401/403 Access denied` on posting: the Community Management API
  product isn't approved yet, or the authenticated user isn't a page admin.
- Rate limits: ~100k posts/day/app, 150/day/member — irrelevant at 2x weekly.

---

## Visuals: hero images & carousels (optional, off by default)

Set `VISUAL_MODE` in `.env`:

| Mode | What happens |
|---|---|
| `off` | Text-only post — original behavior, zero risk |
| `image` | Free AI hero image from [Pollinations.ai](https://pollinations.ai) (no API key needed), styled from your post's hook, attached to the post |
| `carousel` | Your post is parsed into slides (hook cover → numbered takeaways → CTA card), rendered as branded 1080×1350 cards with Pillow, merged into a **PDF** and uploaded as a native **LinkedIn carousel/document post** — the high-reach format |

Extra settings:

```ini
VISUAL_MODE=carousel
BRAND_NAME=Atul Anand        # printed on every slide
ACCENT_COLOR=#22D3EE         # accent bars, numbers, progress dots
```

Safety design: visuals are built *before* posting; if image generation or upload
fails for any reason, the post falls back to text-only automatically and logs a
warning. Generated assets are saved to `drafts/assets/` for review.

---

## Make it yours

### Change the niche / topics

Two layers control what gets written:

**`persona.txt`** — who is writing? Your identity, tone, lanes, what to avoid.
Delete it to fall back to the generic built-in persona. This is where you say
"I'm a data engineer" or "I write about fintech" or "never mention crypto".

**`topics.txt`** — backup evergreen ideas (used when RSS fails). One per line,
ending with `#`. Rewrite entirely for your niche:

```
Why vector databases changed retrieval forever #
Kubernetes for people who hate Kubernetes #
...
```

The news scraper keyword filter lives in [`scraper.py`](scraper.py) under `KEYWORDS`,
`NEGATIVE_KEYWORDS` and `EVENT_KEYWORDS` — edit these lists to match your niche
(currently tuned for cybersecurity/AI/CS; e.g. swap in `fintech`, `payments`,
`devtools` etc.).

### Switch AI models / agents

| You want | Set in `.env` |
|---|---|
| OpenCode default model | remove/comment `OPENCODE_MODEL` |
| A specific OpenCode model | `OPENCODE_MODEL=provider/model` (run `opencode models` to list) |
| **Claude Code** | `OPENCODE_CMD=claude` (the `-p` flag is applied automatically) |
| Another CLI agent | `OPENCODE_CMD=<binary>` — script passes prompt via stdin |

Free starting points: `opencode/x-preview-f-free`, or add an [OpenRouter](https://openrouter.ai)
key to your opencode config and use any `openrouter/...` free model.

### Recommended free models (ranked)

> Free tiers rotate often. Verify what's live with `opencode models`, and before
> committing to a model, run `python generate.py` 2-3 times and compare output
> quality against your current model.

**Via OpenCode Zen (no extra setup if you're logged into Zen):**

| Rank | Model | Notes |
|---|---|---|
| 1 | `opencode/x-preview-f-free` | Stealth preview ("Ox Alpha"), excellent instruction-following, 1M context. Free window — may end, watch for expiry |
| 2 | `opencode/nemotron-3-ultra-free` | NVIDIA 550B MoE — biggest standing free model, strong reasoning |
| 3 | `opencode/hy3-free` | Tencent HunyuanYuan 3 — good long-form writing |
| 4 | `opencode/nemotron-3.5-lightning-free` | Newer Nemotron gen, fast |
| 5 | `opencode/mimo-v2.5-free` | Xiaomi MiMo — decent mid-size fallback |

**Via OpenRouter (needs free key: `opencode auth login` → openrouter):**

| Rank | Model | Notes |
|---|---|---|
| 1 | `openrouter/z-ai/glm-5.2:free` | GLM family — community analysis suggests Ox Alpha itself is GLM-based, so this is the closest sibling |
| 2 | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | Same 550B model via OpenRouter |
| 3 | `openrouter/thinkingmachines/inkling:free` | Worth testing |
| 4 | `openrouter/google/gemma-4-31b-it:free` | Small but reliable |

⚠️ OpenRouter `:free` models are rate-limited (~50 requests/day without credits,
~1000/day once you've ever added $10 credits). Fine for 2 posts/week + testing.

**Other providers (own free API key via `opencode auth login`):**

| Provider | Model example | Why |
|---|---|---|
| Google AI Studio | `google/gemini-flash-latest` | 1M context, generous free daily quota, great instruction-following — best standing free option |
| GitHub Models | via GitHub token | Free for students via GitHub Student Developer Pack |
| Groq | llama/qwen variants | Very fast, solid free tier |
| Ollama (local) | `qwen3`, `llama3.1` | Unlimited requests, offline, quality depends on your hardware |

**Strategy:** ride free stealth-preview windows while they last, keep
`nemotron-3-ultra-free` or Gemini Flash as your permanent fallback, and re-check
`opencode models` every few weeks — new free previews appear regularly.

**Note on visuals:** carousel design quality is model-independent (rendered by
code); only the text quality depends on the model. Hero images use Pollinations
(a diffusion service), also independent of your LLM choice.

---

## Automate on a schedule

### Windows (Task Scheduler)

```powershell
$py = (Get-Command python).Source
$dir = "C:\path\to\linkedin-auto-publisher"
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$dir\run_once.py`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Friday -At 10:00
Register-ScheduledTask -TaskName "LinkedInAutoPost" -Action $action -Trigger $trigger
```

### Linux / macOS (cron)

```bash
crontab -e
# Tuesdays and Fridays at 10:00
0 10 * * 2,5 cd /path/to/repo && /usr/bin/python3 run_once.py >> logs/cron.log 2>&1
```

> Your machine only needs to be ON around the scheduled time. For fully unattended
> runs, host the repo on GitHub Actions or a small VPS.

---

## How it works

| File | Role |
|---|---|
| `scraper.py` | Pulls RSS from TechCrunch, Wired, The Verge, Ars Technica, Engadget, CNET, Gizmodo, ZDNet, Mashable, The Hacker News, Hacker News (+ more), filters by keywords, scores by freshness/event-signal |
| `generate.py` | Builds the prompt (persona + event + rules), calls your CLI agent via stdin, cleans output, enforces minimum length with auto-retry |
| `linkedin_client.py` | OAuth token management (60-day expiry, auto-refresh) + posting via `/rest/posts` with `/v2/ugcPosts` fallback |
| `auth_linkedin.py` | One-time OAuth login (local callback server on port 8913) |
| `run_once.py` | Orchestrates everything, saves drafts to `drafts/`, logs to `logs/posted.log` |
| `visuals.py` | Optional hero images (Pollinations) & branded PDF carousels (Pillow); controlled by `VISUAL_MODE` |

Rate limits: LinkedIn allows ~150 posts/day/member — a 2x-weekly schedule uses 0.03% of it.

## Troubleshooting

| Problem | Fix |
|---|---|
| `'opencode' not found on PATH` | Install it, or set `OPENCODE_CMD` to the full binary path in `.env` |
| `token expired` / auth errors mid-run | Re-run `python auth_linkedin.py` (needed roughly every 60 days if refresh fails) |
| Some feeds print 403 warnings | Normal — a few sites block bots; the pipeline continues with remaining sources |
| Generated post off-topic | Tighten `persona.txt` lanes and `KEYWORDS` in `scraper.py`; delete `cache/news_<date>.json` to re-scrape |
| Want to re-generate the same story | Remove its link from `logs/used_links.txt` |

## Disclaimer

This tool uses LinkedIn's official API within free-tier limits, but automated posting
is still your responsibility: review drafts regularly, keep content authentic, and
follow LinkedIn's policies. Excessive automation can put any account at risk —
2x weekly with quality content (what this tool is designed for) is well within
normal human behavior.

## License

MIT — see [LICENSE](LICENSE).
