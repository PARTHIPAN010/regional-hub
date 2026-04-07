const API_BASE = window.location.origin;
const ADMIN_STORAGE_KEY = "regionalHubAdminKey";

const loginPanel = document.getElementById("loginPanel");
const dashboardPanel = document.getElementById("dashboardPanel");
const adminStatusBanner = document.getElementById("adminStatusBanner");
const adminLoginForm = document.getElementById("adminLoginForm");
const adminPasswordInput = document.getElementById("adminPassword");
const loginButton = document.getElementById("loginButton");
const refreshButton = document.getElementById("refreshButton");
const exportButton = document.getElementById("exportButton");
const logoutButton = document.getElementById("logoutButton");
const registrationCount = document.getElementById("registrationCount");
const registrationsBody = document.getElementById("registrationsBody");
const emptyRegistrations = document.getElementById("emptyRegistrations");

let adminKey = sessionStorage.getItem(ADMIN_STORAGE_KEY) || "";

const setStatus = (type, text) => {
  adminStatusBanner.hidden = false;
  adminStatusBanner.className = `status-banner ${type}`;
  adminStatusBanner.textContent = text;
};

const clearStatus = () => {
  adminStatusBanner.hidden = true;
  adminStatusBanner.className = "status-banner";
  adminStatusBanner.textContent = "";
};

const setAuthMode = (authenticated) => {
  loginPanel.hidden = authenticated;
  dashboardPanel.hidden = !authenticated;
};

const getAdminHeaders = () => {
  return {
    "X-Admin-Key": adminKey,
  };
};

const escapeHtml = (value) => {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
};

const renderRegistrations = (items) => {
  registrationsBody.innerHTML = "";

  if (!items.length) {
    emptyRegistrations.hidden = false;
    return;
  }

  emptyRegistrations.hidden = true;
  const rowsHtml = items
    .map(item => {
      const signatureCell = item["E-Signature"]
        ? `<img class="signature-preview" src="${item["E-Signature"]}" alt="Signature for ${escapeHtml(item["Visitor Name"])}" />`
        : `<span class="signature-missing-copy">No signature</span>`;

      return `
        <tr>
          <td>${escapeHtml(item["S.No"])}</td>
          <td>${escapeHtml(item["Date"])}</td>
          <td>${escapeHtml(item["Visitor Name"])}</td>
          <td>${escapeHtml(item["Organization Name"])}</td>
          <td>${escapeHtml(item["Contact Number"])}</td>
          <td>${escapeHtml(item["Mail ID"])}</td>
          <td>${escapeHtml(item["Region"])}</td>
          <td>${escapeHtml(item["Purpose"])}</td>
          <td>${escapeHtml(item["Further Support"] || "None requested")}</td>
          <td>${signatureCell}</td>
        </tr>
      `;
    })
    .join("");

  registrationsBody.innerHTML = rowsHtml;
};

const handleUnauthorized = () => {
  adminKey = "";
  sessionStorage.removeItem(ADMIN_STORAGE_KEY);
  setAuthMode(false);
  setStatus("error", "Admin session expired. Please enter the password again.");
  adminPasswordInput.focus();
};

const loadRegistrations = async () => {
  const response = await fetch(`${API_BASE}/admin/registrations`, {
    headers: getAdminHeaders(),
  });

  const result = await response.json();
  if (response.status === 401) {
    handleUnauthorized();
    return false;
  }

  if (!response.ok) {
    throw new Error(result.detail || "Could not load registrations.");
  }

  registrationCount.textContent = `${result.count} registration${result.count === 1 ? "" : "s"}`;
  renderRegistrations(result.items || []);
  return true;
};

adminLoginForm.addEventListener("submit", async event => {
  event.preventDefault();
  clearStatus();

  const password = adminPasswordInput.value.trim();
  if (!password) {
    setStatus("error", "Enter the admin password to continue.");
    adminPasswordInput.focus();
    return;
  }

  loginButton.disabled = true;
  loginButton.textContent = "Opening...";

  try {
    const response = await fetch(`${API_BASE}/admin/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ password }),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Admin login failed.");
    }

    adminKey = password;
    sessionStorage.setItem(ADMIN_STORAGE_KEY, adminKey);
    setAuthMode(true);
    setStatus("success", result.message || "Admin access granted.");
    await loadRegistrations();
  } catch (error) {
    setStatus("error", error.message || "Admin login failed.");
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "Open Dashboard";
  }
});

refreshButton.addEventListener("click", async () => {
  clearStatus();
  refreshButton.disabled = true;
  refreshButton.textContent = "Refreshing...";

  try {
    const loaded = await loadRegistrations();
    if (loaded) {
      setStatus("success", "Registrations refreshed.");
    }
  } catch (error) {
    setStatus("error", error.message || "Could not refresh registrations.");
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "Refresh";
  }
});

exportButton.addEventListener("click", async () => {
  clearStatus();
  exportButton.disabled = true;
  exportButton.textContent = "Exporting...";

  try {
    const response = await fetch(`${API_BASE}/admin/export`, {
      headers: getAdminHeaders(),
    });

    if (response.status === 401) {
      handleUnauthorized();
      return;
    }

    if (!response.ok) {
      let detail = "Could not export registrations.";
      try {
        const result = await response.json();
        detail = result.detail || detail;
      } catch (error) {
        detail = "Could not export registrations.";
      }
      throw new Error(detail);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const disposition = response.headers.get("Content-Disposition") || "";
    const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
    const filename = filenameMatch?.[1] || "regional-hub-registrations.xlsx";
    const link = document.createElement("a");

    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setStatus("success", "Export started.");
  } catch (error) {
    setStatus("error", error.message || "Could not export registrations.");
  } finally {
    exportButton.disabled = false;
    exportButton.textContent = "Export XLSX";
  }
});

logoutButton.addEventListener("click", () => {
  adminKey = "";
  sessionStorage.removeItem(ADMIN_STORAGE_KEY);
  adminLoginForm.reset();
  registrationsBody.innerHTML = "";
  emptyRegistrations.hidden = true;
  setAuthMode(false);
  setStatus("success", "Logged out from admin dashboard.");
  adminPasswordInput.focus();
});

if (adminKey) {
  setAuthMode(true);
  loadRegistrations()
    .then(loaded => {
      if (loaded) {
        setStatus("success", "Admin access restored.");
      }
    })
    .catch(error => {
      handleUnauthorized();
      setStatus("error", error.message || "Could not restore admin session.");
    });
} else {
  setAuthMode(false);
}
