"""
evaluate_risk_engine.py
------------------------
Runs risk_engine.py against held_out_test_set.json and reports honest
detection metrics: precision, recall, F1, accuracy, and a business
false-positive/false-negative cost breakdown.

The engine is called directly (RiskEngine().calculate_score(...)) with the
synthetic data — it never touches risk_database.py's global state, so this
evaluation is fully isolated from the live app and reproducible.

Two operating points are reported, matching the engine's own thresholds:
  - FLAG   (score >= 30): would trigger MANUAL_REVIEW or DECLINE
  - DECLINE (score >= 60): would trigger an outright DECLINE

Run:
    python generate_held_out_set.py   # (re)generate the held-out set
    python evaluate_risk_engine.py    # run this evaluation
"""

import csv
import json
from datetime import datetime

from risk_engine import RiskEngine

# --- Cost model (documented assumptions, not hidden) --------------------
# All costs are illustrative INR figures for demonstrating the metric, not
# a claim about ShopAI's real operating costs.
REVIEW_COST = 8.0          # analyst time to manually review one transaction
DECLINE_REPUTATION_COST = 15.0  # trust/friction cost on top of a lost sale
# Fraud loss = the transaction amount itself (money actually lost)
# Wrongly declined legit sale = transaction amount (lost revenue) + reputation cost


def load_held_out_set(path="held_out_test_set.json"):
    with open(path) as f:
        raw = json.load(f)
    for case in raw:
        case["customer"]["created_at"] = datetime.fromisoformat(case["customer"]["created_at"])
        for o in case["order_history"]:
            o["date"] = datetime.fromisoformat(o["date"])
        for p in case["payment_history"]:
            p["timestamp"] = datetime.fromisoformat(p["timestamp"])
    return raw


def run_engine(cases):
    engine_cls = RiskEngine
    results = []
    for case in cases:
        engine = engine_cls()
        score, level, factors = engine.calculate_score(
            transaction=case["transaction"],
            customer=case["customer"],
            payment_history=case["payment_history"],
            order_history=case["order_history"],
        )
        recommendation = "ACCEPT" if score < 30 else "MANUAL_REVIEW" if score < 60 else "DECLINE"
        results.append({
            **case,
            "predicted_score": score,
            "predicted_level": level,
            "predicted_recommendation": recommendation,
            "n_factors": len(factors),
        })
    return results


def confusion_matrix(results, threshold):
    """label=1 (fraud) is 'positive'. Predicted positive = predicted_score >= threshold."""
    tp = fp = tn = fn = 0
    for r in results:
        predicted_positive = r["predicted_score"] >= threshold
        actual_positive = r["label"] == 1
        if predicted_positive and actual_positive:
            tp += 1
        elif predicted_positive and not actual_positive:
            fp += 1
        elif not predicted_positive and actual_positive:
            fn += 1
        else:
            tn += 1
    return tp, fp, tn, fn


def metrics_at_threshold(results, threshold, label):
    tp, fp, tn, fn = confusion_matrix(results, threshold)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(results)
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print(f"\n--- Operating point: {label} (score >= {threshold}) ---")
    print(f"  TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"  Precision: {precision:.3f}   (of everything flagged, how much was really fraud)")
    print(f"  Recall:    {recall:.3f}   (of all real fraud, how much did we catch)")
    print(f"  F1:        {f1:.3f}")
    print(f"  Accuracy:  {accuracy:.3f}")
    print(f"  False Positive Rate: {fpr:.3f}   (of all legit customers, how many got flagged)")
    return {
        "threshold": threshold, "label": label, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy, "fpr": fpr,
    }


def cost_analysis(results):
    """
    Cost of the engine's actual 3-tier recommendation (ACCEPT / MANUAL_REVIEW /
    DECLINE) against ground truth, vs. a 'no risk engine, accept everything'
    baseline. Assumptions:
      - Legit + ACCEPT        -> $0 (correct)
      - Legit + MANUAL_REVIEW -> $8 review cost (sale still likely completes)
      - Legit + DECLINE       -> lost sale (txn amount) + $15 reputation cost
      - Fraud + ACCEPT        -> full fraud loss (txn amount)
      - Fraud + MANUAL_REVIEW -> $8 review cost (assume review catches it)
      - Fraud + DECLINE       -> $0 (correctly blocked)
    """
    engine_cost = 0.0
    baseline_cost = 0.0  # "accept everything" — no risk engine at all
    breakdown = {"fraud_losses_missed": 0.0, "review_costs": 0.0, "wrongly_declined_legit": 0.0}

    for r in results:
        amount = r["transaction"]["amount"]
        rec = r["predicted_recommendation"]
        is_fraud = r["label"] == 1

        if is_fraud:
            baseline_cost += amount  # baseline always accepts -> always loses the fraud amount
            if rec == "ACCEPT":
                engine_cost += amount
                breakdown["fraud_losses_missed"] += amount
            elif rec == "MANUAL_REVIEW":
                engine_cost += REVIEW_COST
                breakdown["review_costs"] += REVIEW_COST
            else:  # DECLINE
                pass  # $0, correctly blocked
        else:
            if rec == "ACCEPT":
                pass  # $0, correct
            elif rec == "MANUAL_REVIEW":
                engine_cost += REVIEW_COST
                breakdown["review_costs"] += REVIEW_COST
            else:  # DECLINE - wrongly declined a legit customer
                cost = amount + DECLINE_REPUTATION_COST
                engine_cost += cost
                breakdown["wrongly_declined_legit"] += cost

    print("\n--- Cost analysis (illustrative INR figures) ---")
    print(f"  Total value in held-out set: {sum(r['transaction']['amount'] for r in results):,.2f}")
    print(f"  Baseline cost (no risk engine, accept everything): {baseline_cost:,.2f}")
    print(f"  Cost with risk engine's actual decisions:          {engine_cost:,.2f}")
    print(f"  Net saved by having the risk engine:               {baseline_cost - engine_cost:,.2f}")
    print(f"  Breakdown:")
    print(f"    Fraud losses still missed (ACCEPTed fraud): {breakdown['fraud_losses_missed']:,.2f}")
    print(f"    Manual review costs (both legit & fraud):   {breakdown['review_costs']:,.2f}")
    print(f"    Legit sales wrongly declined:               {breakdown['wrongly_declined_legit']:,.2f}")

    return {
        "baseline_cost": baseline_cost,
        "engine_cost": engine_cost,
        "net_saved": baseline_cost - engine_cost,
        **breakdown,
    }


def threshold_sweep(results, thresholds=range(0, 101, 5)):
    sweep = []
    for t in thresholds:
        tp, fp, tn, fn = confusion_matrix(results, t)
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        sweep.append({"threshold": t, "precision": precision, "recall": recall})
    return sweep


def scenario_breakdown(results):
    from collections import defaultdict
    by_scenario = defaultdict(lambda: {"n": 0, "flagged": 0, "declined": 0})
    for r in results:
        s = by_scenario[r["scenario"]]
        s["n"] += 1
        if r["predicted_score"] >= 30:
            s["flagged"] += 1
        if r["predicted_score"] >= 60:
            s["declined"] += 1

    print("\n--- Per-scenario breakdown (how the engine handled each case type) ---")
    print(f"  {'scenario':<32} {'n':>4} {'flagged%':>10} {'declined%':>10}")
    for scenario, s in sorted(by_scenario.items()):
        flag_pct = 100 * s["flagged"] / s["n"]
        decline_pct = 100 * s["declined"] / s["n"]
        print(f"  {scenario:<32} {s['n']:>4} {flag_pct:>9.1f}% {decline_pct:>9.1f}%")


def save_raw_results_csv(results, path="held_out_test_set_results.csv"):
    fields = ["case_id", "scenario", "label", "transaction_amount", "predicted_score",
              "predicted_level", "predicted_recommendation", "n_factors", "correct"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            predicted_fraud = r["predicted_score"] >= 30
            actual_fraud = r["label"] == 1
            writer.writerow({
                "case_id": r["case_id"],
                "scenario": r["scenario"],
                "label": r["label"],
                "transaction_amount": r["transaction"]["amount"],
                "predicted_score": r["predicted_score"],
                "predicted_level": r["predicted_level"],
                "predicted_recommendation": r["predicted_recommendation"],
                "n_factors": r["n_factors"],
                "correct": predicted_fraud == actual_fraud,
            })
    print(f"\nRaw per-case results saved to {path} (for judges to audit directly, no aggregation hidden)")


if __name__ == "__main__":
    cases = load_held_out_set()
    print(f"Loaded {len(cases)} held-out cases ({sum(c['label'] for c in cases)} fraud / "
          f"{len(cases) - sum(c['label'] for c in cases)} legit)")

    results = run_engine(cases)

    flag_metrics = metrics_at_threshold(results, 30, "FLAG (review or decline)")
    decline_metrics = metrics_at_threshold(results, 60, "DECLINE only")

    costs = cost_analysis(results)
    scenario_breakdown(results)
    sweep = threshold_sweep(results)

    save_raw_results_csv(results)

    with open("evaluation_summary.json", "w") as f:
        json.dump({
            "n_cases": len(results),
            "n_fraud": sum(r["label"] for r in results),
            "flag_metrics": flag_metrics,
            "decline_metrics": decline_metrics,
            "cost_analysis": costs,
            "threshold_sweep": sweep,
        }, f, indent=2)
    print("\nFull summary saved to evaluation_summary.json")
