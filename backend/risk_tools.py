"""
risk_tools.py
-------------
Tools used by the AI Agent to investigate transactions.
"""

from risk_database import (
    CUSTOMERS,
    PAYMENT_ATTEMPTS,
    TRANSACTIONS,
    get_transaction,
)
from risk_engine import RiskEngine
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


def get_customer(customer_id: int) -> Dict[str, Any]:
    """Retrieve customer profile and account details."""
    if customer_id not in CUSTOMERS:
        return {
            "success": False,
            "error": f"Customer {customer_id} not found"
        }
    
    customer = CUSTOMERS[customer_id]
    
    created_at = customer.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    
    account_age_days = (datetime.now() - created_at).days
    
    return {
        "success": True,
        "customer_id": customer_id,
        "name": customer.get("name"),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "status": customer.get("status", "active"),
        "account_age_days": account_age_days,
        "account_created": created_at.isoformat() if created_at else None,
        "is_new_customer": account_age_days < 7,
        "is_high_value_customer": len(customer.get("order_history", [])) > 10,
    }


def get_customer_history(customer_id: int) -> Dict[str, Any]:
    """Retrieve customer's order history and purchasing patterns."""
    if customer_id not in CUSTOMERS:
        return {
            "success": False,
            "error": f"Customer {customer_id} not found"
        }
    
    customer = CUSTOMERS[customer_id]
    order_history = customer.get("order_history", [])
    
    if not order_history:
        return {
            "success": True,
            "customer_id": customer_id,
            "total_orders": 0,
            "total_spent": 0.0,
            "average_order_value": 0.0,
            "min_order": 0.0,
            "max_order": 0.0,
            "orders": []
        }
    
    amounts = [order["amount"] for order in order_history]
    total_spent = sum(amounts)
    average_order = total_spent / len(order_history)
    
    return {
        "success": True,
        "customer_id": customer_id,
        "total_orders": len(order_history),
        "total_spent": round(total_spent, 2),
        "average_order_value": round(average_order, 2),
        "min_order": round(min(amounts), 2),
        "max_order": round(max(amounts), 2),
        "recent_orders": order_history[-5:],
    }


def get_payment_history(customer_id: int) -> Dict[str, Any]:
    """Retrieve customer's payment attempt records (success/failure)."""
    if customer_id not in PAYMENT_ATTEMPTS:
        return {
            "success": True,
            "customer_id": customer_id,
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "failure_rate_percent": 0.0,
            "failed_in_last_hour": 0,
            "failed_in_last_24h": 0,
        }
    
    attempts = PAYMENT_ATTEMPTS[customer_id]
    successful = sum(1 for a in attempts if a.get("status") == "success")
    failed = sum(1 for a in attempts if a.get("status") == "failed")
    
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)
    
    failures_last_hour = [
        a for a in attempts
        if a.get("status") == "failed" and
        isinstance(a.get("timestamp"), datetime) and
        a["timestamp"] > one_hour_ago
    ]
    
    failures_last_24h = [
        a for a in attempts
        if a.get("status") == "failed" and
        isinstance(a.get("timestamp"), datetime) and
        a["timestamp"] > one_day_ago
    ]
    
    return {
        "success": True,
        "customer_id": customer_id,
        "total_attempts": len(attempts),
        "successful": successful,
        "failed": failed,
        "failure_rate_percent": round(failed / len(attempts) * 100, 1) if attempts else 0.0,
        "failed_in_last_hour": len(failures_last_hour),
        "failed_in_last_24h": len(failures_last_24h),
        "recent_attempts": attempts[-5:],
    }


def analyze_risk_signals(transaction_id: str) -> Dict[str, Any]:
    """Analyze transaction for specific risk signals."""
    transaction = get_transaction(transaction_id)
    if not transaction:
        return {
            "success": False,
            "error": f"Transaction {transaction_id} not found"
        }
    
    customer_id = transaction.get("customer_id")
    customer = CUSTOMERS.get(customer_id)
    
    if not customer:
        return {
            "success": False,
            "error": f"Customer {customer_id} not found"
        }
    
    payment_history = PAYMENT_ATTEMPTS.get(customer_id, [])
    order_history = customer.get("order_history", [])
    
    engine = RiskEngine()
    risk_factors = engine.analyze(
        transaction=transaction,
        customer=customer,
        payment_history=payment_history,
        order_history=order_history
    )
    
    logger.info(f"🔍 Risk Analysis: Found {len(risk_factors)} risk factors for transaction {transaction_id}")
    
    return {
        "success": True,
        "transaction_id": transaction_id,
        "risk_factors": risk_factors,
        "total_factors": len(risk_factors),
    }


def calculate_risk_score(transaction_id: str) -> Dict[str, Any]:
    """Calculate the final risk score (0-100) for a transaction."""
    transaction = get_transaction(transaction_id)
    if not transaction:
        return {
            "success": False,
            "error": f"Transaction {transaction_id} not found"
        }
    
    customer_id = transaction.get("customer_id")
    customer = CUSTOMERS.get(customer_id)
    
    if not customer:
        return {
            "success": False,
            "error": f"Customer {customer_id} not found"
        }
    
    payment_history = PAYMENT_ATTEMPTS.get(customer_id, [])
    order_history = customer.get("order_history", [])
    
    engine = RiskEngine()
    risk_score, risk_level, risk_factors = engine.calculate_score(
        transaction=transaction,
        customer=customer,
        payment_history=payment_history,
        order_history=order_history
    )
    
    if risk_score < 30:
        recommendation = "ACCEPT"
    elif risk_score < 60:
        recommendation = "MANUAL_REVIEW"
    else:
        recommendation = "DECLINE"
    
    logger.info(f"📊 Risk Score: {risk_score}/100 ({risk_level}) for transaction {transaction_id}")
    
    return {
        "success": True,
        "transaction_id": transaction_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "recommendation": recommendation,
    }