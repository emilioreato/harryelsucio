async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Error HTTP ${response.status}`);
  }
  return payload;
}

export const api = {
  mobileAccess: () => requestJson("/api/mobile-access"),
  scenes: () => requestJson("/api/scenes"),
  scenePreviewUrl: (sceneId, channel) => `/api/scenes/${encodeURIComponent(sceneId)}/preview/${channel}`,
  sceneImageUrl: (sceneId, channel) => `/api/scenes/${encodeURIComponent(sceneId)}/image/${channel}`,
  detectors: () => requestJson("/api/detectors"),
  analyze: (request) => requestJson("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }),
  job: (jobId) => requestJson(`/api/jobs/${jobId}`),
  checkpointUrl: (jobId, checkpointId) => `/api/jobs/${jobId}/checkpoints/${encodeURIComponent(checkpointId)}.jpg`,
  layerUrl: (jobId, name) => `/api/jobs/${jobId}/layers/${name}.png`,
  async downloadLayer(jobId, name) {
    const response = await fetch(api.layerUrl(jobId, name));
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "No se pudo preparar el archivo.");
    }
    return response.blob();
  },
  async downloadPackage(jobId, payload) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/package.zip`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.error || "No se pudo preparar el paquete completo.");
    }
    return response.blob();
  },
};

// La experiencia avanzada tiene rutas propias y almacena sus análisis por
// separado; solo comparte la lectura de escenas y utilidades de archivo.
export const advancedApi = {
  scenes: () => requestJson("/api/advanced/scenes"),
  scenePreviewUrl: (sceneId, channel) => (
    `/api/advanced/scenes/${encodeURIComponent(sceneId)}/preview/${channel}`
  ),
  analyze: (request) => requestJson("/api/advanced/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }),
  job: (jobId) => requestJson(`/api/advanced/jobs/${encodeURIComponent(jobId)}`),
  fireProgression: (jobId, scenario) => requestJson(
    `/api/advanced/jobs/${encodeURIComponent(jobId)}/fire-progression`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scenario),
    },
  ),
  layerUrl: (jobId, name) => (
    `/api/advanced/jobs/${encodeURIComponent(jobId)}/layers/${encodeURIComponent(name)}.png`
  ),
  async downloadLayer(jobId, name) {
    const response = await fetch(advancedApi.layerUrl(jobId, name));
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "No se pudo preparar la capa avanzada.");
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
