"""
main.py
-------
FastAPI backend with risk analysis integration.

Routes:
  Products:
    GET /api/products
    GET /api/products/search
    GET /api/products/{product_id}
  
  Cart:
    GET /api/cart
    POST /api/cart
    PUT /api/cart/{product_id}
    DELETE /api/cart/{product_id}
  
  Payment:
    POST /api/payment/create-order
    POST /api/payment/verify
  
  Risk Analysis (NEW):
    GET /api/risk/customers
    POST /api/risk/analyze
    POST /api/risk/merchant-decision
"""

import os
import uuid
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from data import PRODUCTS, CART
from models import (
    Product,
    Cart,
    CartItem,
    CartItemCreate,
    CartItemUpdate,
    PaymentOrder,
    PaymentVerification,
    PaymentVerificationResponse,
    PaymentRiskAnalysisRequest,
    MerchantDecisionRequest,
    RiskChatRequest,
    RiskChatResponse,
)
import payment
from risk_database import (
    CUSTOMERS,
    PAYMENT_ATTEMPTS,
    TRANSACTIONS,
    create_transaction,
    get_transaction,
    store_risk_assessment,
    store_merchant_decision,
    get_chat_history,
    get_risk_assessment,
    get_merchant_decision,
    set_risk_assessment_explanation,
)
from risk_tools import calculate_risk_score
import risk_explainer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="ShopAI API with Payment Risk Analysis",
    description="Phase 2: E-commerce with AI-powered payment risk investigation",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================================
# Helpers
# =========================================================================

def _find_product(product_id: int) -> dict:
    """Look up a product dict by id, or raise a 404 if it doesn't exist."""
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=404, detail=f"Product {product_id} not found")


def _build_cart_response() -> Cart:
    """Turn the raw CART dict into a full Cart model."""
    items: list[CartItem] = []
    total_price = 0.0
    total_items = 0

    for product_id, quantity in CART.items():
        product = _find_product(product_id)
        subtotal = round(product["price"] * quantity, 2)
        items.append(
            CartItem(
                product_id=product["id"],
                name=product["name"],
                price=product["price"],
                image=product["image"],
                quantity=quantity,
                stock=product["stock"],
                subtotal=subtotal,
            )
        )
        total_price += subtotal
        total_items += quantity

    return Cart(items=items, total_items=total_items, total_price=round(total_price, 2))


# =========================================================================
# Product endpoints
# =========================================================================

@app.get("/api/products", response_model=list[Product])
def get_products(category: str | None = Query(default=None, description="Filter by category")):
    """List all products, optionally filtered by category."""
    if category:
        return [p for p in PRODUCTS if p["category"].lower() == category.lower()]
    return PRODUCTS


@app.get("/api/products/search", response_model=list[Product])
def search_products(q: str = Query(default="", description="Search text")):
    """Search products by name, description, or category."""
    if not q.strip():
        return PRODUCTS

    query = q.lower().strip()
    return [
        p
        for p in PRODUCTS
        if query in p["name"].lower()
        or query in p["description"].lower()
        or query in p["category"].lower()
    ]


@app.get("/api/products/{product_id}", response_model=Product)
def get_product(product_id: int):
    """Get a single product's details by id."""
    return _find_product(product_id)


# =========================================================================
# Cart endpoints
# =========================================================================

@app.get("/api/cart", response_model=Cart)
def get_cart():
    """Return the current cart."""
    return _build_cart_response()


@app.post("/api/cart", response_model=Cart, status_code=201)
def add_to_cart(item: CartItemCreate):
    """Add a product to the cart."""
    product = _find_product(item.product_id)

    if item.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be a positive number")

    if product["stock"] == 0:
        raise HTTPException(status_code=400, detail=f"{product['name']} is out of stock")

    current_qty = CART.get(item.product_id, 0)
    new_qty = current_qty + item.quantity

    if new_qty > product["stock"]:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product['stock']} unit(s) of {product['name']} available "
            f"({current_qty} already in your cart)",
        )

    CART[item.product_id] = new_qty
    return _build_cart_response()


@app.put("/api/cart/{product_id}", response_model=Cart)
def update_cart_item(product_id: int, update: CartItemUpdate):
    """Update the quantity for a product in the cart."""
    product = _find_product(product_id)

    if product_id not in CART:
        raise HTTPException(status_code=404, detail=f"{product['name']} is not in your cart")

    if update.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be a positive number. Use DELETE to remove an item.",
        )

    if update.quantity > product["stock"]:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product['stock']} unit(s) of {product['name']} available",
        )

    CART[product_id] = update.quantity
    return _build_cart_response()


@app.delete("/api/cart/{product_id}", response_model=Cart)
def remove_from_cart(product_id: int):
    """Remove a product from the cart."""
    if product_id not in CART:
        raise HTTPException(status_code=404, detail="That product is not in your cart")

    del CART[product_id]
    return _build_cart_response()


# =========================================================================
# Payment endpoints (Razorpay)
# =========================================================================

@app.post("/api/payment/create-order", response_model=PaymentOrder)
async def create_payment_order():
    """Create a Razorpay order (via Razorpay MCP) for the current cart total."""
    cart = _build_cart_response()

    if not cart.items:
        raise HTTPException(status_code=400, detail="Your cart is empty")

    order = await payment.create_order(cart.total_price)

    return PaymentOrder(
        order_id=order["id"],
        amount=order["amount"],
        currency=order["currency"],
        key_id=payment.RAZORPAY_KEY_ID,
        amount_display=cart.total_price,
    )


@app.post("/api/payment/verify", response_model=PaymentVerificationResponse)
def verify_payment(payload: PaymentVerification):
    """Verify a completed payment."""
    is_valid = payment.verify_signature(
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail="Payment verification failed. Signature mismatch.")

    CART.clear()
    return PaymentVerificationResponse(status="success", message="Payment verified. Your order has been placed.")


# =========================================================================
# Risk Analysis endpoints (NEW)
# =========================================================================

@app.get("/api/risk/customers")
def get_available_customers():
    """
    Return list of customers for merchant to select from.
    Each customer has an estimated risk score preview.
    """
    customers = []
    
    for customer_id, customer in CUSTOMERS.items():
        payment_history = PAYMENT_ATTEMPTS.get(customer_id, [])
        order_history = customer.get("order_history", [])
        
        # Calculate estimated risk for preview
        estimated_risk = 0
        created_at = customer.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        account_age = (datetime.now() - created_at).days
        
        if account_age < 7:
            estimated_risk += 25
        
        if len(order_history) == 0:
            estimated_risk += 10
        
        failed_count = sum(1 for p in payment_history if p.get("status") == "failed")
        if failed_count >= 2:
            estimated_risk += 15
        
        customers.append({
            "customer_id": customer_id,
            "name": customer.get("name"),
            "email": customer.get("email"),
            "account_age_days": account_age,
            "total_orders": len(order_history),
            "estimated_risk_score": min(estimated_risk, 100),
        })
    
    return customers


@app.post("/api/risk/analyze")
def analyze_payment_risk(request: PaymentRiskAnalysisRequest):
    """
    Analyze payment risk for a transaction.
    
    This is called after merchant selects a customer.
    Returns: Risk assessment with score, factors, and explanation
    """
    logger.info(f"🔍 Risk Analysis: Customer {request.customer_id}, Amount ${request.amount}")
    
    # Create transaction
    transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
    create_transaction(
        transaction_id=transaction_id,
        customer_id=request.customer_id,
        amount=request.amount,
        currency=request.currency
    )
    
    # Get customer
    customer = CUSTOMERS.get(request.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer {request.customer_id} not found")
    
    # Calculate risk (deterministic — this is the score of record)
    risk_result = calculate_risk_score(transaction_id)
    
    if not risk_result.get("success"):
        raise HTTPException(status_code=500, detail=f"Risk analysis failed: {risk_result.get('error')}")
    
    # Store the assessment first so the explainer has something to ground itself in.
    store_risk_assessment(
        transaction_id=transaction_id,
        risk_score=risk_result['risk_score'],
        risk_level=risk_result['risk_level'],
        risk_factors=risk_result['risk_factors'],
        ai_explanation="",
        recommendation=risk_result['recommendation']
    )

    # Ask the LLM to translate the score + factors into plain, merchant-friendly language.
    # The score/level/recommendation above are never touched by the LLM — it only explains them.
    try:
        ai_explanation = risk_explainer.explain_risk(transaction_id)
        set_risk_assessment_explanation(transaction_id, ai_explanation)
    except Exception as e:
        logger.error(f"❌ LLM explanation failed: {str(e)}")
        ai_explanation = (
            f"This transaction scored {risk_result['risk_score']}/100 ({risk_result['risk_level']} risk). "
            "A plain-language explanation isn't available right now — see the risk factors below for details."
        )
        set_risk_assessment_explanation(transaction_id, ai_explanation)
    
    logger.info(f"✅ Risk Analysis Complete: Score {risk_result['risk_score']}/100")
    
    return {
        "success": True,
        "transaction_id": transaction_id,
        "customer_id": request.customer_id,
        "amount": request.amount,
        "risk_score": risk_result['risk_score'],
        "risk_level": risk_result['risk_level'],
        "risk_factors": risk_result['risk_factors'],
        "ai_explanation": ai_explanation,
        "recommendation": risk_result['recommendation'],
    }


@app.post("/api/risk/merchant-decision")
async def merchant_decision(decision_request: MerchantDecisionRequest):
    """
    Process merchant's accept/decline decision.
    
    If ACCEPT: Return Razorpay order details
    If DECLINE: Return declined status
    """
    logger.info(f"🎯 Merchant Decision: {decision_request.decision} for {decision_request.transaction_id}")
    
    transaction = get_transaction(decision_request.transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction {decision_request.transaction_id} not found")
    
    # Store decision
    store_merchant_decision(
        transaction_id=decision_request.transaction_id,
        decision=decision_request.decision,
        reason=decision_request.reason or ""
    )
    
    if decision_request.decision == "ACCEPT":
        try:
            order = await payment.create_order(transaction["amount"])
            
            logger.info(f"✅ Razorpay order created: {order['id']}")
            
            return {
                "success": True,
                "status": "accepted",
                "order_id": order["id"],
                "amount": order["amount"],
                "currency": order["currency"],
                "key_id": payment.RAZORPAY_KEY_ID,
                "amount_display": transaction["amount"],
                "transaction_id": decision_request.transaction_id,
            }
        except Exception as e:
            logger.error(f"❌ Error creating Razorpay order: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Payment setup failed: {str(e)}")
    
    elif decision_request.decision == "DECLINE":
        logger.info(f"❌ Payment declined: {decision_request.transaction_id}")
        
        return {
            "success": True,
            "status": "declined",
            "message": "Payment declined by merchant",
            "transaction_id": decision_request.transaction_id,
            "reason": decision_request.reason or "No reason provided"
        }
    
    else:
        raise HTTPException(status_code=400, detail="Invalid decision. Must be ACCEPT or DECLINE")


@app.post("/api/risk/chat", response_model=RiskChatResponse)
def risk_chat(chat_request: RiskChatRequest):
    """
    Let the merchant ask a follow-up question about a transaction's risk assessment.

    Answers are grounded by letting the LLM call the same investigation tools a
    human analyst would use (customer profile, order history, payment history,
    risk signals) — it never invents facts, and it never overrides the score.
    """
    transaction = get_transaction(chat_request.transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction {chat_request.transaction_id} not found")

    try:
        reply = risk_explainer.chat_about_risk(chat_request.transaction_id, chat_request.message)
    except Exception as e:
        logger.error(f"❌ Risk chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Couldn't get an answer right now, please try again.")

    history = get_chat_history(chat_request.transaction_id)

    return RiskChatResponse(
        transaction_id=chat_request.transaction_id,
        reply=reply,
        history=history,
    )

@app.get("/api/risk/dashboard")
def get_risk_dashboard():
    """
    Return every transaction that's had a risk assessment, newest first, with
    its current decision status. Powers the merchant dashboard panel and its
    notification badge (pending_count = assessed but not yet decided).
    """
    items = []

    for transaction_id, transaction in TRANSACTIONS.items():
        assessment = get_risk_assessment(transaction_id)
        if not assessment:
            continue  # still mid-analysis or never completed

        decision = get_merchant_decision(transaction_id)
        customer = CUSTOMERS.get(transaction["customer_id"], {})

        items.append({
            "transaction_id": transaction_id,
            "customer_id": transaction["customer_id"],
            "customer_name": customer.get("name", "Unknown customer"),
            "amount": transaction["amount"],
            "currency": transaction["currency"],
            "created_at": transaction["created_at"],
            "risk_score": assessment["risk_score"],
            "risk_level": assessment["risk_level"],
            "recommendation": assessment["recommendation"],
            "decision": decision["decision"] if decision else None,
            "decided_at": decision["decided_at"] if decision else None,
        })

    items.sort(key=lambda item: item["created_at"], reverse=True)
    pending_count = sum(1 for item in items if item["decision"] is None)

    return {"transactions": items, "pending_count": pending_count}


@app.get("/api/risk/transaction/{transaction_id}")
def get_risk_transaction_detail(transaction_id: str):
    """
    Return everything the merchant dashboard needs to redisplay one
    transaction: the stored risk assessment, decision (if any), and chat
    history — without re-running the risk engine or calling the LLM again.
    """
    transaction = get_transaction(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")

    assessment = get_risk_assessment(transaction_id)
    if not assessment:
        raise HTTPException(status_code=404, detail=f"No risk assessment yet for {transaction_id}")

    decision = get_merchant_decision(transaction_id)

    return {
        "transaction_id": transaction_id,
        "customer_id": transaction["customer_id"],
        "amount": transaction["amount"],
        "currency": transaction["currency"],
        "risk_score": assessment["risk_score"],
        "risk_level": assessment["risk_level"],
        "risk_factors": assessment["risk_factors"],
        "ai_explanation": assessment["ai_explanation"],
        "recommendation": assessment["recommendation"],
        "decision": decision["decision"] if decision else None,
        "decided_at": decision["decided_at"] if decision else None,
        "chat_history": get_chat_history(transaction_id),
    }

@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "message": "ShopAI API v2.0 is running",
        "endpoints": {
            "products": "/api/products",
            "cart": "/api/cart",
            "payment": "/api/payment/create-order",
            "risk_analysis": "/api/risk/customers",
            "docs": "/docs"
        }
    }