"""
generate_held_out_set.py
-------------------------
Builds a synthetic, labeled, held-out test set for evaluating risk_engine.py.

Design principles (why this is a fair test, not a self-fulfilling one):
  - Ground-truth labels (is_fraud) are assigned by the SCENARIO the case was
    generated from, never by running the engine. The engine never sees the
    label and never influences it. This avoids the circular trap of
    "labeling fraud as whatever the engine flags."
  - It's not just easy cases. Roughly a third of the legit cases are
    deliberately built to *look* suspicious by one signal (a big one-time
    purchase, a brand-new but genuine customer, a payment glitch) — these
    are "hard negatives" that stress-test false positives. Roughly a third
    of the fraud cases are deliberately built to be missing 1-2 of the
    textbook fraud signals — "hard positives" that stress-test recall.
  - Every case is generated with randomization (seeded for reproducibility),
    not hand-picked, so results can't be cherry-picked.

Run this to regenerate the held-out set (same seed = same set every time):
    python generate_held_out_set.py
"""

import json
import random
from datetime import datetime, timedelta

random.seed(42)  # reproducible — same held-out set every run

NOW = datetime.now()


def _order(order_id, amount, days_ago):
    return {"order_id": order_id, "amount": round(amount, 2), "date": NOW - timedelta(days=days_ago)}


def _payment(status, amount, minutes_ago=None, days_ago=None):
    if minutes_ago is not None:
        ts = NOW - timedelta(minutes=minutes_ago)
    else:
        ts = NOW - timedelta(days=days_ago)
    return {"timestamp": ts, "status": status, "amount": round(amount, 2)}


def _case(case_id, scenario, label, created_days_ago_or_hours, is_hours, order_history, payment_history, txn_amount):
    created_at = NOW - (timedelta(hours=created_days_ago_or_hours) if is_hours else timedelta(days=created_days_ago_or_hours))
    return {
        "case_id": case_id,
        "scenario": scenario,
        "label": label,  # 1 = fraud, 0 = legit — GROUND TRUTH, independent of the engine
        "customer": {"created_at": created_at},
        "order_history": order_history,
        "payment_history": payment_history,
        "transaction": {"amount": round(txn_amount, 2), "currency": "INR"},
    }


# =========================================================================
# LEGIT scenarios (label = 0)
# =========================================================================

def gen_legit_established(i):
    """Long-standing customer, normal repeat purchase. The easy, common case."""
    age_days = random.randint(60, 900)
    n_orders = random.randint(3, 20)
    base = random.uniform(40, 200)
    orders = [_order(f"L1_{i}_{j}", base * random.uniform(0.7, 1.3), age_days - j * 7) for j in range(n_orders)]
    payments = [_payment("success", o["amount"], days_ago=age_days - j * 7) for j, o in enumerate(orders)]
    txn = base * random.uniform(0.8, 1.5)
    return _case(f"L1_{i}", "legit_established", 0, age_days, False, orders, payments, txn)


def gen_legit_new_normal(i):
    """Brand-new account, first purchase, but nothing else suspicious — a real new customer.
    Hard negative: tests whether the engine over-penalizes newness alone."""
    age_hours = random.uniform(0, 20)
    txn = random.uniform(20, 90)
    return _case(f"L2_{i}", "legit_new_normal", 0, age_hours, True, [], [], txn)


def gen_legit_big_onetime(i):
    """Established customer, usually buys cheap items, makes one unusually large purchase
    (e.g. a gift). Hard negative: directly stress-tests the amount-anomaly signal."""
    age_days = random.randint(90, 600)
    n_orders = random.randint(2, 8)
    base = random.uniform(20, 60)
    orders = [_order(f"L3_{i}_{j}", base * random.uniform(0.8, 1.2), age_days - j * 10) for j in range(n_orders)]
    payments = [_payment("success", o["amount"], days_ago=age_days - j * 10) for j, o in enumerate(orders)]
    txn = base * random.uniform(4, 8)  # >3x their normal average, on purpose
    return _case(f"L3_{i}", "legit_big_onetime", 0, age_days, False, orders, payments, txn)


def gen_legit_payment_glitch(i):
    """Legit, established customer who had 1-2 failed payments scattered over time
    (bank/network hiccups), not a fraud pattern. Hard negative for failed_attempts signal."""
    age_days = random.randint(30, 400)
    n_orders = random.randint(1, 6)
    base = random.uniform(50, 150)
    orders = [_order(f"L4_{i}_{j}", base * random.uniform(0.8, 1.2), age_days - j * 15) for j in range(n_orders)]
    payments = [_payment("success", o["amount"], days_ago=age_days - j * 15) for j, o in enumerate(orders)]
    # 1-2 old failures, NOT clustered in the last hour
    for _ in range(random.randint(1, 2)):
        payments.append(_payment("failed", base * random.uniform(0.8, 1.2), days_ago=random.randint(10, age_days)))
    txn = base * random.uniform(0.8, 1.3)
    return _case(f"L4_{i}", "legit_payment_glitch", 0, age_days, False, orders, payments, txn)


def gen_legit_new_plus_glitch(i):
    """Two individually-weak signals stacking to cross the flag threshold on a genuinely
    legit customer: brand-new account (+20) that also had 1-2 old scattered payment
    hiccups (+10). Neither alone would flag; together they might. This is the real
    stress test for false positives — most single-signal 'hard negatives' don't
    actually cross the threshold, so this is where a genuine FP should show up."""
    age_hours = random.uniform(0, 20)
    txn = random.uniform(25, 90)
    payments = [_payment("failed", random.uniform(15, 40), minutes_ago=random.randint(120, 600)) for _ in range(2)]
    return _case(f"L5_{i}", "legit_new_plus_glitch", 0, age_hours, True, [], payments, txn)


LEGIT_GENERATORS = [
    (gen_legit_established, 0.40),
    (gen_legit_new_normal, 0.15),
    (gen_legit_big_onetime, 0.15),
    (gen_legit_payment_glitch, 0.15),
    (gen_legit_new_plus_glitch, 0.15),
]


# =========================================================================
# FRAUD scenarios (label = 1)
# =========================================================================

def gen_fraud_textbook(i):
    """Classic pattern: brand-new account, tiny first order, burst of failed attempts,
    then a big purchase attempt. The easy, obvious case."""
    age_hours = random.uniform(0, 5)
    small = random.uniform(10, 30)
    orders = [_order(f"F1_{i}", small, age_hours / 24)]
    n_fail = random.randint(3, 6)
    payments = [
        _payment(random.choice(["failed", "failed", "failed", "success"]), random.uniform(10, 50), minutes_ago=random.randint(0, 50))
        for _ in range(n_fail)
    ]
    txn = small * random.uniform(4, 15)
    return _case(f"F1_{i}", "fraud_textbook", 1, age_hours, True, orders, payments, txn)


def gen_fraud_evasive_no_retries(i):
    """Harder case: new account + big first purchase, but the fraudster's card worked on the
    first try — no failed attempts at all. Tests whether the engine catches fraud from the
    amount-anomaly + new-account combo alone, without a failure signal to lean on."""
    age_hours = random.uniform(0, 10)
    small = random.uniform(10, 25)
    orders = [_order(f"F2_{i}", small, age_hours / 24)]
    txn = small * random.uniform(4, 10)
    return _case(f"F2_{i}", "fraud_evasive_no_retries", 1, age_hours, True, orders, [], txn)


def gen_fraud_compromised_older_account(i):
    """Account isn't brand-new (10-60 days old, past the 7-day 'new account' threshold) but
    has been compromised: sudden burst of failed/velocity activity. Tests whether the engine
    over-relies on account age instead of behavior."""
    age_days = random.randint(10, 60)
    orders = [_order(f"F3_{i}", random.uniform(30, 80), age_days - 5)]
    n_fail = random.randint(4, 7)
    payments = [
        _payment(random.choice(["failed", "failed", "success"]), random.uniform(20, 60), minutes_ago=random.randint(0, 55))
        for _ in range(n_fail)
    ]
    txn = random.uniform(150, 400)
    return _case(f"F3_{i}", "fraud_compromised_older_account", 1, age_days, False, orders, payments, txn)


def gen_fraud_low_and_slow(i):
    """Evasive: new account, moderate (not extreme) amount anomaly, only 2 failures — deliberately
    tuned just under the HIGH-severity failed_attempts threshold (3) to test recall at the edges."""
    age_hours = random.uniform(0, 15)
    small = random.uniform(15, 35)
    orders = [_order(f"F4_{i}", small, age_hours / 24)]
    payments = [_payment("failed", random.uniform(15, 35), minutes_ago=random.randint(0, 55)) for _ in range(2)]
    txn = small * random.uniform(3.2, 4.5)  # just over the 3x anomaly threshold
    return _case(f"F4_{i}", "fraud_low_and_slow", 1, age_hours, True, orders, payments, txn)


def gen_fraud_account_takeover(i):
    """Sophisticated evasion: an ESTABLISHED account (not new — takes new_account off the
    table entirely) that has genuinely been taken over. The only signal available is
    amount anomaly — a normal-history account suddenly making a huge purchase. No new
    account flag, no failed attempts, no velocity spike. This is a deliberate stress
    test of whether the engine can catch account-takeover fraud on old accounts — a
    real, named limitation if it can't."""
    age_days = random.randint(60, 400)
    n_orders = random.randint(3, 10)
    base = random.uniform(30, 70)
    orders = [_order(f"F5_{i}_{j}", base * random.uniform(0.8, 1.2), age_days - j * 12) for j in range(n_orders)]
    payments = [_payment("success", o["amount"], days_ago=age_days - j * 12) for j, o in enumerate(orders)]
    txn = base * random.uniform(4, 9)  # the takeover: one big anomalous purchase, nothing else
    return _case(f"F5_{i}", "fraud_account_takeover", 1, age_days, False, orders, payments, txn)


FRAUD_GENERATORS = [
    (gen_fraud_textbook, 0.30),
    (gen_fraud_evasive_no_retries, 0.20),
    (gen_fraud_compromised_older_account, 0.15),
    (gen_fraud_low_and_slow, 0.15),
    (gen_fraud_account_takeover, 0.20),
]


def _sample_generator(weighted_generators):
    generators, weights = zip(*weighted_generators)
    return random.choices(generators, weights=weights, k=1)[0]


def generate_held_out_set(n_total=300, fraud_rate=0.20):
    """
    Generate the held-out set. fraud_rate=0.20 is intentionally higher than
    real-world fraud incidence (real rates are often <1%) so the test set has
    enough positive examples for recall to be statistically meaningful. This
    is a standard practice for evaluation sets and is reported explicitly,
    not hidden.
    """
    n_fraud = int(n_total * fraud_rate)
    n_legit = n_total - n_fraud

    cases = []
    for i in range(n_legit):
        cases.append(_sample_generator(LEGIT_GENERATORS)(i))
    for i in range(n_fraud):
        cases.append(_sample_generator(FRAUD_GENERATORS)(i))

    random.shuffle(cases)
    return cases


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError


if __name__ == "__main__":
    cases = generate_held_out_set()
    with open("held_out_test_set.json", "w") as f:
        json.dump(cases, f, default=_json_default, indent=2)

    n_fraud = sum(c["label"] for c in cases)
    print(f"Generated {len(cases)} cases ({n_fraud} fraud / {len(cases) - n_fraud} legit)")
    print("Saved to held_out_test_set.json")
