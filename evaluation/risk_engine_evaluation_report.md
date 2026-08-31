# risk_engine.py — Held-Out Evaluation Report

This report evaluates `risk_engine.py`'s deterministic fraud detector against a
synthetic, labeled, held-out test set — reproducible by anyone from the two
scripts in this repo:

```
python generate_held_out_set.py   # builds held_out_test_set.json (seed=42)
python evaluate_risk_engine.py    # runs the engine against it, prints + saves metrics
```

## Methodology

- **300 synthetic transactions**, 240 legit (80%) / 60 fraud (20%). The
  20% fraud rate is intentionally higher than real-world incidence
  (often <1%) so the test set has enough positive examples for recall to be
  statistically meaningful — reported explicitly, not hidden.
- **Ground-truth labels come from the generating scenario, never from the
  engine.** The engine never sees or influences the label. This avoids the
  circular trap of effectively grading the engine against its own opinion.
- **The set is deliberately hard, not just easy cases.** ~40% of legit
  cases and ~50% of fraud cases are "hard" variants designed to stress-test
  the engine specifically — see scenario list below. An earlier draft of
  this set scored a suspicious 100%/100% at the flag threshold; that was a
  sign the test wasn't hard enough, not that the engine was flawless. The
  scenarios below were added specifically to find real failure modes.
- The engine is called directly (`RiskEngine().calculate_score(...)`) with
  synthetic data — it never touches the live app's database, so this
  evaluation is fully isolated and reproducible.

### Scenarios

| Legit (label=0) | Fraud (label=1) |
|---|---|
| `legit_established` — normal repeat customer | `fraud_textbook` — new account + failed attempts + velocity + amount anomaly |
| `legit_new_normal` — genuine new customer, no other signals | `fraud_evasive_no_retries` — new account + big first purchase, card works first try |
| `legit_big_onetime` — loyal customer, one big one-off purchase | `fraud_compromised_older_account` — 10-60 day account, sudden burst |
| `legit_payment_glitch` — old, scattered payment failures | `fraud_low_and_slow` — new account, only 2 failures, borderline amount anomaly |
| `legit_new_plus_glitch` — new account **+** old glitch stacked | `fraud_account_takeover` — established account, single large anomalous purchase, no other signal |

## Results

Two operating points, matching the engine's own recommendation tiers:

| Threshold | Precision | Recall | F1 | Accuracy | False Positive Rate |
|---|---|---|---|---|---|
| **FLAG** (score ≥ 30 → review or decline) | 0.521 | 0.817 | 0.636 | 0.813 | 0.188 |
| **DECLINE** (score ≥ 60 → outright decline) | 1.000 | 0.333 | 0.500 | 0.867 | 0.000 |

**What this actually means:**
- The engine **never wrongly auto-declines a legit customer** in this set (DECLINE precision = 1.000, 0 false positives at that tier) — the highest-cost mistake never happens.
- At the review tier, it catches **82% of fraud** but at the cost of flagging **19% of legit customers** for manual review — an honest precision/recall trade-off, not a free lunch.
- At the auto-decline tier alone, it only catches **33% of fraud** outright — most fraud is caught by *routing to review*, not by blocking automatically.

### Where it fails (the useful part)

- **`fraud_account_takeover`: 0/11 caught, 0% flagged.** An established account (60-400 days old, real order history) making one large anomalous purchase, with no other signal, sails through completely. This is a real, named blind spot: the engine currently has no way to catch account-takeover fraud on established accounts — it only reasons about newness, failures, and velocity, none of which fire here.
- **`legit_new_plus_glitch`: 45/45 flagged (100%), 0% declined.** A genuine new customer who also had 1-2 old, unrelated payment hiccups gets routed to manual review every time — two individually-weak signals (new_account +20, old failures +10) stack past the 30-point flag threshold. This is the main driver of the 18.8% false positive rate. The mitigating factor: none of these get auto-declined, so no legit sale is actually lost — just an $8 review cost per case.

## Cost analysis

Illustrative INR figures (assumptions documented in `evaluate_risk_engine.py`): review = ₹8/case, wrongly declining a legit customer = lost sale + ₹15 reputation cost, missed fraud = full transaction amount.

| | Baseline (no detector) | With `risk_engine.py` |
|---|---|---|
| Total cost on held-out set | ₹10,572.84 | ₹3,855.93 |
| **Net saved** | | **₹6,716.91** |

Cost breakdown with the detector in place:
- Fraud losses still missed (account-takeover cases that were ACCEPTed): ₹3,263.93
- Manual review costs (legit + fraud combined): ₹592.00
- Legit sales wrongly declined: **₹0.00**

## Honest conclusion

`risk_engine.py` is a real, working detector with a measurable, favorable
cost trade-off (63% cost reduction vs. no detector on this set) and zero
wrongful auto-declines. Its clearest limitation is **account-takeover
fraud on established accounts**, which it currently cannot detect at all —
a natural next signal to add (e.g. device/IP fingerprint change, shipping
address mismatch) rather than a flaw to hide.

Raw per-case predictions are in `held_out_test_set_results.csv` — every
single case, correct or not, for direct audit.
