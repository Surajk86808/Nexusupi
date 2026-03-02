const output = document.getElementById("output");
const tokenInput = document.getElementById("token");
const apiBaseInput = document.getElementById("apiBase");
const API_BASE_STORAGE_KEY = "nexusapi_api_base";
const TOKEN_STORAGE_KEY = "nexusapi_token";

function getDefaultApiBase() {
  // On Vercel, default to deployed Cloud Run backend.
  if (window.location.hostname.endsWith("vercel.app")) {
    return "https://nexusapi-994745516874.us-central1.run.app";
  }
  return "http://localhost:8000";
}

function loadStoredApiBase() {
  const stored = localStorage.getItem(API_BASE_STORAGE_KEY);
  const base = (stored || "").trim() || getDefaultApiBase();
  apiBaseInput.value = base;
}

function storeApiBase(base) {
  const normalized = (base || "").trim().replace(/\/$/, "");
  if (!normalized) {
    localStorage.removeItem(API_BASE_STORAGE_KEY);
    return;
  }
  localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
}

function loadStoredToken() {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    tokenInput.value = token;
  }
}

function storeToken(token) {
  if (!token) {
    return;
  }
  tokenInput.value = token;
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

function clearToken() {
  tokenInput.value = "";
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

function parseHashParams() {
  const hash = window.location.hash.replace(/^#/, "");
  const params = new URLSearchParams(hash);
  return params;
}

function handleOAuthCallbackFromHash() {
  const params = parseHashParams();
  const accessToken = params.get("access_token");
  if (!accessToken) {
    return;
  }
  storeToken(accessToken);
  history.replaceState({}, document.title, window.location.pathname + window.location.search);
  showResult("Google login successful. Token stored in browser.");
}

function getConfig() {
  const base = apiBaseInput.value.trim().replace(/\/$/, "");
  const token = tokenInput.value.trim();
  return { base, token };
}

async function apiCall(path, options = {}) {
  const { base, token } = getConfig();

  if (!base) {
    throw new Error("API Base URL is required.");
  }

  if (!/^https?:\/\//i.test(base)) {
    throw new Error("API Base URL must start with http:// or https://");
  }

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${base}${path}`, {
    ...options,
    headers,
  });

  const text = await response.text();
  let data;

  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }

  if (!response.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data;
}

function showResult(value) {
  output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function showError(error) {
  showResult({ error: error.message || String(error) });
}

document.getElementById("googleLoginBtn").addEventListener("click", () => {
  try {
    const { base } = getConfig();
    if (!base) {
      throw new Error("API Base URL is required.");
    }
    window.location.href = `${base}/auth/google`;
  } catch (error) {
    showError(error);
  }
});

document.getElementById("clearTokenBtn").addEventListener("click", () => {
  clearToken();
  showResult("Token cleared.");
});

tokenInput.addEventListener("change", () => {
  const token = tokenInput.value.trim();
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
});

apiBaseInput.addEventListener("change", () => {
  storeApiBase(apiBaseInput.value);
});

apiBaseInput.addEventListener("blur", () => {
  const normalized = apiBaseInput.value.trim().replace(/\/$/, "");
  apiBaseInput.value = normalized;
  storeApiBase(normalized);
});

document.getElementById("getMeBtn").addEventListener("click", async () => {
  try {
    showResult("Loading /me...");
    const data = await apiCall("/me", { method: "GET" });
    showResult(data);
  } catch (error) {
    showError(error);
  }
});

document.getElementById("balanceBtn").addEventListener("click", async () => {
  try {
    showResult("Loading /credits/balance...");
    const data = await apiCall("/credits/balance", { method: "GET" });
    showResult(data);
  } catch (error) {
    showError(error);
  }
});

document.getElementById("analyseBtn").addEventListener("click", async () => {
  try {
    const text = document.getElementById("analyseText").value;
    showResult("Posting /api/analyse...");
    const data = await apiCall("/api/analyse", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    showResult(data);
  } catch (error) {
    showError(error);
  }
});

document.getElementById("summariseBtn").addEventListener("click", async () => {
  try {
    const text = document.getElementById("summariseText").value;
    showResult("Posting /api/summarise...");
    const data = await apiCall("/api/summarise", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    showResult(data);

    if (data.job_id) {
      document.getElementById("jobId").value = data.job_id;
    }
  } catch (error) {
    showError(error);
  }
});

document.getElementById("jobStatusBtn").addEventListener("click", async () => {
  try {
    const jobId = document.getElementById("jobId").value.trim();

    if (!jobId) {
      throw new Error("Job ID is required.");
    }

    showResult(`Loading /api/jobs/${jobId}...`);
    const data = await apiCall(`/api/jobs/${jobId}`, { method: "GET" });
    showResult(data);
  } catch (error) {
    showError(error);
  }
});

loadStoredApiBase();
loadStoredToken();
handleOAuthCallbackFromHash();
