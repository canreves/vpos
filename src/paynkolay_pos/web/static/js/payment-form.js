(function () {
  const form = document.getElementById("payment-form");
  const configStatus = document.getElementById("config-status");
  const environmentLabel = document.getElementById("environment-label");
  const submitButton = document.getElementById("submit-payment");
  const message = document.getElementById("form-message");
  const state = document.getElementById("payment-state");

  const resultFields = {
    orderId: document.getElementById("result-order-id"),
    status: document.getElementById("result-status"),
    amount: document.getElementById("result-amount"),
    threeDs: document.getElementById("result-3ds"),
    providerRef: document.getElementById("result-provider-ref"),
    paymentListStatus: document.getElementById("result-payment-list-status"),
    paymentListAuth: document.getElementById("result-payment-list-auth"),
  };
  const threeDsLink = document.getElementById("result-three-ds-link");

  function setMessage(text, kind) {
    message.textContent = text;
    state.textContent = kind === "success" ? "Created" : kind === "error" ? "Error" : "Idle";
    state.className = `status-pill ${kind === "success" ? "success" : kind === "error" ? "error" : "neutral"}`;
  }

  function formPayload() {
    const data = new FormData(form);
    return {
      amount: data.get("amount"),
      currency: data.get("currency"),
      card_brand: data.get("card_brand"),
      card_number: String(data.get("card_number") || "").replace(/\s+/g, ""),
      card_holder: data.get("card_holder"),
      expiry_month: Number(data.get("expiry_month")),
      expiry_year: Number(data.get("expiry_year")),
      cvv: data.get("cvv"),
      requires_3ds: data.get("requires_3ds") === "on",
      installment_count: Number(data.get("installment_count")),
    };
  }

  async function loadConfig() {
    const config = await window.PaynkolayApi.getConfig();
    const currencySelect = document.getElementById("currency");
    const brandSelect = document.getElementById("card-brand");
    currencySelect.replaceChildren(
      ...config.supported_currencies.map((currency) => {
        const option = document.createElement("option");
        option.value = currency;
        option.textContent = currency;
        return option;
      }),
    );
    brandSelect.replaceChildren(
      ...config.supported_card_brands.map((brand) => {
        const option = document.createElement("option");
        option.value = brand;
        option.textContent = brand.toUpperCase();
        return option;
      }),
    );

    if (config.runtime_configured) {
      configStatus.textContent = "Configured";
      configStatus.className = "status-pill success";
      environmentLabel.textContent = `Environment ${config.active_environment}`;
      return;
    }

    configStatus.textContent = "Local";
    configStatus.className = "status-pill neutral";
    environmentLabel.textContent = "Runtime config not loaded";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submitButton.disabled = true;
    setMessage("Submitting", "neutral");

    try {
      const response = await window.PaynkolayApi.createPayment(formPayload());
      resultFields.orderId.textContent = response.order_id;
      resultFields.status.textContent = response.status;
      resultFields.amount.textContent = `${response.amount} ${response.currency}`;
      resultFields.threeDs.textContent = response.requires_3ds ? "Required" : "Not required";
      resultFields.providerRef.textContent = response.provider_transaction_id || "-";
      if (response.payment_list) {
        resultFields.paymentListStatus.textContent =
          response.payment_list.status || response.payment_list.error || "-";
        resultFields.paymentListAuth.textContent = response.payment_list.authorization_code || "-";
      } else {
        resultFields.paymentListStatus.textContent = "-";
        resultFields.paymentListAuth.textContent = "-";
      }
      if (response.three_ds && response.three_ds.render_url) {
        threeDsLink.href = response.three_ds.render_url;
        threeDsLink.classList.remove("hidden");
      } else {
        threeDsLink.classList.add("hidden");
      }
      setMessage(response.message, "success");
    } catch (error) {
      setMessage(error.message, "error");
    } finally {
      submitButton.disabled = false;
    }
  });

  loadConfig().catch((error) => {
    configStatus.textContent = "Error";
    configStatus.className = "status-pill error";
    environmentLabel.textContent = "Config unavailable";
    setMessage(error.message, "error");
  });
})();
