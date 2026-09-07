# job-agent

Human-in-the-loop SWE job search, application & networking agent.

Pipeline: **discover → normalize/dedup → sponsorship evidence → resume match → rank → daily digest → human decision → application prep → human review → human submit**. Networking is deferred (see `ARCHITECTURE.md`).

The MVP is implemented and tested end to end. It runs with **zero external keys** (SQLite for dev; the LLM is used only for cover-letter drafting when `ANTHROPIC_API_KEY` is set, with a deterministic template fallback).

## Guarantees baked into the design
- No application is submitted and no message sent without an explicit human `APPROVED`/`SUBMITTED` transition — enforced by the state machine (agents can't reach those states).
- Every derived claim (sponsorship, match) carries provenance + a FACT/INFERENCE/UNKNOWN label.
- Sponsorship never emits a bare "yes"; silence/uncertainty → UNKNOWN/UNCLEAR + needs-verification.
- Nothing is fabricated; drafting is constrained to verified profile facts.
- No CAPTCHA/auth/rate-limit bypass. Only the GitHub connector is active; others are stubs to plug in later.

## Quick start (zero-setup SQLite)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp config/profile.example.yaml config/profile.yaml   # edit with your real profile (PII, gitignored)
export DATABASE_URL="sqlite:///data/jobs.db"
mkdir -p data && job-agent init-db

# Full pipeline: fetch -> score -> digest
job-agent run --stage all
# ...or individually:
job-agent run --stage discovery     # fetch from GitHub repos (cron-safe lane)
job-agent run --stage enrich        # sponsorship + match + rank
job-agent run --stage digest        # build data/digest_<date>.html (emails if SMTP set)

# Browse & act
job-agent top --limit 15            # highest-ranked jobs
job-agent load-profile              # load your profile as the candidate
job-agent shortlist 112 118         # shortlist by job ID (from `top`/`jobs`)
job-agent prepare 112               # build review package -> AWAITING_REVIEW
job-agent review 1                  # inspect cover letter + classified answers
job-agent approve 1                 # human: AWAITING_REVIEW -> APPROVED
job-agent submit 1                  # after you submit yourself: APPROVED -> SUBMITTED
job-agent feedback                  # suggest weight changes from your decisions (--apply to apply)

job-agent dashboard                 # web UI at http://127.0.0.1:8000
```

For production, point `DATABASE_URL` at Postgres+pgvector (`docker compose up -d db`) and use Alembic.

## Running it (on-demand now; cloud schedule later)
By design there is **no local cron**. You trigger a run yourself whenever you want fresh results:
```
job-agent run --stage all      # discover -> hydrate -> enrich -> digest (+ email if SMTP set)
```
The same one command is what a scheduler will call once the system lives on an always-on cloud
host. Do NOT put it in local crontab — a laptop that's asleep at the scheduled time misses runs.
When you deploy to cloud, add the schedule there (cron/APScheduler); example (8:00 AM Phoenix):
```
# cloud host only, when ready:
0 8 * * *  cd /path/to/job-agent && .venv/bin/job-agent run --stage all >> data/cron.log 2>&1
```
The supervised lane (`run --supervised`, includes LinkedIn later) always needs a present human —
never schedule it.

## Component status
| Module | State |
|---|---|
| `connectors/github_list` | ✅ live (HTML + markdown READMEs, ATS + dates, dedup) |
| `normalize/` (dedup, normalizer) | ✅ implemented |
| `sponsorship/` (assessor + official-data loader) | ✅ implemented (JD signals; USCIS/DOL cache optional) |
| `matching/` | ✅ implemented (rule + lexical; embeddings optional) |
| `ranking/` | ✅ implemented (configurable, explainable) |
| `pipeline/` (discovery, enrich, digest, all) | ✅ implemented |
| `digest/` (HTML + SMTP) | ✅ implemented |
| `application/` (state machine, classifier, prep, CLI) | ✅ implemented |
| `dashboard/` (FastAPI) | ✅ implemented |
| `feedback/` | ✅ implemented (transparent, reversible) |
| `connectors/ats_api`, `connectors/linkedin_supervised` | 🟡 stubs (disabled in config; plug in later) |
| `networking/` | ⚪ deferred (schema present) |

Run the tests: `pytest -q`.

This is an informational tool for job search and screening, not legal or immigration advice. Sponsorship outputs are evidence summaries with confidence levels and must be independently verified.
