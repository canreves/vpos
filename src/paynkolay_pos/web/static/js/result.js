(function () {
  const form = document.getElementById("result-lookup-form");
  const lookupInput = document.getElementById("lookup-order-id");
  const lookupButton = document.getElementById("lookup-payment");
  const state = document.getElementById("result-state");
  const message = document.getElementById("result-message");
  const threeDsLink = document.getElementById("result-three-ds-link");

  const fields = {
    orderId: document.getElementById("result-order-id"),
    status: document.getElementById("result-status"),
    amount: document.getElementById("result-amount"),
    card: document.getElementById("result-card"),
    cardHolder: document.getElementById("result-card-holder"),
    installment: document.getElementById("result-installment"),
    providerRef: document.getElementById("result-provider-ref"),
    failure: document.getElementById("result-failure"),
    updated: document.getElementById("result-updated"),
  };

  function setState(text, kind) {
    state.textContent = text;
    state.className = `status-pill ${kind}`;
  }

  function clearResult() {
    Object.values(fields).forEach((field) => {
      field.textContent = "-";
    });
    threeDsLink.classList.add("hidden");
  }

  function renderPayment(payment) {
    fields.orderId.textContent = payment.order_id;
    fields.status.textContent = payment.status;
    fields.amount.textContent = `${payment.amount} ${payment.currency}`;
    fields.card.textContent = payment.masked_pan;
    fields.cardHolder.textContent = payment.card_holder;
    fields.installment.textContent = String(payment.installment_count);
    fields.providerRef.textContent = payment.provider_transaction_id || "-";
    fields.failure.textContent = payment.failure_reason || "-";
    fields.updated.textContent = payment.updated_at;

    if (payment.links && payment.links.three_ds) {
      threeDsLink.href = payment.links.three_ds;
      threeDsLink.classList.remove("hidden");
    } else {
      threeDsLink.classList.add("hidden");
    }

    setState(payment.status, payment.status === "failed" ? "error" : "success");
    message.textContent = "Payment state loaded.";
  }

  async function lookupPayment(orderId) {
    const normalizedOrderId = String(orderId || "").trim();
    if (!normalizedOrderId) {
      clearResult();
      setState("Idle", "neutral");
      message.textContent = "Enter an order ID to inspect payment state.";
      return;
    }

    lookupButton.disabled = true;
    setState("Loading", "neutral");
    message.textContent = "Loading payment state.";

    try {
      const payment = await window.PaynkolayApi.getPayment(normalizedOrderId);
      lookupInput.value = payment.order_id;
      renderPayment(payment);
    } catch (error) {
      clearResult();
      setState("Error", "error");
      message.textContent = error.message;
    } finally {
      lookupButton.disabled = false;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    lookupPayment(lookupInput.value);
  });

  const initialOrderId = new URLSearchParams(window.location.search).get("order_id");
  if (initialOrderId) {
    lookupInput.value = initialOrderId;
    lookupPayment(initialOrderId);
  }
})();
