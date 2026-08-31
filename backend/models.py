"""
models.py
---------
All Pydantic models used by the API.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class Product(BaseModel):
    """Represents one product in the catalog."""
    id: int
    name: str
    description: str
    price: float
    category: str
    brand: str
    image: str
    stock: int
    rating: float
    reviews_count: int
    tags: List[str]


class CartItemCreate(BaseModel):
    """Body for POST /api/cart (add a product to the cart)."""
    product_id: int
    quantity: int = Field(default=1, description="How many units to add")


class CartItemUpdate(BaseModel):
    """Body for PUT /api/cart/{product_id} (set a new quantity)."""
    quantity: int


class CartItem(BaseModel):
    """One line item inside the cart response."""
    product_id: int
    name: str
    price: float
    image: str
    quantity: int
    stock: int
    subtotal: float


class Cart(BaseModel):
    """The full shape returned by GET /api/cart."""
    items: List[CartItem]
    total_items: int
    total_price: float


class PaymentOrder(BaseModel):
    """Response for POST /api/payment/create-order."""
    order_id: str
    amount: int
    currency: str
    key_id: str
    amount_display: float


class PaymentVerification(BaseModel):
    """Body for POST /api/payment/verify."""
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentVerificationResponse(BaseModel):
    """Response for POST /api/payment/verify."""
    status: str
    message: str


class RiskFactor(BaseModel):
    """A single risk factor with evidence."""
    factor: str
    severity: str
    score: int
    evidence: str
    explanation: str


class PaymentRiskAnalysisRequest(BaseModel):
    """Request for risk analysis."""
    customer_id: int
    amount: float
    currency: str = "INR"


class MerchantDecisionRequest(BaseModel):
    """Merchant's decision to accept or decline payment."""
    transaction_id: str
    decision: str
    reason: Optional[str] = None


class ChatMessage(BaseModel):
    """One turn in the merchant/AI chat about a transaction's risk."""
    role: str
    content: str


class RiskChatRequest(BaseModel):
    """Body for POST /api/risk/chat — a merchant's follow-up question."""
    transaction_id: str
    message: str


class RiskChatResponse(BaseModel):
    """Response for POST /api/risk/chat."""
    transaction_id: str
    reply: str
    history: List[ChatMessage]