(function () {
  const status = document.getElementById("report-status");
  const path = document.getElementById("report-path");
  const entrypoint = document.getElementById("report-entrypoint");
  const message = document.getElementById("report-message");
  const help = document.getElementById("report-help");
  const historyStatus = document.getElementById("history-status");
  const historyPath = document.getElementById("history-path");
  const historyTotal = document.getElementById("history-total");
  const historyCounts = document.getElementById("history-counts");
  const historyDuration = document.getElementById("history-duration");
  const historyFinished = document.getElementById("history-finished");
  const historyMessage = document.getElementById("history-message");
  const historyTests = document.getElementById("history-tests");
  const credentialRunStatus = document.getElementById("credential-run-status");
  const credentialRunButton = document.getElementById("credential-run-button");
  const credentialRunStarted = document.getElementById("credential-run-started");
  const credentialRunFinished = document.getElementById("credential-run-finished");
  const credentialRunExit = document.getElementById("credential-run-exit");
  const credentialRunOutput = document.getElementById("credential-run-output");
  let credentialRunPoll = null;

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = `status-pill ${kind}`;
  }

  function setHistoryStatus(text, kind) {
    historyStatus.textContent = text;
    historyStatus.className = `status-pill ${kind}`;
  }

  function setCredentialRunStatus(text, kind) {
    credentialRunStatus.textContent = text;
    credentialRunStatus.className = `status-pill ${kind}`;
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

  function formatDate(value) {
    if (!value) {
      return "-";
    }
    return new Date(value).toLocaleString();
  }

  function renderHistory(history) {
    historyPath.textContent = history.results_path;
    historyMessage.textContent = history.message;
    historyTests.replaceChildren();

    if (!history.available || !history.latest) {
      historyTotal.textContent = "-";
      historyCounts.textContent = "-";
      historyDuration.textContent = "-";
      historyFinished.textContent = "-";
      setHistoryStatus("Not generated", "neutral");
      return;
    }

    const latest = history.latest;
    historyTotal.textContent = String(latest.total);
    historyCounts.textContent = [
      `passed: ${latest.passed}`,
      `failed: ${latest.failed}`,
      `broken: ${latest.broken}`,
      `skipped: ${latest.skipped}`,
      `unknown: ${latest.unknown}`,
    ].join(", ");
    historyDuration.textContent = formatDuration(latest.duration_ms);
    historyFinished.textContent = formatDate(latest.finished_at);
    const hasFailures = latest.failed || latest.broken;
    setHistoryStatus(hasFailures ? "Attention" : "Passed", hasFailures ? "error" : "success");

    historyTests.append(
      ...latest.recent_tests.map((test) => {
        const row = document.createElement("tr");
        for (const value of [
          test.name,
          test.suite || "-",
          test.status,
          formatDuration(test.duration_ms),
        ]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        return row;
      }),
    );
  }

  function renderCredentialRun(run) {
    credentialRunStarted.textContent = formatDate(run.started_at);
    credentialRunFinished.textContent = formatDate(run.finished_at);
    credentialRunExit.textContent = run.exit_code === null ? "-" : String(run.exit_code);
    credentialRunOutput.textContent = run.output_tail || run.message;
    credentialRunButton.disabled = run.status === "running";

    if (run.status === "running") {
      setCredentialRunStatus("Running", "neutral");
      startCredentialRunPolling();
      return;
    }
    if (run.status === "passed") {
      setCredentialRunStatus("Passed", "success");
      refreshHistory();
      return;
    }
    if (run.status === "failed") {
      setCredentialRunStatus("Failed", "error");
      refreshHistory();
      return;
    }
    setCredentialRunStatus("Local/mock", "neutral");
  }

  function refreshHistory() {
    window.PaynkolayApi.getReportHistory().then(renderHistory).catch((error) => {
      historyMessage.textContent = error.message;
      setHistoryStatus("Error", "error");
    });
  }

  function refreshCredentialRun() {
    window.PaynkolayApi.getCredentialReportRun().then(renderCredentialRun).catch((error) => {
      credentialRunOutput.textContent = error.message;
      setCredentialRunStatus("Error", "error");
    });
  }

  function startCredentialRunPolling() {
    if (credentialRunPoll !== null) {
      return;
    }
    credentialRunPoll = window.setInterval(() => {
      window.PaynkolayApi.getCredentialReportRun()
        .then((run) => {
          renderCredentialRun(run);
          if (run.status !== "running" && credentialRunPoll !== null) {
            window.clearInterval(credentialRunPoll);
            credentialRunPoll = null;
          }
        })
        .catch((error) => {
          credentialRunOutput.textContent = error.message;
          setCredentialRunStatus("Error", "error");
          if (credentialRunPoll !== null) {
            window.clearInterval(credentialRunPoll);
            credentialRunPoll = null;
          }
        });
    }, 2000);
  }

  function renderReport(report) {
    path.textContent = report.report_path;
    entrypoint.textContent = report.entrypoint || "-";
    message.textContent = report.message;

    if (report.available) {
      setStatus("Available", "success");
      help.textContent = "Open the Allure report with allure open allure-report.";
      return;
    }

    setStatus("Not generated", "neutral");
    help.textContent = "Generate the report with make report, then refresh this page.";
  }

  window.PaynkolayApi.getLatestReport()
    .then(renderReport)
    .catch((error) => {
      path.textContent = "-";
      entrypoint.textContent = "-";
      message.textContent = error.message;
      setStatus("Error", "error");
      help.textContent = "Report status could not be loaded.";
    });

  window.PaynkolayApi.getReportHistory()
    .then(renderHistory)
    .catch((error) => {
      historyPath.textContent = "-";
      historyTotal.textContent = "-";
      historyCounts.textContent = "-";
      historyDuration.textContent = "-";
      historyFinished.textContent = "-";
      historyMessage.textContent = error.message;
      historyTests.replaceChildren();
      setHistoryStatus("Error", "error");
    });

  credentialRunButton.addEventListener("click", () => {
    credentialRunButton.disabled = true;
    setCredentialRunStatus("Starting", "neutral");
    window.PaynkolayApi.startCredentialReportRun()
      .then(renderCredentialRun)
      .catch((error) => {
        credentialRunButton.disabled = false;
        credentialRunOutput.textContent = error.message;
        setCredentialRunStatus("Error", "error");
      });
  });

  refreshCredentialRun();
})();
