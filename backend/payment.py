"""
payment.py
----------
Razorpay integration for ShopAI, via Razorpay's official remote MCP server
(https://mcp.razorpay.com/mcp) instead of the razorpay Python SDK.

Order/payment/refund actions go through MCP tool calls, so this module is a
thin translator between our FastAPI routes and Razorpay's own managed tool
surface. Signature verification stays local — it's pure HMAC math, not a
Razorpay API call, so there's no MCP tool for it and nothing to gain by
routing it through MCP.
"""

import os
import json
import logging
import hashlib
import hmac
import base64
from datetime import datetime
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

logger = logging.getLogger(__name__)

# =========================================================================
# Razorpay Configuration
# =========================================================================

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_CURRENCY = os.getenv("RAZORPAY_CURRENCY", "USD")
RAZORPAY_MCP_URL = os.getenv("RAZORPAY_MCP_URL", "https://mcp.razorpay.com/mcp")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    logger.warning(
        "⚠️  Razorpay credentials not set in .env file. "
        "Payment creation will fail. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET."
    )

# Razorpay's REMOTE MCP server authenticates via a single "merchant token":
# an Authorization: Basic <base64(key_id:key_secret)> header. This differs
# from their LOCAL/Docker MCP server, which uses plain RAZORPAY_KEY_ID /
# RAZORPAY_KEY_SECRET environment variables instead — that scheme does NOT
# work against the remote endpoint we're calling here.
_merchant_token = (
    base64.b64encode(f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode()).decode()
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET
    else ""
)
_MCP_HEADERS = {
    "Authorization": f"Basic {_merchant_token}",
}


async def _call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Open a connection to Razorpay's remote MCP server, call one tool, and
    return its parsed JSON result.

    A fresh connection per call keeps this simple and safe for a
    request-scoped FastAPI handler. If this becomes a hot path, switch to a
    long-lived session managed at app startup instead.
    """
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise Exception(
            "Razorpay credentials not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env"
        )

    http_client = httpx2.AsyncClient(headers=_MCP_HEADERS)

    async with streamable_http_client(RAZORPAY_MCP_URL, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    text = "".join(
        getattr(block, "text", "") for block in result.content if getattr(block, "text", None)
    )

    if result.is_error:
        raise Exception(f"Razorpay MCP tool '{tool_name}' failed: {text or 'unknown error'}")

    # Prefer the SDK's already-parsed structured result when the server provides
    # one; fall back to parsing the text content block if not.
    if result.structured_content is not None:
        return result.structured_content

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"raw": text}


# =========================================================================
# Order Creation
# =========================================================================

async def create_order(amount: float, currency: str = "USD", receipt: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a Razorpay order via the Razorpay MCP server's `create_order` tool.

    Args:
        amount: Order amount in rupees (converted to paise for Razorpay)
        currency: Currency code (default: USD)
        receipt: Optional receipt ID for tracking

    Returns:
        Order details dict with id, amount, currency

    Raises:
        Exception: If order creation fails
    """
    try:
        # Razorpay expects amount in paise (smallest unit): 1 rupee = 100 paise
        amount_in_paise = int(amount * 100)

        if not receipt:
            receipt = f"order_{datetime.now().timestamp()}"

        order = await _call_tool(
            "create_order",
            {
                "amount": amount_in_paise,
                "currency": currency,
                "receipt": receipt,
            },
        )

        logger.info(f"✅ Order created via MCP: {order.get('id')} for ₹{amount}")

        return {
            "id": order["id"],
            "amount": amount_in_paise,  # Keep in paise for Razorpay Checkout
            "amount_display": amount,  # For display purposes
            "currency": currency,
            "receipt": receipt,
            "status": order.get("status"),
            "created_at": order.get("created_at"),
        }

    except Exception as e:
        logger.error(f"❌ Error creating Razorpay order via MCP: {str(e)}")
        raise Exception(f"Failed to create payment order: {str(e)}")


# =========================================================================
# Payment Verification (local — unchanged)
# =========================================================================

def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verify the Razorpay payment signature.

    This is CRITICAL for security. Never trust the frontend alone.
    Always verify the signature on the backend using your API secret.

    This stays a local HMAC check rather than an MCP call: it's pure
    cryptographic verification against a secret you already hold, not a
    Razorpay API operation.

    Args:
        order_id: Razorpay order ID
        payment_id: Razorpay payment ID
        signature: Signature from payment response

    Returns:
        True if signature is valid, False otherwise
    """

    if not RAZORPAY_KEY_SECRET:
        logger.error("❌ Razorpay secret not configured")
        return False

    try:
        message = f"{order_id}|{payment_id}"

        expected_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        is_valid = expected_signature == signature

        if is_valid:
            logger.info(f"✅ Payment verified: {payment_id}")
        else:
            logger.warning(f"❌ Payment verification failed: {payment_id}")

        return is_valid

    except Exception as e:
        logger.error(f"❌ Error verifying signature: {str(e)}")
        return False


# =========================================================================
# Payment / Order lookups — via MCP
# =========================================================================
# Tool names below match Razorpay's published MCP tool list. If Razorpay
# renames or adds a singular fetch_payment/fetch_order tool, list the live
# tools with `session.list_tools()` and update the name here.

async def get_payment(payment_id: str) -> Dict[str, Any]:
    """Get payment details from Razorpay via MCP."""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise Exception("Razorpay credentials not configured")

    try:
        return await _call_tool("fetch_payment", {"payment_id": payment_id})
    except Exception as e:
        logger.error(f"❌ Error fetching payment via MCP: {str(e)}")
        raise Exception(f"Failed to fetch payment details: {str(e)}")


async def get_order(order_id: str) -> Dict[str, Any]:
    """Get order details from Razorpay via MCP."""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise Exception("Razorpay credentials not configured")

    try:
        return await _call_tool("fetch_order", {"order_id": order_id})
    except Exception as e:
        logger.error(f"❌ Error fetching order via MCP: {str(e)}")
        raise Exception(f"Failed to fetch order details: {str(e)}")


# =========================================================================
# Refunds
# =========================================================================

async def create_refund(
    payment_id: str, amount: Optional[float] = None, notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a refund for a payment via the Razorpay MCP server's `create_refund` tool.

    Args:
        payment_id: Razorpay payment ID to refund
        amount: Optional amount to refund (in rupees). If None, full refund.
        notes: Optional notes for the refund

    Returns:
        Refund details dict
    """
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise Exception("Razorpay credentials not configured")

    try:
        args: Dict[str, Any] = {"payment_id": payment_id}

        if amount:
            args["amount"] = int(amount * 100)  # Convert to paise

        if notes:
            args["notes"] = {"reason": notes}

        refund = await _call_tool("create_refund", args)

        logger.info(f"✅ Refund created via MCP: {refund.get('id')} for payment {payment_id}")

        return refund

    except Exception as e:
        logger.error(f"❌ Error creating refund via MCP: {str(e)}")
        raise Exception(f"Failed to create refund: {str(e)}")


# =========================================================================
# Health Check
# =========================================================================

def is_configured() -> bool:
    """Check if Razorpay is properly configured."""
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def get_config() -> Dict[str, Any]:
    """Get Razorpay configuration (safe, no secrets)."""
    return {
        "is_configured": is_configured(),
        "key_id": RAZORPAY_KEY_ID[:10] + "..." if RAZORPAY_KEY_ID else None,
        "currency": RAZORPAY_CURRENCY,
        "mode": "TEST" if RAZORPAY_KEY_ID and "test" in RAZORPAY_KEY_ID.lower() else "UNKNOWN",
        "transport": "MCP",
        "mcp_url": RAZORPAY_MCP_URL,
    }
