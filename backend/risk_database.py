"""
risk_database.py
----------------
In-memory storage for risk assessment data.

Data structures:
    CUSTOMERS      -> Customer profiles and history
    PAYMENT_ATTEMPTS -> Payment success/failure records
    TRANSACTIONS   -> Transaction records and status
    RISK_ASSESSMENTS -> Audit trail of risk analyses
    MERCHANT_DECISIONS -> Audit trail of merchant accept/decline decisions
"""

from datetime import datetime
from typing import Dict, List, Any

# Mock customer database
CUSTOMERS: Dict[int, Dict[str, Any]] = {
    1: {
        "customer_id": 1,
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "9876543210",
        "status": "active",
        "created_at": datetime(2024, 1, 1),  # 8 months old
        "order_history": [
            {"order_id": "ORD_001", "amount": 150.00, "date": datetime(2024, 8, 10)},
            {"order_id": "ORD_002", "amount": 120.00, "date": datetime(2024, 8, 15)},
            {"order_id": "ORD_003", "amount": 180.00, "date": datetime(2024, 8, 20)},
            {"order_id": "ORD_004", "amount": 160.00, "date": datetime(2024, 8, 22)},
            {"order_id": "ORD_005", "amount": 140.00, "date": datetime(2024, 8, 25)},
        ],
    },
    2: {
        "customer_id": 2,
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "9876543211",
        "status": "active",
        "created_at": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),  # Today - new account
        "order_history": [
            {"order_id": "ORD_006", "amount": 200.00, "date": datetime.now()},
        ],
    },
    3: {
        "customer_id": 3,
        "name": "Bob Johnson",
        "email": "bob@example.com",
        "phone": "9876543212",
        "status": "active",
        "created_at": datetime(2023, 6, 1),  # Very loyal - 14+ months
        "order_history": [
            {"order_id": "ORD_007", "amount": 250.00, "date": datetime(2024, 8, 1)},
            {"order_id": "ORD_008", "amount": 300.00, "date": datetime(2024, 8, 8)},
            {"order_id": "ORD_009", "amount": 275.00, "date": datetime(2024, 8, 15)},
            {"order_id": "ORD_010", "amount": 290.00, "date": datetime(2024, 8, 22)},
            {"order_id": "ORD_011", "amount": 310.00, "date": datetime(2024, 8, 25)},
            {"order_id": "ORD_012", "amount": 280.00, "date": datetime(2024, 8, 26)},
        ],
    },
    4: {
        # HIGH RISK demo persona: brand-new account, tiny first order, then a burst
        # of failed payment attempts in the last hour — reads like a stolen card
        # being tested repeatedly before a bigger purchase.
        "customer_id": 4,
        "name": "Alex Rivera",
        "email": "alex.rivera@example.com",
        "phone": "9876543213",
        "status": "active",
        "created_at": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),  # Today - new account
        "order_history": [
            {"order_id": "ORD_013", "amount": 18.00, "date": datetime.now()},
        ],
    },
    5: {
        # HIGH RISK demo persona: brand-new account, tiny first order, then a rapid
        # burst of mixed success/failed attempts — reads like automated card
        # testing (bot behavior) rather than one person retrying a purchase.
        "customer_id": 5,
        "name": "Priya Nair",
        "email": "priya.nair@example.com",
        "phone": "9876543214",
        "status": "active",
        "created_at": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),  # Today - new account
        "order_history": [
            {"order_id": "ORD_014", "amount": 22.00, "date": datetime.now()},
        ],
    },
}

# Payment attempts (success/failure history)
PAYMENT_ATTEMPTS: Dict[int, List[Dict[str, Any]]] = {
    1: [
        {"timestamp": datetime(2024, 8, 10, 10, 30), "status": "success", "amount": 150.00},
        {"timestamp": datetime(2024, 8, 15, 14, 20), "status": "success", "amount": 120.00},
        {"timestamp": datetime(2024, 8, 20, 9, 15), "status": "success", "amount": 180.00},
        {"timestamp": datetime(2024, 8, 22, 16, 45), "status": "success", "amount": 160.00},
        {"timestamp": datetime(2024, 8, 25, 11, 0), "status": "success", "amount": 140.00},
    ],
    2: [
        {"timestamp": datetime.now(), "status": "success", "amount": 200.00},
    ],
    3: [
        {"timestamp": datetime(2024, 8, 1, 11, 0), "status": "success", "amount": 250.00},
        {"timestamp": datetime(2024, 8, 8, 15, 30), "status": "success", "amount": 300.00},
        {"timestamp": datetime(2024, 8, 15, 13, 45), "status": "success", "amount": 275.00},
        {"timestamp": datetime(2024, 8, 22, 10, 20), "status": "success", "amount": 290.00},
        {"timestamp": datetime(2024, 8, 25, 14, 0), "status": "success", "amount": 310.00},
        {"timestamp": datetime(2024, 8, 26, 9, 30), "status": "success", "amount": 280.00},
    ],
    4: [
        # 5 failed attempts, all within the last hour — reads like a stolen card
        # being retried repeatedly.
        {"timestamp": datetime.now(), "status": "failed", "amount": 449.00},
        {"timestamp": datetime.now(), "status": "failed", "amount": 449.00},
        {"timestamp": datetime.now(), "status": "failed", "amount": 449.00},
        {"timestamp": datetime.now(), "status": "failed", "amount": 449.00},
        {"timestamp": datetime.now(), "status": "failed", "amount": 449.00},
    ],
    5: [
        # 7 attempts within the last hour, mixed success/failure at varying
        # amounts — reads like automated card testing rather than one retrying
        # customer.
        {"timestamp": datetime.now(), "status": "failed", "amount": 15.00},
        {"timestamp": datetime.now(), "status": "success", "amount": 8.00},
        {"timestamp": datetime.now(), "status": "failed", "amount": 22.00},
        {"timestamp": datetime.now(), "status": "success", "amount": 5.00},
        {"timestamp": datetime.now(), "status": "failed", "amount": 30.00},
        {"timestamp": datetime.now(), "status": "success", "amount": 12.00},
        {"timestamp": datetime.now(), "status": "success", "amount": 9.00},
    ],
}

# Active transactions
TRANSACTIONS: Dict[str, Dict[str, Any]] = {}

# Risk assessments audit trail
RISK_ASSESSMENTS: Dict[str, Dict[str, Any]] = {}

# Merchant decisions audit trail
MERCHANT_DECISIONS: Dict[str, Dict[str, Any]] = {}

# Merchant <-> AI chat threads, keyed by transaction_id.
# Each entry is a list of {"role": "user"|"assistant", "content": str} turns.
# This is the human-readable log shown in the UI.
CHAT_SESSIONS: Dict[str, List[Dict[str, str]]] = {}

# The Gemini Interactions API is stateful: it keeps the real conversation
# (including tool calls and thought signatures) server-side, keyed by
# interaction id. We just need to remember the last id per transaction to
# continue the thread.
LAST_INTERACTION_ID: Dict[str, str] = {}


def create_transaction(
    transaction_id: str,
    customer_id: int,
    amount: float,
    currency: str = "INR"
) -> Dict[str, Any]:
    """Create a new transaction record."""
    transaction = {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "amount": amount,
        "currency": currency,
        "status": "pending_risk_analysis",
        "created_at": datetime.now().isoformat(),
        "risk_assessment_at": None,
        "merchant_decision_at": None,
    }
    TRANSACTIONS[transaction_id] = transaction
    return transaction


def get_transaction(transaction_id: str) -> Dict[str, Any] | None:
    """Retrieve a transaction by ID."""
    return TRANSACTIONS.get(transaction_id)


def update_transaction_status(transaction_id: str, status: str) -> None:
    """Update transaction status."""
    if transaction_id in TRANSACTIONS:
        TRANSACTIONS[transaction_id]["status"] = status
        TRANSACTIONS[transaction_id]["updated_at"] = datetime.now().isoformat()


def store_risk_assessment(
    transaction_id: str,
    risk_score: int,
    risk_level: str,
    risk_factors: List[Dict],
    ai_explanation: str,
    recommendation: str
) -> None:
    """Store risk assessment results."""
    RISK_ASSESSMENTS[transaction_id] = {
        "transaction_id": transaction_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "ai_explanation": ai_explanation,
        "recommendation": recommendation,
        "assessed_at": datetime.now().isoformat(),
    }
    update_transaction_status(transaction_id, "risk_assessment_complete")


def get_risk_assessment(transaction_id: str) -> Dict[str, Any] | None:
    """Retrieve risk assessment for a transaction."""
    return RISK_ASSESSMENTS.get(transaction_id)


def store_merchant_decision(
    transaction_id: str,
    decision: str,
    reason: str = ""
) -> None:
    """Store merchant's accept/decline decision."""
    MERCHANT_DECISIONS[transaction_id] = {
        "transaction_id": transaction_id,
        "decision": decision,
        "reason": reason,
        "decided_at": datetime.now().isoformat(),
    }
    update_transaction_status(transaction_id, f"merchant_{decision.lower()}")


def get_merchant_decision(transaction_id: str) -> Dict[str, Any] | None:
    """Retrieve merchant decision for a transaction."""
    return MERCHANT_DECISIONS.get(transaction_id)


def set_risk_assessment_explanation(transaction_id: str, explanation: str) -> None:
    """Patch in the plain-language explanation once the LLM has produced it."""
    if transaction_id in RISK_ASSESSMENTS:
        RISK_ASSESSMENTS[transaction_id]["ai_explanation"] = explanation


def get_chat_history(transaction_id: str) -> List[Dict[str, str]]:
    """Retrieve the merchant's Q&A history about a transaction's risk assessment."""
    return CHAT_SESSIONS.get(transaction_id, [])


def append_chat_message(transaction_id: str, role: str, content: str) -> None:
    """Append one turn (merchant question or AI reply) to a transaction's chat history."""
    CHAT_SESSIONS.setdefault(transaction_id, []).append({"role": role, "content": content})


def get_last_interaction_id(transaction_id: str) -> str | None:
    """Retrieve the Gemini interaction id to continue this transaction's thread, if any."""
    return LAST_INTERACTION_ID.get(transaction_id)


def set_last_interaction_id(transaction_id: str, interaction_id: str) -> None:
    """Remember the latest Gemini interaction id so the next question continues the thread."""
    LAST_INTERACTION_ID[transaction_id] = interaction_id