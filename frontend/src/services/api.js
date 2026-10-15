async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `Error HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

export const api = {
  authStatus: () => requestJson("/api/auth/status"),
  login: (password) => requestJson("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  }),
  scenes: () => requestJson("/api/scenes"),
  detectors: () => requestJson("/api/detectors"),
  analyze: (request) => requestJson("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }),
  job: (jobId) => requestJson(`/api/jobs/${jobId}`),
  layerUrl: (jobId, name) => `/api/jobs/${jobId}/layers/${name}.png`,
  async downloadLayer(jobId, name) {
    const response = await fetch(api.layerUrl(jobId, name));
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "No se pudo preparar el archivo.");
    }
    return response.blob();
  },
};

export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`No se pudo leer ${file.name}.`));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}
