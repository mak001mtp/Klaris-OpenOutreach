# CLAUDE.md

## Rules

- **Python env**: Always use `.venv/bin/python` (not system `python3`).
- **Commits**: No `Co-Authored-By` lines. Single-line messages (no body).
- **Dependencies**: Managed in `requirements/*.txt` (used by local dev and Docker).
- **Docs sync**: When modifying code, update CLAUDE.md and ARCHITECTURE.md to reflect changes.
- **No memory**: Never use the auto-memory system (no MEMORY.md, no memory files). All persistent context belongs in CLAUDE.md or ARCHITECTURE.md.
- **Error handling**: App should crash on unexpected errors. `try/except` only for expected, recoverable errors. Custom exceptions in `exceptions.py`.
- **No API backward compat**: Project has no external users yet — don't preserve old Python APIs, function signatures, or import paths. Rename, delete, and rewrite freely; no shims or re-export modules. DB schema changes still go through Django migrations as normal — existing installs must upgrade cleanly.

## Project Overview

OpenOutreach — self-hosted LinkedIn automation for B2B lead generation. Playwright + stealth for browser automation, LinkedIn Voyager API for profile data, Django + Django Admin for CRM (models owned by this project).

## Commands

```bash
# Docker
make build / make up / make stop / make logs / make up-view

# Local dev
make setup    # install deps + browsers + migrate + bootstrap CRM
make run      # run daemon
make admin    # Django Admin at localhost:8000/admin/

# Testing
make test / make docker-test
pytest tests/api/test_voyager.py   # single file
pytest -k test_name                # single test
```

## Architecture (quick reference)

For detailed module docs, see `ARCHITECTURE.md`.

- **Pipeline scope**: qualify-only. No connect requests, no follow-ups, no chat. Three discovery funnels (people search / job signals / post signals) all feed the same LLM qualifier and produce QUALIFIED or FAILED Deals stamped with the funnel that surfaced them.
- **Entry**: `manage.py` — stock Django management. `rundaemon` command (migrate → onboard → validate → task queue loop). `manage.py` with no args defaults to `rundaemon`. Onboarding logic in `onboarding.py`: `OnboardConfig` (pure dataclass), `missing_keys()`, `collect_from_wizard()`, single `apply()` write path. Docker `start` script handles Xvfb/VNC, then `exec python manage.py rundaemon`.
- **State machine**: `enums.py:ProfileState` — only QUALIFIED and FAILED are reachable now (the post-connect states still exist on the enum for historical compatibility with the `Deal.state` choices, but no code transitions into them). `Outcome` (converted/not_interested/wrong_fit/etc.) on `Deal.outcome`. `Lead.disqualified=True` = permanent exclusion. LLM rejections = FAILED Deals with `wrong_fit` outcome (campaign-scoped).
- **Funnel attribution**: `crm.models.Source` (people_search / job_signal / post_signal) is stamped on `Deal.source` at qualification. The lookup goes through `crm.models.LeadDiscovery`, an audit row written by `discover_and_enrich(source=...)` every time a funnel surfaces a lead (even on dedup). `promote_lead_to_deal` and `_create_deal` read the latest `LeadDiscovery` for the lead and copy its `source` onto the new Deal.
- **Task queue**: `Task` model (persistent). One type: `qualify`. Handler in `linkedin/tasks/qualify.py`, signature `handle_qualify(task, session, qualifiers)`. The handler runs all three funnels (`run_job_discovery`, `run_content_discovery`, then drains `qualify_source`) and self-reschedules via `enqueue_qualify`. Task creation is centralized in `linkedin/tasks/scheduler.py`. `reconcile(session)` seeds one qualify task per campaign and recovers stale RUNNING rows; runs on daemon startup and whenever the queue drains. On 401 (`AuthenticationError`), the daemon calls `session.reauthenticate()`, marks the task FAILED, and reconcile re-creates it.
- **Three funnels**:
  - **People search** (existing) — `linkedin/pipeline/search.py` generates keywords from `Campaign.product_docs + campaign_objective`, navigates to `/search/results/people/`, enriches discovered /in/ URLs with `source="people_search"`.
  - **Job signals** (new) — `linkedin/actions/job_search.py` walks `Campaign.job_keywords`, navigates to `/jobs/search/`, extracts company URLs, then for each company iterates `Campaign.persona_keywords` to find buyers via people search. Discovered leads tagged `source="job_signal"`.
  - **Post signals** (new) — `linkedin/actions/content_search.py` walks `Campaign.content_keywords`, navigates to `/search/results/content/`, enriches post authors with `source="post_signal"`.
  - Each tick of `handle_qualify` runs all three sequentially, then drains the shared qualifier on whatever's in the Lead table.
- **ML pipeline**: GPR (sklearn) + BALD active learning + LLM qualification. Per-campaign models stored in `Campaign.model_blob` (DB). All three funnels feed the same Bayesian/LLM qualifier — no fork by source.
- **Config**: `SiteConfig` DB singleton (LLM_PROVIDER, LLM_API_KEY, AI_MODEL, LLM_API_BASE — editable via Django Admin; `llm_provider` chooses between OpenAI/Anthropic/Google/Groq/Mistral/Cohere/openai_compatible, `llm_api_base` only consulted when provider is `openai_compatible`), `conf.py:CAMPAIGN_CONFIG` (timing/ML defaults), `conf.py` browser constants (`BROWSER_*`, `HUMAN_TYPE_*`), `conf.py` schedule constants (`ENABLE_ACTIVE_HOURS` flag, active hours/timezone/rest days), `conf.py:FASTEMBED_CACHE_DIR` (persistent model cache, defaults to `<project>/.cache/fastembed/`), `Campaign` keyword fields (`job_keywords`, `content_keywords`, `persona_keywords` — JSON lists, edited in Django Admin), `LinkedInProfile` (Django Admin). `VOYAGER_REQUEST_TIMEOUT_MS` lives in `api/client.py` (constructor default on `PlaywrightLinkedinAPI`). `conf.py:DUMP_PAGES` (default `False`) — enable to save page HTML snapshots for fixture collection.
- **Lazy accessors**: `Lead.get_profile(session)` is a pure live Voyager scrape (no DB caching of the raw dict); `Lead.get_urn(session)` reads the `urn` column and falls back to a scrape; `Lead.get_embedding(session)` lazily scrapes + embeds on first access, then caches the 384-dim bytes on the row. `Lead.embed_from_profile(profile)` reuses an in-hand profile dict to skip the scrape (used by `create_enriched_lead`). `Lead.to_profile_dict()` returns a minimal `{lead_id, public_identifier, url, meta}` dict (no `profile` key). `AccountSession.campaigns` (cached_property, list). `AccountSession.self_profile` (cached_property, re-discovers via Voyager on first access per session — no DB cache).
- **Django apps**: `linkedin` (main — Campaign with users M2M + keyword JSON fields), `crm` (Lead, LeadDiscovery, Deal). `chat` (ChatMessage) is retained for historical migrations but unused by the qualify-only pipeline.
- **Data dir**: `data/` holds persistent state (`db.sqlite3`). Docker users mount volumes at `/app/data`.
- **Docker**: Playwright base image, VNC on port 5900, `BUILD_ENV` arg selects requirements.
- **CI/CD**: `.github/workflows/tests.yml` (pytest), `deploy.yml` (build + push to ghcr.io).
