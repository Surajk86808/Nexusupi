const output = document.getElementById("output");
const tokenInput = document.getElementById("token");
const apiBaseInput = document.getElementById("apiBase");

function loadStoredToken() {
  const token = localStorage.getItem("nexusapi_token");
  if (token) {
    tokenInput.value = token;
  }
}

function storeToken(token) {
  if (!token) {
    return;
  }
  tokenInput.value = token;
  localStorage.setItem("nexusapi_token", token);
}

function clearToken() {
  tokenInput.value = "";
  localStorage.removeItem("nexusapi_token");
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
    localStorage.setItem("nexusapi_token", token);
  } else {
    localStorage.removeItem("nexusapi_token");
  }
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

loadStoredToken();
handleOAuthCallbackFromHash();
