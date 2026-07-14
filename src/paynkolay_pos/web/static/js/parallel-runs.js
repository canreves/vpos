(function () {
  const parallelRunStatus = document.getElementById("parallel-run-status");
  const parallelMode = document.getElementById("parallel-mode");
  const parallelAmount = document.getElementById("parallel-amount");
  const parallelConcurrency = document.getElementById("parallel-concurrency");
  const parallelRandomCountField = document.getElementById("parallel-random-count-field");
  const parallelRandomCount = document.getElementById("parallel-random-count");
  const parallelManualPanel = document.getElementById("parallel-manual-panel");
  const parallelCardSelect = document.getElementById("parallel-card-select");
  const parallelRepeatCount = document.getElementById("parallel-repeat-count");
  const parallelAddCard = document.getElementById("parallel-add-card");
  const parallelSelectionBody = document.getElementById("parallel-selection-body");
  const parallelRunButton = document.getElementById("parallel-run-button");
  const parallelRunId = document.getElementById("parallel-run-id");
  const parallelProgress = document.getElementById("parallel-progress");
  const parallelSelectedTotal = document.getElementById("parallel-selected-total");
  const parallelMessage = document.getElementById("parallel-message");
  const parallelResultsBody = document.getElementById("parallel-results-body");
  let parallelRunPoll = null;
  let parallelSelections = [];

  function setParallelRunStatus(text, kind) {
    parallelRunStatus.textContent = text;
    parallelRunStatus.className = `status-pill ${kind}`;
  }

  function formatDuration(value) {
    if (value === null || value === undefined) {
      return "-";
    }
    if (value < 1000) {
      return `${value} ms`;
    }
    return `${(value / 1000).toFixed(2)} s`;
  }

  function renderParallelMode() {
    const randomMode = parallelMode.value === "random";
    parallelRandomCountField.classList.toggle("hidden", !randomMode);
    parallelManualPanel.classList.toggle("hidden", randomMode);
    renderParallelSelections();
  }

  function renderParallelSelections() {
    const total = parallelSelections.reduce((sum, selection) => sum + selection.repeat_count, 0);
    parallelSelectionBody.replaceChildren(
      ...parallelSelections.map((selection, index) => {
        const row = document.createElement("tr");
        for (const value of [selection.alias, String(selection.repeat_count)]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        const actionCell = document.createElement("td");
        const removeButton = document.createElement("button");
        removeButton.className = "secondary-action";
        removeButton.type = "button";
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", () => {
          parallelSelections.splice(index, 1);
          renderParallelSelections();
        });
        actionCell.append(removeButton);
        row.append(actionCell);
        return row;
      }),
    );
    parallelSelectedTotal.textContent = String(total);
    parallelRunButton.disabled = parallelMode.value === "manual" && total === 0;
  }

  function loadParallelCards() {
    window.PaynkolayApi.getCards()
      .then((payload) => {
        parallelCardSelect.replaceChildren(
          ...payload.cards.map((card) => {
            const option = document.createElement("option");
            option.value = card.alias;
            option.textContent = `${card.alias} (${card.brand.toUpperCase()} ${card.flow_type})`;
            return option;
          }),
        );
      })
      .catch((error) => {
        parallelMessage.textContent = error.message;
        setParallelRunStatus("Config error", "error");
      });
  }

  function parallelPayload() {
    const mode = parallelMode.value;
    const payload = {
      mode,
      amount: parallelAmount.value,
      currency: "TRY",
      concurrency: Number(parallelConcurrency.value),
    };
    if (mode === "random") {
      payload.random_count = Number(parallelRandomCount.value);
      return payload;
    }
    payload.manual_cards = parallelSelections;
    return payload;
  }

  function renderParallelRun(run) {
    parallelRunId.textContent = run.run_id;
    parallelProgress.textContent = `${run.completed + run.failed}/${run.total}`;
    parallelMessage.textContent = run.message;
    parallelRunButton.disabled = run.status === "running";
    if (run.status === "running") {
      setParallelRunStatus("Running", "neutral");
      startParallelPolling(run.run_id);
    } else if (run.status === "completed") {
      setParallelRunStatus("Completed", "success");
    } else if (run.status === "completed_with_failures") {
      setParallelRunStatus("Attention", "error");
    } else if (run.status === "failed") {
      setParallelRunStatus("Failed", "error");
    } else {
      setParallelRunStatus("Idle", "neutral");
    }
    renderParallelItems(run.items || []);
  }

  function renderParallelItems(items) {
    parallelResultsBody.replaceChildren(
      ...items.map((item) => {
        const row = document.createElement("tr");
        const provider = [item.provider_response_code, item.provider_response_data]
          .filter(Boolean)
          .join(" ");
        const values = [
          item.card_alias,
          String(item.attempt_index),
          item.order_id,
          item.status,
          item.classification,
          provider || item.error_message || "-",
          item.payment_list_status || item.payment_list_error || "-",
          formatAutomation(item.three_ds_automation),
        ];
        for (const value of values) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        const threeDsCell = document.createElement("td");
        if (item.three_ds_url) {
          const link = document.createElement("a");
          link.href = item.three_ds_url;
          link.textContent = "Open";
          threeDsCell.append(link);
        } else {
          threeDsCell.textContent = "-";
        }
        row.append(threeDsCell);

        const durationCell = document.createElement("td");
        durationCell.textContent = formatDuration(item.duration_ms);
        row.append(durationCell);
        return row;
      }),
    );
  }

  function formatAutomation(automation) {
    if (!automation) {
      return "-";
    }
    const source = automation.otp_source_type || "no-source";
    const submitted = automation.submitted ? "submitted" : "not-submitted";
    return `${automation.status} ${submitted} ${source}`;
  }

  function startParallelPolling(runId) {
    if (parallelRunPoll !== null) {
      return;
    }
    parallelRunPoll = window.setInterval(() => {
      window.PaynkolayApi.getParallelRun(runId)
        .then((run) => {
          renderParallelRun(run);
          if (run.status !== "running" && parallelRunPoll !== null) {
            window.clearInterval(parallelRunPoll);
            parallelRunPoll = null;
          }
        })
        .catch((error) => {
          parallelMessage.textContent = error.message;
          setParallelRunStatus("Error", "error");
          if (parallelRunPoll !== null) {
            window.clearInterval(parallelRunPoll);
            parallelRunPoll = null;
          }
        });
    }, 1500);
  }

  parallelMode.addEventListener("change", renderParallelMode);
  parallelRandomCount.addEventListener("input", renderParallelSelections);

  parallelAddCard.addEventListener("click", () => {
    if (!parallelCardSelect.value) {
      return;
    }
    const repeatCount = Number(parallelRepeatCount.value);
    const currentTotal = parallelSelections.reduce(
      (sum, selection) => sum + selection.repeat_count,
      0,
    );
    if (currentTotal + repeatCount > 10) {
      parallelMessage.textContent = "Manual selection can include at most 10 test items.";
      setParallelRunStatus("Limit", "error");
      return;
    }
    parallelSelections.push({
      alias: parallelCardSelect.value,
      repeat_count: repeatCount,
    });
    parallelMessage.textContent = "Selection updated.";
    setParallelRunStatus("Idle", "neutral");
    renderParallelSelections();
  });

  parallelRunButton.addEventListener("click", () => {
    parallelRunButton.disabled = true;
    parallelMessage.textContent = "Starting parallel run";
    setParallelRunStatus("Starting", "neutral");
    window.PaynkolayApi.createParallelRun(parallelPayload())
      .then(renderParallelRun)
      .catch((error) => {
        parallelRunButton.disabled = false;
        parallelMessage.textContent = error.message;
        setParallelRunStatus("Error", "error");
      });
  });

  renderParallelMode();
  renderParallelSelections();
  loadParallelCards();
})();
