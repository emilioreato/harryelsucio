async function requestJson(url, options = {}) {
  const { timeoutMs = 15000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...fetchOptions, signal: controller.signal });
    let payload = {};
    try {
      payload = await response.json();
    } catch (cause) {
      if (cause?.name === "AbortError") throw cause;
      if (response.ok) throw new Error("El motor devolvió una respuesta que no se pudo interpretar.");
    }
    if (!response.ok) {
      throw new Error(payload.error || `Error HTTP ${response.status}`);
    }
    return payload;
  } catch (cause) {
    if (cause?.name === "AbortError") {
      const error = new Error("El motor local ha tardado demasiado en responder. Comprueba la conexión e inténtalo de nuevo.");
      error.name = "TimeoutError";
      throw error;
    }
    throw cause;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export const api = {
  scenes: () => requestJson("/api/scenes"),
  detectors: () => requestJson("/api/detectors"),
  analyze: (request) => requestJson("/api/analyze", {
    method: "POST",
    timeoutMs: 120000,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }),
  job: (jobId) => requestJson(`/api/jobs/${jobId}`),
  layerUrl: (jobId, name) => `/api/jobs/${jobId}/layers/${name}.png`,
  async downloadLayer(jobId, name) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(api.layerUrl(jobId, name), { signal: controller.signal });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || "No se pudo preparar el archivo.");
      }
      return await response.blob();
    } catch (cause) {
      if (cause?.name === "AbortError") {
        throw new Error("La descarga ha tardado demasiado. Comprueba la conexión e inténtalo de nuevo.");
      }
      throw cause;
    } finally {
      window.clearTimeout(timeoutId);
    }
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
