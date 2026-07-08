(function () {
  const status = document.getElementById("report-status");
  const path = document.getElementById("report-path");
  const entrypoint = document.getElementById("report-entrypoint");
  const message = document.getElementById("report-message");
  const help = document.getElementById("report-help");

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = `status-pill ${kind}`;
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
})();
