(function () {
  async function requestJson(url, options) {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => item.msg).join("; ")
        : payload.detail || response.statusText;
      throw new Error(detail);
    }
    return payload;
  }

  window.PaynkolayApi = {
    getConfig() {
      return requestJson("/api/config");
    },
    getConfigOverview() {
      return requestJson("/api/config/overview");
    },
    getCards() {
      return requestJson("/api/cards");
    },
    createCard(payload) {
      return requestJson("/api/cards", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    getInstallmentOptions(payload) {
      return requestJson("/api/installments/options", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    getLatestReport() {
      return requestJson("/api/reports/latest");
    },
    getReportHistory() {
      return requestJson("/api/reports/history");
    },
    getCredentialReportRun() {
      return requestJson("/api/reports/credential-run");
    },
    startCredentialReportRun() {
      return requestJson("/api/reports/credential-run", {
        method: "POST",
      });
    },
    createPayment(payload) {
      return requestJson("/api/payments", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    getPayment(orderId) {
      return requestJson(`/api/payments/${encodeURIComponent(orderId)}`);
    },
  };
})();
