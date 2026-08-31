"""
risk_engine.py
--------------
Deterministic risk scoring engine.

Risk Score Ranges:
    0-29   = LOW
    30-59  = MEDIUM
    60-100 = HIGH
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any
import logging

logger = logging.getLogger(__name__)


class RiskFactor:
    """Represents a single risk factor with evidence."""
    
    def __init__(
        self,
        factor_name: str,
        severity: str,
        score_contribution: int,
        evidence: str,
        explanation: str
    ):
        self.factor_name = factor_name
        self.severity = severity
        self.score_contribution = score_contribution
        self.evidence = evidence
        self.explanation = explanation
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor": self.factor_name,
            "severity": self.severity,
            "score": self.score_contribution,
            "evidence": self.evidence,
            "explanation": self.explanation,
        }


class RiskEngine:
    """Deterministic risk scoring engine."""
    
    # Configurable thresholds
    AMOUNT_ANOMALY_MULTIPLIER = 3.0
    ACCOUNT_AGE_THRESHOLD_DAYS = 7
    FAILED_ATTEMPTS_THRESHOLD = 3
    VELOCITY_SPIKE_THRESHOLD = 5
    
    # Score contributions
    SCORE_WEIGHTS = {
        "amount_anomaly": 25,
        "new_account": 20,
        "failed_attempts": 20,
        "velocity_spike": 15,
        "new_device": 10,
        "unusual_location": 10,
    }
    
    def __init__(self):
        self.risk_factors: List[RiskFactor] = []
    
    def analyze(
        self,
        transaction: Dict[str, Any],
        customer: Dict[str, Any],
        payment_history: List[Dict[str, Any]],
        order_history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Analyze a transaction and return detected risk factors."""
        self.risk_factors = []
        
        self._check_amount_anomaly(transaction, order_history)
        self._check_new_account(customer)
        self._check_failed_attempts(payment_history, transaction)
        self._check_velocity_spike(payment_history, transaction)
        
        return [factor.to_dict() for factor in self.risk_factors]
    
    def calculate_score(
        self,
        transaction: Dict[str, Any],
        customer: Dict[str, Any],
        payment_history: List[Dict[str, Any]],
        order_history: List[Dict[str, Any]]
    ) -> Tuple[int, str, List[Dict[str, Any]]]:
        """Calculate overall risk score (0-100)."""
        factors = self.analyze(transaction, customer, payment_history, order_history)
        
        total_score = sum(factor.score_contribution for factor in self.risk_factors)
        total_score = min(total_score, 100)
        
        if total_score < 30:
            risk_level = "LOW"
        elif total_score < 60:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"
        
        return total_score, risk_level, factors
    
    def _check_amount_anomaly(
        self,
        transaction: Dict[str, Any],
        order_history: List[Dict[str, Any]]
    ) -> None:
        """Check if transaction amount is unusually high."""
        if not order_history:
            return
        
        amounts = [order["amount"] for order in order_history]
        average_amount = sum(amounts) / len(amounts)
        current_amount = transaction["amount"]
        
        multiplier = current_amount / average_amount if average_amount > 0 else 0
        
        if multiplier > self.AMOUNT_ANOMALY_MULTIPLIER:
            factor = RiskFactor(
                factor_name="amount_anomaly",
                severity="HIGH",
                score_contribution=self.SCORE_WEIGHTS["amount_anomaly"],
                evidence=f"Current ${current_amount:.2f} vs historical average ${average_amount:.2f} ({multiplier:.1f}x)",
                explanation=f"Transaction amount is {multiplier:.1f}x the customer's typical purchase."
            )
            self.risk_factors.append(factor)
            logger.info(f"⚠️  Risk Factor: {factor.factor_name}")
    
    def _check_new_account(self, customer: Dict[str, Any]) -> None:
        """Check if account is very new."""
        created_at = customer.get("created_at")
        if not created_at:
            return
        
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        account_age = (datetime.now() - created_at).days
        
        if account_age < self.ACCOUNT_AGE_THRESHOLD_DAYS:
            factor = RiskFactor(
                factor_name="new_account",
                severity="MEDIUM",
                score_contribution=self.SCORE_WEIGHTS["new_account"],
                evidence=f"Account created {account_age} day(s) ago",
                explanation="Account is very new and has limited transaction history."
            )
            self.risk_factors.append(factor)
            logger.info(f"⚠️  Risk Factor: {factor.factor_name}")
    
    def _check_failed_attempts(
        self,
        payment_history: List[Dict[str, Any]],
        transaction: Dict[str, Any]
    ) -> None:
        """Check for multiple failed payment attempts."""
        if not payment_history:
            return
        
        recent_failures = [
            p for p in payment_history
            if p.get("status") == "failed"
        ]
        
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        failures_in_last_hour = [
            p for p in recent_failures
            if isinstance(p.get("timestamp"), datetime) and p["timestamp"] > one_hour_ago
        ]
        
        if len(failures_in_last_hour) >= self.FAILED_ATTEMPTS_THRESHOLD:
            factor = RiskFactor(
                factor_name="failed_attempts",
                severity="HIGH",
                score_contribution=self.SCORE_WEIGHTS["failed_attempts"],
                evidence=f"{len(failures_in_last_hour)} failed payment attempts in the last hour",
                explanation="Multiple failed payment attempts suggest potential issues."
            )
            self.risk_factors.append(factor)
            logger.info(f"⚠️  Risk Factor: {factor.factor_name}")
        elif len(recent_failures) >= 2:
            factor = RiskFactor(
                factor_name="failed_attempts",
                severity="MEDIUM",
                score_contribution=self.SCORE_WEIGHTS["failed_attempts"] // 2,
                evidence=f"{len(recent_failures)} failed payment attempts in recent history",
                explanation="Some recent payment failures detected."
            )
            self.risk_factors.append(factor)
            logger.info(f"⚠️  Risk Factor: {factor.factor_name}")
    
    def _check_velocity_spike(
        self,
        payment_history: List[Dict[str, Any]],
        transaction: Dict[str, Any]
    ) -> None:
        """Check for unusually high transaction frequency."""
        if not payment_history:
            return
        
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        
        recent_transactions = [
            p for p in payment_history
            if isinstance(p.get("timestamp"), datetime) and p["timestamp"] > one_hour_ago
        ]
        
        recent_count = len(recent_transactions) + 1
        
        if recent_count >= self.VELOCITY_SPIKE_THRESHOLD:
            factor = RiskFactor(
                factor_name="velocity_spike",
                severity="MEDIUM",
                score_contribution=self.SCORE_WEIGHTS["velocity_spike"],
                evidence=f"{recent_count} transactions in the last hour",
                explanation="Unusually high number of transactions in a short time period."
            )
            self.risk_factors.append(factor)
            logger.info(f"⚠️  Risk Factor: {factor.factor_name}")