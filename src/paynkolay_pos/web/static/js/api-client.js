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
    getLatestReport() {
      return requestJson("/api/reports/latest");
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
