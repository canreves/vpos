(function () {
  const runtimeStatus = document.getElementById("runtime-status");
  const readinessStatus = document.getElementById("readiness-status");
  const cardsStatus = document.getElementById("cards-status");
  const scenariosStatus = document.getElementById("scenarios-status");
  const issueList = document.getElementById("settings-issues");
  const cardTable = document.getElementById("settings-cards");
  const message = document.getElementById("settings-message");

  const fields = {
    environment: document.getElementById("settings-environment"),
    configSource: document.getElementById("settings-config-source"),
    merchant: document.getElementById("settings-merchant"),
    terminal: document.getElementById("settings-terminal"),
    cancelKey: document.getElementById("settings-cancel-key"),
    callback: document.getElementById("settings-callback"),
    cardCount: document.getElementById("settings-card-count"),
    scenarioCount: document.getElementById("settings-scenario-count"),
    issueCount: document.getElementById("settings-issue-count"),
    scenarioSource: document.getElementById("settings-scenario-source"),
    scenarioTags: document.getElementById("settings-scenario-tags"),
  };

  function setStatus(element, text, kind) {
    element.textContent = text;
    element.className = `status-pill ${kind}`;
  }

  function text(value) {
    return value || "-";
  }

  function yesNo(value) {
    return value ? "Yes" : "No";
  }

  function renderIssues(readiness) {
    issueList.replaceChildren();
    if (!readiness.checked) {
      const item = document.createElement("li");
      item.textContent = readiness.message || "Readiness has not been checked.";
      issueList.append(item);
      return;
    }
    if (readiness.issues.length === 0) {
      const item = document.createElement("li");
      item.textContent = "No readiness issues.";
      issueList.append(item);
      return;
    }
    issueList.append(
      ...readiness.issues.map((issue) => {
        const item = document.createElement("li");
        item.textContent = `${issue.code}: ${issue.message}`;
        return item;
      }),
    );
  }

  function renderCards(cards) {
    cardTable.replaceChildren();
    cardTable.append(
      ...cards.map((card) => {
        const row = document.createElement("tr");
        for (const value of [
          card.alias,
          card.brand.toUpperCase(),
          yesNo(card.requires_3ds),
          yesNo(card.has_expected_otp),
        ]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        return row;
      }),
    );
  }

  function renderOverview(overview) {
    if (!overview.runtime_configured) {
      setStatus(runtimeStatus, "Missing", "error");
      setStatus(readinessStatus, "Blocked", "error");
      setStatus(cardsStatus, "0", "neutral");
      setStatus(scenariosStatus, overview.scenarios.configured ? "Loaded" : "Missing", "neutral");
      fields.configSource.textContent = text(overview.config_source);
      fields.scenarioSource.textContent = text(overview.scenarios.source);
      fields.scenarioCount.textContent = String(overview.scenarios.scenario_count);
      fields.issueCount.textContent = "-";
      fields.scenarioTags.textContent = overview.scenarios.tags.join(", ") || "-";
      renderIssues(overview.readiness);
      renderCards([]);
      message.textContent = overview.message || "Runtime config is not loaded.";
      return;
    }

    setStatus(runtimeStatus, "Configured", "success");
    setStatus(
      readinessStatus,
      overview.readiness.ready ? "Ready" : "Needs input",
      overview.readiness.ready ? "success" : "error",
    );
    setStatus(cardsStatus, String(overview.card_count), "neutral");
    setStatus(scenariosStatus, overview.scenarios.configured ? "Loaded" : "Missing", "neutral");

    fields.environment.textContent = text(overview.active_environment);
    fields.configSource.textContent = text(overview.config_source);
    fields.merchant.textContent = overview.merchant ? overview.merchant.merchant_id : "-";
    fields.terminal.textContent = overview.merchant ? overview.merchant.terminal_id : "-";
    fields.cancelKey.textContent = overview.merchant
      ? yesNo(overview.merchant.has_cancel_refund_key)
      : "-";
    fields.callback.textContent = yesNo(overview.callback_configured);
    fields.cardCount.textContent = String(overview.card_count);
    fields.scenarioCount.textContent = String(overview.scenarios.scenario_count);
    fields.issueCount.textContent = String(overview.readiness.issue_count);
    fields.scenarioSource.textContent = text(overview.scenarios.source);
    fields.scenarioTags.textContent = overview.scenarios.tags.join(", ") || "-";

    renderIssues(overview.readiness);
    renderCards(overview.cards);
    message.textContent = overview.readiness.ready
      ? "Config and scenario catalogue are ready for local validation."
      : "Review readiness issues before running sandbox or local scenario checks.";
  }

  window.PaynkolayApi.getConfigOverview()
    .then(renderOverview)
    .catch((error) => {
      setStatus(runtimeStatus, "Error", "error");
      setStatus(readinessStatus, "Error", "error");
      message.textContent = error.message;
    });
})();
