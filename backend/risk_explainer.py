"""
risk_explainer.py
------------------
LLM layer (Google Gemini) that sits on top of the deterministic risk engine.

It does NOT decide the risk score — risk_engine.py already did that. Its job is to:
  1. Translate the score + risk factors into plain, non-technical language a
     merchant can act on.
  2. Let the merchant ask follow-up questions, answered by calling the same
     tools a human fraud analyst would use (customer profile, order history,
     payment history, risk signals) rather than guessing.

Uses the Gemini Interactions API (client.interactions.create) in STATEFUL mode:
Gemini keeps the actual conversation (including tool calls) server-side, keyed
by interaction id, and we just remember the latest id per transaction in
risk_database.py so the next merchant question continues the same thread.

Two entry points:
  explain_risk(transaction_id)              -> first, plain-language write-up
  chat_about_risk(transaction_id, question)  -> answer a follow-up question
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from google import genai

from risk_database import (
    get_transaction,
    get_risk_assessment,
    append_chat_message,
    get_last_interaction_id,
    set_last_interaction_id,
)
from risk_tools import (
    get_customer,
    get_customer_history,
    get_payment_history,
    analyze_risk_signals,
)

logger = logging.getLogger(__name__)

MODEL = "gemini-3.6-flash"
MAX_TOOL_ROUNDS = 6  # hard cap so a runaway tool loop can't hang a request

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_INSTRUCTION = """You are a payment-risk assistant explaining a transaction to a small \
business merchant who is NOT a data scientist or fraud analyst.

Rules you always follow:
- Speak in plain, everyday language. Never use jargon like "amount anomaly", \
"velocity spike", "risk score contribution", or raw statistics/math.
- Use short, concrete, real-world comparisons a shop owner would immediately get \
(for example: "this is like someone walking into your store for the first time and \
buying your most expensive item in cash").
- Ground every claim in real data. Call the tools available to you to check facts \
before stating them — never invent numbers, dates, or history.
- Keep the first explanation short: 3-5 sentences is usually enough. Follow-up \
answers should be direct and conversational, answering exactly what was asked.
- You explain risk. You never tell the merchant what decision to make ("you should \
accept/decline") — that call is always theirs.
- If something can't be answered from the available data, say so plainly instead of \
guessing.
"""

TOOLS = [
    {
        "type": "function",
        "name": "get_customer",
        "description": "Look up a customer's profile: name, email, account age, "
        "and whether they're a new or high-value customer.",
        "parameters": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
    {
        "type": "function",
        "name": "get_customer_history",
        "description": "Look up a customer's order history: total orders, total spent, "
        "average/min/max order value, and recent orders.",
        "parameters": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
    {
        "type": "function",
        "name": "get_payment_history",
        "description": "Look up a customer's payment attempt history: how many succeeded, "
        "how many failed, and recent failure counts.",
        "parameters": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer"}},
            "required": ["customer_id"],
        },
    },
    {
        "type": "function",
        "name": "analyze_risk_signals",
        "description": "Re-run the deterministic risk-signal detector for a transaction "
        "and get the raw list of factors it found, with evidence for each.",
        "parameters": {
            "type": "object",
            "properties": {"transaction_id": {"type": "string"}},
            "required": ["transaction_id"],
        },
    },
]

TOOL_IMPL = {
    "get_customer": lambda args: get_customer(args["customer_id"]),
    "get_customer_history": lambda args: get_customer_history(args["customer_id"]),
    "get_payment_history": lambda args: get_payment_history(args["customer_id"]),
    "analyze_risk_signals": lambda args: analyze_risk_signals(args["transaction_id"]),
}


def _transaction_context(transaction_id: str) -> str:
    """Build a compact fact block for the model to ground its explanation in."""
    transaction = get_transaction(transaction_id)
    assessment = get_risk_assessment(transaction_id)

    if not transaction or not assessment:
        raise ValueError(f"No transaction/assessment found for {transaction_id}")

    return json.dumps(
        {
            "transaction_id": transaction_id,
            "customer_id": transaction["customer_id"],
            "amount": transaction["amount"],
            "currency": transaction["currency"],
            "risk_score": assessment["risk_score"],
            "risk_level": assessment["risk_level"],
            "risk_factors": assessment["risk_factors"],
            "recommendation": assessment["recommendation"],
        },
        default=str,
    )


def _run_tool_loop(
    input_data: Any, previous_interaction_id: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    Run the Gemini function-calling loop (stateful mode) until it produces a
    final text answer. Returns (final_text, last_interaction_id).
    """
    for _ in range(MAX_TOOL_ROUNDS):
        interaction = client.interactions.create(
            model=MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
            input=input_data,
            tools=TOOLS,
            previous_interaction_id=previous_interaction_id,
        )

        function_call_steps = [s for s in interaction.steps if s.type == "function_call"]

        if not function_call_steps:
            return (interaction.output_text or "").strip(), interaction.id

        results: List[Dict[str, Any]] = []
        for fc in function_call_steps:
            impl = TOOL_IMPL.get(fc.name)
            try:
                result = (
                    impl(fc.arguments)
                    if impl
                    else {"success": False, "error": f"Unknown tool {fc.name}"}
                )
            except Exception as exc:  # keep the loop alive even if one tool call fails
                logger.exception("Tool %s failed", fc.name)
                result = {"success": False, "error": str(exc)}

            results.append(
                {
                    "type": "function_result",
                    "name": fc.name,
                    "call_id": fc.id,
                    "result": [{"type": "text", "text": json.dumps(result, default=str)}],
                }
            )

        previous_interaction_id = interaction.id
        input_data = results

    return "I wasn't able to finish looking into that — please try asking again.", previous_interaction_id


def explain_risk(transaction_id: str) -> str:
    """Produce the first, plain-language explanation for a transaction's risk assessment."""
    context = _transaction_context(transaction_id)

    prompt = (
        "Here is the completed risk analysis for a transaction:\n"
        f"{context}\n\n"
        "Explain to the merchant, in plain everyday language, why this transaction "
        "got this risk level. Use the tools if you need more detail before answering."
    )

    explanation, interaction_id = _run_tool_loop(prompt)

    if interaction_id:
        set_last_interaction_id(transaction_id, interaction_id)
    append_chat_message(transaction_id, "assistant", explanation)

    return explanation


def chat_about_risk(transaction_id: str, question: str) -> str:
    """Answer a merchant's follow-up question about a transaction's risk assessment."""
    append_chat_message(transaction_id, "user", question)

    previous_interaction_id = get_last_interaction_id(transaction_id)

    if previous_interaction_id:
        # Gemini already has the transaction context and prior turns server-side.
        prompt = question
    else:
        # Merchant jumped straight to chat without requesting the initial explanation —
        # seed this first turn with the same background facts.
        context = _transaction_context(transaction_id)
        prompt = (
            f"Background facts for this transaction:\n{context}\n\n"
            f"Merchant question: {question}"
        )

    reply, interaction_id = _run_tool_loop(prompt, previous_interaction_id=previous_interaction_id)

    if interaction_id:
        set_last_interaction_id(transaction_id, interaction_id)
    append_chat_message(transaction_id, "assistant", reply)

    return reply
