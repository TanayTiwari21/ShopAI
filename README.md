# ShopAI — AI-Powered Payment Risk Investigation Layer

**Live demo:** https://shopai.csproject.org

An AI-powered payment risk investigation layer that sits around the payment workflow and gives merchants **explainable, evidence-backed risk analysis** with an **explicit accept/decline decision**. Every risk score is deterministic and auditable; the LLM's job is to explain it in plain language and answer follow-up questions — it never decides the score and never moves money on its own.

---

## Table of contents

- [Evaluation results](#evaluation-results)
- [How it works](#how-it-works)
- [The AI agent](#yes-this-project-has-an-ai-agent)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Running it locally](#running-it-locally)
- [Testing](#testing)
- [Known limitations](#known-limitations)

---

## Evaluation results

`risk_engine.py` is measured against a reproducible, 300-case synthetic held-out test set with independent ground-truth labels — not just demoed. Full methodology, per-case results, and a named failure mode are in [`evaluation/risk_engine_evaluation_report.md`](evaluation/risk_engine_evaluation_report.md).

| Threshold | Precision | Recall | F1 | False Positive Rate |
|---|---|---|---|---|
| **FLAG** (score ≥ 30 → review or decline) | 0.521 | 0.817 | 0.636 | 0.188 |
| **DECLINE** (score ≥ 60 → outright block) | 1.000 | 0.333 | 0.500 | 0.000 |

- **Zero legitimate customers wrongly auto-declined** in the test set (100% precision at the decline threshold).
- **Net cost saved vs. no detector: ₹6,716.91** (63% reduction) across the held-out set, with a full cost breakdown by category.
- **A real, named blind spot**: account-takeover fraud on established accounts (0/11 caught) — found by deliberately hardening the test set after an earlier version scored a suspicious 100%/100%. Reported honestly, not hidden.

See [Testing](#testing) below for how to view or reproduce these numbers yourself.

---

## How it works

```
Merchant checkout ──► risk_engine.py (deterministic score + evidence)
                              │
                              ▼
                    Gemini (LLM agent) explains the score
                    in plain language, answers follow-up
                    questions via tool-calling into
                    risk_tools.py — never invents facts,
                    never sets the score
                              │
                              ▼
                    Merchant Dashboard (📋 icon, badge
                    for pending decisions)
                              │
                              ▼
                    Merchant clicks Accept/Decline
                    (the only thing that can trigger
                    a real payment action)
                              │
                              ▼
                    payment.py ──► Razorpay's server
                    (create_order / create_refund)
```

**The safety boundary, stated explicitly**: the LLM (Gemini) only ever gets *read-only* investigation tools. Money-moving actions (`create_order`, `create_refund`) are wired only into deterministic backend code, triggered only by an explicit human Accept/Decline click. No AI system in this project can authorize a payment.

---

## Yes, this project has an AI agent

Specifically, `risk_explainer.py`'s tool-calling loop (`_run_tool_loop`). When a merchant asks a question, Gemini doesn't just answer from a single prompt — it decides for itself which tools to call (`get_customer`, `get_customer_history`, `get_payment_history`, `analyze_risk_signals`), reads the results, decides whether it needs to call more, and loops autonomously (capped at 6 rounds) until it has enough to answer. That decide → act → observe → decide-again loop is what makes it a genuine agent, not just an LLM call with a system prompt.

What's deliberately **not** agentic, on purpose:

- **`risk_engine.py`** — pure deterministic rules, zero AI. The score needs to be auditable and reproducible (see [Evaluation results](#evaluation-results)), which an agent making judgment calls wouldn't give you.
- **`payment.py`** — no AI involved. Orders and refunds fire only from an explicit human Accept/Decline click, never from the agent's own judgment.

The agent investigates and explains; it never scores, and it never moves money.

---

## Features

- **Deterministic risk engine** (`risk_engine.py`) — weighted scoring across amount anomaly, new-account risk, failed payment attempts, and velocity spikes. Every factor carries concrete evidence, not just a label.
- **AI investigation agent + merchant chat** (`risk_explainer.py`) — Gemini translates the score into language a non-technical merchant understands, and answers follow-up questions by autonomously calling real tools (`risk_tools.py`) instead of guessing.
- **Explicit accept/decline workflow** — every decision is human-made and stored in an audit trail (`risk_database.py`), never automated.
- **Merchant Dashboard** — a 📋 icon with a live notification badge for pending decisions; click through to review evidence, chat history, and decide.
- **Razorpay payments** (`payment.py`) — order creation and refunds go through Razorpay's official server.

---

## Tech stack

- **Backend**: FastAPI (Python), in-memory data store for this demo
- **LLM**: Google Gemini (`gemini-3.6-flash`) via the Interactions API, function-calling for grounded investigation, with automatic retry on rate limits
- **Payments**: Razorpay, via their official remote MCP server
- **Frontend**: Vanilla HTML/CSS/JS (no framework/build step)

---

## Project structure

```
backend/
  main.py                       FastAPI app, all routes
  models.py                     Pydantic request/response models
  data.py                       Product catalog
  payment.py                    Razorpay integration
  risk_engine.py                Deterministic scoring engine
  risk_tools.py                 Investigation tool functions
  risk_database.py              In-memory data store
  risk_explainer.py             Gemini agent: explanation + chat layer
  requirements.txt

frontend/
  index.html
  app.js
  style.css

evaluation/
  generate_held_out_set.py          Synthetic held-out test set generator (seeded)
  evaluate_risk_engine.py           Runs the engine against it, computes metrics
  held_out_test_set.json            The 300 generated test cases
  held_out_test_set_results.csv     Per-case predictions, for direct audit
  evaluation_summary.json           Machine-readable metrics summary
  risk_engine_evaluation_report.md  Full write-up
```

---

## Running it locally

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in `backend/`:

```
RAZORPAY_KEY_ID=your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
GEMINI_API_KEY=your_gemini_key
```

```bash
uvicorn main:app --reload
```

### 2. Frontend

Open `frontend/index.html` directly, or serve it with any static server. It talks to `http://localhost:8000/api` automatically when run locally (see `API_BASE` in `app.js`).

---

## Testing

### View the evaluation report (no setup needed)

The numbers in [Evaluation results](#evaluation-results) above are already computed and committed to this repo — nothing needs to run for you to see them:

- [`evaluation/risk_engine_evaluation_report.md`](evaluation/risk_engine_evaluation_report.md) — full write-up: methodology, results, cost analysis, the named failure mode.
- [`evaluation/held_out_test_set_results.csv`](evaluation/held_out_test_set_results.csv) — every one of the 300 test cases with its prediction, for direct line-by-line audit.
- `evaluation/evaluation_summary.json` — the same metrics in machine-readable form.

### Reproduce the evaluation yourself

The held-out set is generated with a fixed random seed, so re-running this produces the identical 300 cases and identical metrics shown in the report — nothing is cherry-picked after the fact.

```bash
cd evaluation
python generate_held_out_set.py   # regenerates the same 300 cases (seed=42)
python evaluate_risk_engine.py    # re-runs risk_engine.py against them, reprints all metrics
```

### Manually test the live app

With the backend running (see [Running it locally](#running-it-locally)):

1. Open the frontend, add a product to the cart, and check out.
2. Switch the "shopping as" account (top nav) to **Alex Rivera** or **Priya Nair** first — these two are seeded with data designed to trigger a HIGH risk score (new account, failed payment attempts, amount anomaly). Checking out as one of the original three customers will mostly show LOW risk instead.
3. Open the 📋 merchant dashboard — the transaction should appear as pending, with a notification badge.
4. Click into it to see the risk score, evidence, the plain-language explanation, and ask the chat a follow-up question (e.g. "has this customer paid before?").
5. Accept or Decline — check the dashboard again to confirm the decision was recorded and the badge count dropped.

---

## Known limitations

- **The held-out test set is synthetic**, not real transaction data — generated with a fixed random seed for full reproducibility, not real customer history.
- **Account-takeover fraud on established accounts is currently undetected** (see evaluation report) — the engine has no signal for "this normal-looking account is suddenly behaving differently," only for newness, failures, and velocity.
- **In-memory data store** — this demo uses plain Python dicts for simplicity; a production version would need a real database.

---

## Topics

`explainable-ai` · `fastapi` · `fraud-detection` · `gemini` · `llm-agents` · `payment-risk` · `razorpay`
