# Support Ticket Triage v2 — Local Agentic Ticket Workflow

Free local upgrade of the uploaded **Project1_support-ticket-classifier**. Inspired by the original six-node LangGraph classification pipeline (PII redaction, injection check, LLM classification, validation, fallback, cost logging). This is a **new implementation** with local model integration, deterministic routing, persistent ticket lifecycle, review and audit endpoints. It does not include or require the paid OpenAI API.

## 1. What the user inputs and receives

Input: `My laptop order has not arrived. Please help urgently.`

Output: JSON with a unique ticket ID, category (`delivery_issue`), priority (`high` if predicted), deterministic team (`logistics_team`), status (`assigned` or `pending_review`), model estimate, and a PII-redacted ticket. Results vary by model. No external support desk is contacted.

## 2. Technical architecture

```text
Browser UI / POST /tickets
        |
        v
     FastAPI
        |
        v
 LangGraph: PII redact -> injection flag -> Ollama structured classification
        |                     |
        |                model failure or suspicious input
        |                     v
        |                manual review
        v
 Deterministic category -> team routing
        |
        v
 Provisional review rule (low model score / critical / other / suspicious)
        |
        v
 SQLite ticket + audit event
        |
        v
 GET tickets / review / status transitions / audit events
```

**Important:** Model self-reported confidence is *not calibrated*. Do not use this prototype for automatic high-impact customer decisions. Review requires trust/authentication in any deployed system; local demo is intentionally unauthenticated. Regex-based PII and injection checks are incomplete by design.

## 3. Local setup (no API charges)

Requirements: Python 3.11+, enough memory to run a local Ollama model. Ollama can be installed from https://ollama.com .

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\\Scripts\\Activate.ps1
pip install -r requirements-dev.txt
ollama pull qwen3:4b
ollama serve  # only if Ollama is not already running
```

In a second terminal from the project directory:

```bash
uvicorn app.main:app --reload
```

Go to http://127.0.0.1:8000 for the browser UI and http://127.0.0.1:8000/docs for Swagger.

The model and URL can be configured using `OLLAMA_MODEL` / `OLLAMA_BASE_URL`. Copy `.env.example` to `.env` as a reminder, but note: this implementation reads **environment variables directly**; export them in your shell or launch with `uvicorn app.main:app --env-file .env` (requires `python-dotenv`, included). Never commit `.env`.

### Offline smoke demo without an LLM

```bash
# Linux/macOS
MODEL_PROVIDER=rules_demo uvicorn app.main:app --reload
# Windows PowerShell
# $env:MODEL_PROVIDER='rules_demo'; uvicorn app.main:app --reload
```

`rules_demo` is keyword matching, **not AI**; it forces manual review and is useful to exercise UI/DB when Ollama is unavailable.

## 4. API

```bash
curl -X POST http://127.0.0.1:8000/tickets \
  -H 'Content-Type: application/json' \
  -d '{"ticket_text":"My laptop delivery is late and I need it urgently"}'

curl http://127.0.0.1:8000/tickets
curl http://127.0.0.1:8000/health
```

POST `/tickets/{ticket_id}/review` with `{"issue_category":"delivery_issue","priority":"high","note":"Verified by operator"}` only for `pending_review` tickets.

POST `/tickets/{ticket_id}/status` with `{"status":"in_progress","note":"Investigating"}` then `{"status":"resolved","note":"Resolved"}`.

Other endpoints: GET `/tickets/{ticket_id}`, GET `/tickets/{ticket_id}/events`, GET `/tickets?status=pending_review`.

## 5. Tests and evaluation

```bash
pytest -q
python -m evaluation.run_eval
```

Unit + API tests mock the classifier so **no Ollama or paid API is needed for CI**. If LangGraph is not installed, a small sequential fallback executes the identical four nodes for offline smoke/testing; with LangGraph installed, the real compiled LangGraph graph is used. The 6-case benchmark is a smoke dataset only. A portfolio-ready report should use a larger held-out labeled dataset with category macro-F1, priority macro-F1, routing accuracy, review coverage, and median/p95 latency. Compare Qwen3 variants and a TF-IDF baseline; publish actual measurements (not invented values).

## 6. Portfolio talking points

- LangGraph orchestration and structured tool/LLM output
- Pydantic validation and deterministic routing mapping
- SQLite ticket persistence with audit events and transition checks
- Review gates, safe failure fallback and privacy-first inference
- FastAPI, HTML dashboard, pytest, GitHub Actions, Docker

## 7. Known limitations / next upgrades

1. Local demo has **no authentication**: do not expose directly to the Internet. Add RBAC and SSO before production.
2. Sensitive raw text is not persisted, but can reach local FastAPI process memory. Regex redaction is not complete; review false negatives.
3. Model confidence is uncalibrated. Require an offline calibration/evaluation phase before automatic routing.
4. SQLite is fine for local demo, not a shared multi-node production database. Use PostgreSQL and migrations later.
5. Blocking LLM call is synchronous; a multi-user service should use a bounded queue and worker processes.
6. No third-party help desk integration, actual customer refund, or email sending is claimed.
7. Injection rules are illustrative only; policy must be enforced independently of LLM output.

## 8. Cost

$0 in required API/cloud fees when running on existing local hardware. Electricity, hardware, and model download bandwidth are separate.
