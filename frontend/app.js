/**
 * app.js - SHOPAI WITH PAYMENT RISK ANALYSIS
 * Complete frontend logic with customer selection and risk dashboard
 */

const API_BASE = "http://localhost:8000/api";

// ---- App state -------------------------------------------------------
let allProducts = [];
let activeCategory = "All";
let searchQuery = "";
let currentCart = { items: [], total_items: 0, total_price: 0 };
let currentCustomerId = null; // the "logged in" shopper — set once, used automatically at checkout
let availableCustomers = [];

// ---- DOM references --------------------------------------------------
const els = {
  searchInput: document.getElementById("searchInput"),
  categoryBar: document.getElementById("categoryBar"),
  productGrid: document.getElementById("productGrid"),
  resultMeta: document.getElementById("resultMeta"),
  emptyState: document.getElementById("emptyState"),

  cartToggle: document.getElementById("cartToggle"),
  accountSwitch: document.getElementById("accountSwitch"),
  accountAvatar: document.getElementById("accountAvatar"),
  accountName: document.getElementById("accountName"),
  cartClose: document.getElementById("cartClose"),
  cartOverlay: document.getElementById("cartOverlay"),
  cartDrawer: document.getElementById("cartDrawer"),
  cartCount: document.getElementById("cartCount"),
  cartItems: document.getElementById("cartItems"),
  cartEmptyState: document.getElementById("cartEmptyState"),
  summaryItems: document.getElementById("summaryItems"),
  summaryTotal: document.getElementById("summaryTotal"),
  checkoutBtn: document.getElementById("checkoutBtn"),

  customerModal: document.getElementById("customerModal"),
  customerList: document.getElementById("customerList"),

  dashboardToggle: document.getElementById("dashboardToggle"),
  dashboardBadge: document.getElementById("dashboardBadge"),
  dashboardOverlay: document.getElementById("dashboardOverlay"),
  dashboardDrawer: document.getElementById("dashboardDrawer"),
  dashboardClose: document.getElementById("dashboardClose"),
  dashboardList: document.getElementById("dashboardList"),
  dashboardEmptyState: document.getElementById("dashboardEmptyState"),

  toast: document.getElementById("toast"),
};

// =========================================================================
// API helpers
// =========================================================================

async function apiRequest(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (_) {}
    throw new Error(detail);
  }

  return res.json();
}

async function fetchProducts({ category, search } = {}) {
  if (search && search.trim()) {
    return apiRequest(`/products/search?q=${encodeURIComponent(search.trim())}`);
  }
  if (category && category !== "All") {
    return apiRequest(`/products?category=${encodeURIComponent(category)}`);
  }
  return apiRequest("/products");
}

async function fetchCart() {
  return apiRequest("/cart");
}

async function addToCart(productId, quantity = 1) {
  return apiRequest("/cart", {
    method: "POST",
    body: JSON.stringify({ product_id: productId, quantity }),
  });
}

async function setCartQuantity(productId, quantity) {
  return apiRequest(`/cart/${productId}`, {
    method: "PUT",
    body: JSON.stringify({ quantity }),
  });
}

async function removeFromCart(productId) {
  return apiRequest(`/cart/${productId}`, { method: "DELETE" });
}

async function fetchCustomers() {
  return apiRequest("/risk/customers");
}

async function fetchRiskDashboard() {
  return apiRequest("/risk/dashboard");
}

async function fetchRiskTransactionDetail(transactionId) {
  return apiRequest(`/risk/transaction/${transactionId}`);
}

async function analyzePaymentRisk(customerId) {
  return apiRequest("/risk/analyze", {
    method: "POST",
    body: JSON.stringify({
      customer_id: customerId,
      amount: currentCart.total_price,
      currency: "USD",
    }),
  });
}

async function submitMerchantDecision(transactionId, decision, reason = "") {
  return apiRequest("/risk/merchant-decision", {
    method: "POST",
    body: JSON.stringify({
      transaction_id: transactionId,
      decision: decision,
      reason: reason,
    }),
  });
}

async function sendRiskChatMessage(transactionId, message) {
  return apiRequest("/risk/chat", {
    method: "POST",
    body: JSON.stringify({ transaction_id: transactionId, message }),
  });
}

async function createPaymentOrder() {
  return apiRequest("/payment/create-order", { method: "POST" });
}

async function verifyPayment(payload) {
  return apiRequest("/payment/verify", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// =========================================================================
// Rendering — products
// =========================================================================

function renderCategoryBar() {
  const categories = ["All", ...new Set(allProducts.map((p) => p.category))];

  els.categoryBar.innerHTML = "";
  categories.forEach((cat) => {
    const chip = document.createElement("button");
    chip.className = "chip" + (cat === activeCategory ? " is-active" : "");
    chip.textContent = cat;
    chip.addEventListener("click", () => {
      activeCategory = cat;
      els.searchInput.value = "";
      searchQuery = "";
      loadProducts();
    });
    els.categoryBar.appendChild(chip);
  });
}

function stockBadge(stock) {
  if (stock === 0) return { text: "Out of stock", cls: "is-out" };
  if (stock <= 5) return { text: `Only ${stock} left`, cls: "is-low" };
  return { text: "In stock", cls: "" };
}

function renderProducts(products) {
  els.productGrid.innerHTML = "";
  els.emptyState.hidden = products.length > 0;

  els.resultMeta.textContent =
    products.length === 0
      ? ""
      : `${products.length} product${products.length === 1 ? "" : "s"}` +
        (activeCategory !== "All" ? ` in ${activeCategory}` : "") +
        (searchQuery ? ` matching "${searchQuery}"` : "");

  products.forEach((product) => {
    const badge = stockBadge(product.stock);

    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="card__image-wrap">
        <img src="${product.image}" alt="${product.name}" loading="lazy" />
        <span class="card__stock-badge ${badge.cls}">${badge.text}</span>
      </div>
      <div class="card__body">
        <span class="card__category">${product.category}</span>
        <h3 class="card__name">${product.name}</h3>
        <div class="card__meta">
          <span class="card__brand">${product.brand}</span>
          <span class="card__rating">★ ${product.rating.toFixed(1)} <span class="card__rating-count">(${product.reviews_count})</span></span>
        </div>
        <p class="card__desc">${product.description}</p>
        <div class="card__footer">
          <span class="price-tag">$${product.price.toFixed(2)}</span>
          <button class="add-btn" ${product.stock === 0 ? "disabled" : ""} data-id="${product.id}">
            ${product.stock === 0 ? "Unavailable" : "Add to Cart"}
          </button>
        </div>
      </div>
    `;

    card.querySelector(".add-btn").addEventListener("click", (e) => {
      handleAddToCart(product.id, e.currentTarget);
    });

    els.productGrid.appendChild(card);
  });
}

async function loadProducts() {
  renderCategoryBar();
  try {
    const products = await fetchProducts({ category: activeCategory, search: searchQuery });
    renderProducts(products);
  } catch (err) {
    showToast(err.message, true);
  }
}

// =========================================================================
// Rendering — cart
// =========================================================================

function renderCart() {
  els.cartCount.textContent = currentCart.total_items;
  els.summaryItems.textContent = currentCart.total_items;
  els.summaryTotal.textContent = `$${currentCart.total_price.toFixed(2)}`;

  els.cartItems.innerHTML = "";
  const isEmpty = currentCart.items.length === 0;
  els.cartEmptyState.hidden = !isEmpty;
  els.checkoutBtn.disabled = isEmpty;

  currentCart.items.forEach((item) => {
    const line = document.createElement("div");
    line.className = "cart-line";
    line.innerHTML = `
      <img src="${item.image}" alt="${item.name}" />
      <div class="cart-line__info">
        <span class="cart-line__name">${item.name}</span>
        <span class="cart-line__unit-price mono">$${item.price.toFixed(2)} each</span>
        <div class="cart-line__row">
          <div class="qty-control">
            <button data-action="decrease" aria-label="Decrease quantity">−</button>
            <span>${item.quantity}</span>
            <button data-action="increase" aria-label="Increase quantity">+</button>
          </div>
          <span class="cart-line__subtotal">$${item.subtotal.toFixed(2)}</span>
        </div>
        <button class="remove-btn" data-action="remove">Remove</button>
      </div>
    `;

    line.querySelector('[data-action="increase"]').addEventListener("click", () =>
      handleQuantityChange(item.product_id, item.quantity + 1)
    );
    line.querySelector('[data-action="decrease"]').addEventListener("click", () => {
      if (item.quantity - 1 <= 0) {
        handleRemove(item.product_id);
      } else {
        handleQuantityChange(item.product_id, item.quantity - 1);
      }
    });
    line.querySelector('[data-action="remove"]').addEventListener("click", () =>
      handleRemove(item.product_id)
    );

    els.cartItems.appendChild(line);
  });
}

async function refreshCart() {
  try {
    currentCart = await fetchCart();
    renderCart();
  } catch (err) {
    showToast(err.message, true);
  }
}

// =========================================================================
// Account Switcher (demo only — simulates "logging in" as a different shopper)
// =========================================================================

function getInitials(name) {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase();
}

function getRiskColor(riskScore) {
  if (riskScore < 30) return "risk-low";
  if (riskScore < 60) return "risk-medium";
  return "risk-high";
}

function getRiskLabel(riskScore) {
  if (riskScore < 30) return "LOW";
  if (riskScore < 60) return "MEDIUM";
  return "HIGH";
}

function setCurrentCustomer(customerId) {
  currentCustomerId = customerId;
  const customer = availableCustomers.find((c) => c.customer_id === customerId);
  if (customer) {
    els.accountAvatar.textContent = getInitials(customer.name);
    els.accountName.textContent = customer.name;
  }
}

function openCustomerModal() {
  els.customerModal.hidden = false;
  els.customerList.innerHTML = "";

  availableCustomers.forEach((customer) => {
    const card = document.createElement("div");
    card.className = "customer-card";
    if (currentCustomerId === customer.customer_id) {
      card.classList.add("is-selected");
    }

    const riskColor = getRiskColor(customer.estimated_risk_score);
    const riskLabel = getRiskLabel(customer.estimated_risk_score);

    card.innerHTML = `
      <div class="customer-avatar">${getInitials(customer.name)}</div>
      <div class="customer-info">
        <div class="customer-name">${customer.name}</div>
        <div class="customer-email">${customer.email}</div>
        <div class="customer-meta">
          <span class="customer-meta__item">📅 ${customer.account_age_days} days old</span>
          <span class="customer-meta__item">📦 ${customer.total_orders} orders</span>
        </div>
      </div>
      <div class="customer-risk-badge ${riskColor}">${riskLabel}</div>
    `;

    card.addEventListener("click", () => {
      setCurrentCustomer(customer.customer_id);
      closeCustomerModal();
    });

    els.customerList.appendChild(card);
  });
}

function closeCustomerModal() {
  els.customerModal.hidden = true;
}

// =========================================================================
// Event handlers
// =========================================================================

async function handleAddToCart(productId, buttonEl) {
  buttonEl.disabled = true;
  try {
    currentCart = await addToCart(productId, 1);
    renderCart();
    showToast("Added to cart");
    openCart();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    buttonEl.disabled = false;
  }
}

async function handleQuantityChange(productId, quantity) {
  try {
    currentCart = await setCartQuantity(productId, quantity);
    renderCart();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function handleRemove(productId) {
  try {
    currentCart = await removeFromCart(productId);
    renderCart();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function handleCheckout() {
  if (currentCart.items.length === 0) {
    showToast("Your cart is empty", true);
    return;
  }

  if (!currentCustomerId) {
    showToast("No shopper account loaded yet — try again in a moment", true);
    return;
  }

  await proceedWithRiskAnalysis();
}

async function proceedWithRiskAnalysis() {
  els.checkoutBtn.disabled = true;
  els.checkoutBtn.textContent = "Analyzing risk…";

  try {
    await analyzePaymentRisk(currentCustomerId);
    await refreshDashboardBadge();
    closeCart();
    showToast("Risk analysis complete — review it in the merchant dashboard 📋");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    els.checkoutBtn.disabled = currentCart.items.length === 0;
    els.checkoutBtn.textContent = "Checkout";
  }
}

// =========================================================================
// Risk Dashboard
// =========================================================================

function showRiskDashboard(riskAnalysis, options = {}) {
  const { risk_score, risk_level, risk_factors, ai_explanation, recommendation, transaction_id } = riskAnalysis;
  const decision = options.decision || riskAnalysis.decision || null;
  const chatHistory = options.chatHistory || [];

  const riskColor = getRiskColor(risk_score);
  const riskLevelText = getRiskLabel(risk_score);

  const actionsHtml = decision
    ? `
      <div class="risk-dashboard__decision risk-dashboard__decision--${decision.toLowerCase()}">
        ${decision === "ACCEPT" ? "✓ Payment accepted" : "✕ Payment declined"}
      </div>
    `
    : `
      <div class="risk-dashboard__actions">
        <button class="btn btn--secondary" onclick="closeRiskDashboard()">Cancel</button>
        <button class="btn btn--primary" onclick="approvePayment('${transaction_id}')">
          ✓ Accept Payment
        </button>
        ${risk_score >= 30 ? `
          <button class="btn btn--danger" onclick="declinePayment('${transaction_id}')">
            ✕ Decline Payment
          </button>
        ` : ""}
      </div>

      <p class="risk-dashboard__note">⚠️ Final decision is yours. Proceed at your discretion.</p>
    `;

  const dashboard = document.createElement("div");
  dashboard.className = "risk-dashboard";
  dashboard.innerHTML = `
    <div class="risk-dashboard__overlay"></div>
    <div class="risk-dashboard__content">
      <div class="risk-dashboard__header">
        <h2>Payment Risk Assessment</h2>
        <button class="close-btn" onclick="closeRiskDashboard()">✕</button>
      </div>

      <div class="risk-dashboard__score">
        <div class="score-circle ${riskColor}">
          <span class="score-number">${risk_score}</span>
          <span class="score-total">/100</span>
        </div>
        <div class="score-info">
          <h3 class="score-level">${riskLevelText} RISK</h3>
          <p class="score-desc">
            ${risk_score < 30 ? "This transaction appears safe to process." : ""}
            ${risk_score >= 30 && risk_score < 60 ? "This transaction requires manual review." : ""}
            ${risk_score >= 60 ? "This transaction shows concerning patterns." : ""}
          </p>
        </div>
      </div>

      <div class="risk-dashboard__factors">
        <h4>Risk Factors</h4>
        ${risk_factors.length > 0 
          ? risk_factors.map(factor => `
              <div class="risk-factor">
                <div class="risk-factor__header">
                  <span class="risk-factor__name">${factor.factor}</span>
                  <span class="risk-factor__severity ${factor.severity.toLowerCase()}">${factor.severity}</span>
                </div>
                <p class="risk-factor__evidence">${factor.evidence}</p>
              </div>
            `).join("")
          : "<p>No significant risk factors detected.</p>"
        }
      </div>

      <div class="risk-dashboard__explanation">
        <h4>What this means</h4>
        <p>${ai_explanation}</p>
      </div>

      <div class="risk-dashboard__chat">
        <h4>Ask a question</h4>
        <div class="risk-chat__messages" id="riskChatMessages"></div>
        <form class="risk-chat__form" id="riskChatForm">
          <input
            type="text"
            id="riskChatInput"
            placeholder="e.g. Has this customer paid before?"
            autocomplete="off"
          />
          <button type="submit" class="btn btn--secondary">Ask</button>
        </form>
      </div>

      ${actionsHtml}
    </div>
  `;

  document.body.appendChild(dashboard);

  // Replay any prior chat turns (skips the very first assistant turn, which
  // duplicates the "What this means" explanation already shown above).
  chatHistory.forEach((turn, index) => {
    if (index === 0 && turn.role === "assistant") return;
    appendChatBubble(turn.role, turn.content);
  });

  attachRiskChatHandlers(transaction_id);
}

function closeRiskDashboard() {
  const dashboard = document.querySelector(".risk-dashboard");
  if (dashboard) dashboard.remove();
}

function appendChatBubble(role, text) {
  const list = document.getElementById("riskChatMessages");
  if (!list) return;
  const bubble = document.createElement("div");
  bubble.className = `risk-chat__bubble risk-chat__bubble--${role}`;
  bubble.textContent = text;
  list.appendChild(bubble);
  list.scrollTop = list.scrollHeight;
  return bubble;
}

function attachRiskChatHandlers(transactionId) {
  const form = document.getElementById("riskChatForm");
  const input = document.getElementById("riskChatInput");
  if (!form || !input) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendChatBubble("user", message);
    input.value = "";
    input.disabled = true;

    const thinking = appendChatBubble("assistant", "Thinking…");
    thinking.classList.add("risk-chat__bubble--thinking");

    try {
      const { reply } = await sendRiskChatMessage(transactionId, message);
      thinking.remove();
      appendChatBubble("assistant", reply);
    } catch (err) {
      thinking.remove();
      appendChatBubble("assistant", "Sorry, I couldn't answer that just now.");
    } finally {
      input.disabled = false;
      input.focus();
    }
  });
}

async function approvePayment(transactionId) {
  closeRiskDashboard();
  
  // Store merchant decision
  try {
    await submitMerchantDecision(transactionId, "ACCEPT", "Merchant approved");
    refreshDashboardBadge();
  } catch (err) {
    showToast(err.message, true);
    return;
  }

  els.checkoutBtn.disabled = true;
  els.checkoutBtn.textContent = "Processing payment…";

  try {
    const order = await createPaymentOrder();

    const options = {
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      order_id: order.order_id,
      name: "ShopAI",
      description: "Test mode order",
      theme: { color: "#5b4fe8" },
      handler: async function (response) {
        try {
          await verifyPayment({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          showToast("✓ Payment successful — order placed!");
          await refreshCart();
          closeCart();
        } catch (err) {
          showToast(err.message, true);
        }
      },
      modal: {
        ondismiss: function () {
          showToast("Checkout cancelled");
        },
      },
    };

    const rzp = new Razorpay(options);
    rzp.on("payment.failed", function (response) {
      showToast(`Payment failed: ${response.error.description}`, true);
    });
    rzp.open();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    els.checkoutBtn.disabled = currentCart.items.length === 0;
    els.checkoutBtn.textContent = "Checkout";
  }
}

async function declinePayment(transactionId) {
  closeRiskDashboard();
  
  // Store merchant decision
  try {
    await submitMerchantDecision(transactionId, "DECLINE", "Merchant declined payment");
    refreshDashboardBadge();
  } catch (err) {
    showToast(err.message, true);
  }

  showToast("❌ Payment declined by merchant");
  closeCart();
}

function openCart() {
  els.cartDrawer.classList.add("is-open");
  els.cartOverlay.hidden = false;
}

function closeCart() {
  els.cartDrawer.classList.remove("is-open");
  els.cartOverlay.hidden = true;
}

// =========================================================================
// Merchant Dashboard (accept/decline lives here — click the 📋 icon)
// =========================================================================

async function refreshDashboardBadge() {
  try {
    const { pending_count } = await fetchRiskDashboard();
    if (pending_count > 0) {
      els.dashboardBadge.textContent = pending_count > 9 ? "9+" : pending_count;
      els.dashboardBadge.hidden = false;
    } else {
      els.dashboardBadge.hidden = true;
    }
  } catch (err) {
    // Silent — badge just won't update this cycle.
  }
}

async function openDashboard() {
  els.dashboardDrawer.classList.add("is-open");
  els.dashboardOverlay.hidden = false;
  await renderDashboardList();
}

function closeDashboard() {
  els.dashboardDrawer.classList.remove("is-open");
  els.dashboardOverlay.hidden = true;
}

async function renderDashboardList() {
  els.dashboardList.innerHTML = "";

  let transactions = [];
  try {
    ({ transactions } = await fetchRiskDashboard());
  } catch (err) {
    showToast("Could not load the dashboard", true);
    return;
  }

  els.dashboardEmptyState.hidden = transactions.length > 0;

  transactions.forEach((txn) => {
    const riskColor = getRiskColor(txn.risk_score);
    const riskLabel = getRiskLabel(txn.risk_score);
    const statusLabel = !txn.decision
      ? "Awaiting decision"
      : txn.decision === "ACCEPT"
      ? "Accepted"
      : "Declined";
    const statusClass = !txn.decision
      ? "is-pending"
      : txn.decision === "ACCEPT"
      ? "is-accepted"
      : "is-declined";

    const row = document.createElement("div");
    row.className = `dashboard-row ${statusClass}`;
    row.innerHTML = `
      <div class="dashboard-row__risk ${riskColor}">${riskLabel}</div>
      <div class="dashboard-row__info">
        <div class="dashboard-row__customer">${txn.customer_name}</div>
        <div class="dashboard-row__meta">${txn.currency} ${txn.amount.toFixed(2)} · Score ${txn.risk_score}/100</div>
      </div>
      <div class="dashboard-row__status ${statusClass}">${statusLabel}</div>
    `;

    row.addEventListener("click", () => openTransactionFromDashboard(txn.transaction_id));
    els.dashboardList.appendChild(row);
  });
}

async function openTransactionFromDashboard(transactionId) {
  try {
    const detail = await fetchRiskTransactionDetail(transactionId);
    closeDashboard();
    showRiskDashboard(detail, { decision: detail.decision, chatHistory: detail.chat_history });
  } catch (err) {
    showToast(err.message, true);
  }
}

let searchDebounce;
function handleSearchInput(e) {
  searchQuery = e.target.value;
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    activeCategory = "All";
    loadProducts();
  }, 250);
}

function showToast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle("is-error", isError);
  els.toast.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    els.toast.hidden = true;
  }, 2500);
}

// =========================================================================
// Init
// =========================================================================

async function init() {
  els.searchInput.addEventListener("input", handleSearchInput);
  els.cartToggle.addEventListener("click", openCart);
  els.cartClose.addEventListener("click", closeCart);
  els.cartOverlay.addEventListener("click", closeCart);
  els.checkoutBtn.addEventListener("click", handleCheckout);
  els.accountSwitch.addEventListener("click", openCustomerModal);
  els.dashboardToggle.addEventListener("click", openDashboard);
  els.dashboardClose.addEventListener("click", closeDashboard);
  els.dashboardOverlay.addEventListener("click", closeDashboard);

  try {
    allProducts = await fetchProducts();
    renderCategoryBar();
    renderProducts(allProducts);
  } catch (err) {
    showToast("Could not reach the ShopAI API. Is the backend running?", true);
  }

  // Fetch available customers and default to the first as the "logged in" shopper.
  // In a real storefront this would come from the shopper's session/auth instead.
  try {
    availableCustomers = await fetchCustomers();
    console.log("✓ Customers loaded:", availableCustomers.length);
    if (availableCustomers.length > 0) {
      setCurrentCustomer(availableCustomers[0].customer_id);
    }
  } catch (err) {
    showToast("Could not load customers for risk analysis", true);
  }

  await refreshCart();
  await refreshDashboardBadge();
}

// Start the app
init();