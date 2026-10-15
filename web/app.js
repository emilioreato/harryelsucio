"use strict";

const $ = (selector) => document.querySelector(selector);
const state = {
  source: "preloaded",
  scenes: [],
  detectors: [],
  jobId: null,
  jobLabel: "",
  metrics: null,
  grid: null,
  layer: "swir",
  showSegmentation: true,
  showMarks: true,
  tool: "view",
  marks: [],
  polygonClosed: false,
  inspectedPixel: null,
  imageUrl: null,
  settings: null,
};

const connectionDot = $("#connection-dot");
const connectionLabel = $("#connection-label");
const runButton = $("#run-analysis");
const runButtonText = runButton.querySelector("span:last-child");
const image = $("#analysis-image");
const stage = $("#image-stage");
const canvas = $("#mark-canvas");
const canvasContext = canvas.getContext("2d");
const KMEANS_WEIGHT_FIELDS = [
  ["swir_red", "weight-swir-red"],
  ["swir_chroma", "weight-swir-chroma"],
  ["true_green", "weight-true-green"],
  ["true_luminance", "weight-true-luminance"],
  ["swir_luminance", "weight-swir-luminance"],
  ["true_chroma", "weight-true-chroma"],
  ["swir_red_green", "weight-swir-red-green"],
  ["true_blue", "weight-true-blue"],
];
const KMEANS_WEIGHT_LABELS = {
  swir_red: "rojo SWIR",
  swir_chroma: "cromaticidad SWIR",
  true_green: "verdor True Color",
  true_luminance: "luminosidad True Color",
  swir_luminance: "luminosidad SWIR",
  true_chroma: "cromaticidad True Color",
  swir_red_green: "rojo/verde SWIR",
  true_blue: "azul True Color",
};
const SWIR_THRESHOLD_LABELS = {
  seed_red: "semilla rojo SWIR",
  grow_red: "crecimiento rojo SWIR",
  seed_red_green: "semilla rojo/verde SWIR",
  grow_red_green: "crecimiento rojo/verde SWIR",
  vegetation_max: "límite de verdor",
};
const SWIR_THRESHOLD_FIELDS = [
  ["seed_red", "swir-seed-red", 0.80, 0.9999],
  ["grow_red", "swir-grow-red", 0.50, 0.98],
  ["seed_red_green", "swir-seed-rg", 0.40, 0.99],
  ["grow_red_green", "swir-grow-rg", 0.30, 0.98],
  ["vegetation_max", "swir-vegetation-max", 0.50, 1],
];
const WATER_THRESHOLD_FIELDS = [
  ["true_color_darkness", "water-true-darkness", 0.20],
  ["swir_darkness", "water-swir-darkness", 0.10],
  ["swir_red_max", "water-swir-red", 0.55],
  ["swir_red_green_max", "water-swir-red-green", 0.55],
];

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Error HTTP ${response.status}`);
  return payload;
}

async function initialize() {
  bindEvents();
  syncViewerControls();
  renderNotes();
  try {
    const [scenesResponse, detectorsResponse] = await Promise.all([
      fetchJson("/api/scenes"),
      fetchJson("/api/detectors"),
    ]);
    state.scenes = scenesResponse.scenes || [];
    state.detectors = detectorsResponse.detectors || [];
    renderScenes();
    renderDetectors();
    setConnection(true, "Motor Python conectado");
  } catch (error) {
    setConnection(false, "No se pudo conectar con el motor local");
    showFormError(error.message);
    $("#scene-select").innerHTML = '<option value="">No se pudieron cargar las escenas</option>';
    runButton.disabled = true;
  }
}

function bindEvents() {
  document.querySelectorAll(".source-tab").forEach((button) => {
    button.addEventListener("click", () => setSource(button.dataset.source));
  });
  $("#run-analysis").addEventListener("click", runAnalysis);
  $("#detector-select").addEventListener("change", updateDetectorControls);
  $("#sensitivity").addEventListener("input", () => $("#sensitivity-value").value = $("#sensitivity").value);
  $("#num-classes").addEventListener("input", () => $("#classes-value").value = $("#num-classes").value);
  [
    ["fusion-kmeans-weight", "fusion-kmeans-weight-value"],
    ["fusion-swir-weight", "fusion-swir-weight-value"],
    ["fusion-threshold", "fusion-threshold-value"],
    ["smoke-cyan-weight", "smoke-cyan-weight-value"],
    ["smoke-luminance-weight", "smoke-luminance-weight-value"],
    ["smoke-neutrality-weight", "smoke-neutrality-weight-value"],
    ["smoke-threshold", "smoke-threshold-value"],
  ].forEach(([inputId, outputId]) => {
    $(`#${inputId}`).addEventListener("input", () => {
      $(`#${outputId}`).textContent = `${Math.round(Number($(`#${inputId}`).value) * 100)} %`;
    });
  });
  $("#reset-tuning").addEventListener("click", resetTuning);
  $("#keep-separate").addEventListener("change", () => {
    $("#max-distance").disabled = $("#keep-separate").checked;
  });
  document.querySelectorAll(".layer-choice").forEach((button) => {
    button.addEventListener("click", () => {
      state.layer = button.dataset.layer;
      if (state.layer === "candidates") {
        state.showSegmentation = true;
        $("#show-segmentation").checked = true;
      }
      syncViewerControls();
      updateImage();
    });
  });
  $("#show-segmentation").addEventListener("change", () => {
    state.showSegmentation = $("#show-segmentation").checked;
    if (!state.showSegmentation && state.layer === "candidates") state.layer = "true-color";
    syncViewerControls();
    updateImage();
  });
  $("#show-marks").addEventListener("change", () => {
    state.showMarks = $("#show-marks").checked;
    drawMarks();
  });
  document.querySelectorAll(".tool-button").forEach((button) => {
    button.addEventListener("click", () => setTool(button.dataset.tool));
  });
  stage.addEventListener("click", handleImageClick);
  image.addEventListener("load", () => {
    resizeCanvas();
    drawMarks();
  });
  window.addEventListener("resize", () => {
    resizeCanvas();
    drawMarks();
  });
  $("#undo-mark").addEventListener("click", undoMark);
  $("#close-polygon").addEventListener("click", closePolygon);
  $("#clear-marks").addEventListener("click", clearMarks);
  $("#download-map").addEventListener("click", () => downloadLayer("overlay-true-color", "pyroscope_mapa_segmentado.png"));
  $("#download-mask").addEventListener("click", () => downloadLayer("mask", "pyroscope_mascara_candidata.png"));
  $("#download-measurements").addEventListener("click", downloadMeasurements);
  $("#note-form").addEventListener("submit", addNote);
}

function setConnection(ready, label) {
  connectionDot.classList.toggle("is-ready", ready);
  connectionDot.classList.toggle("is-error", !ready);
  connectionLabel.textContent = label;
}

function renderScenes() {
  const select = $("#scene-select");
  select.replaceChildren();
  if (state.scenes.length === 0) {
    const option = new Option("No hay escenas disponibles", "");
    select.add(option);
    runButton.disabled = state.source === "preloaded";
    return;
  }
  for (const scene of state.scenes) select.add(new Option(scene.label, scene.id));
  runButton.disabled = false;
  syncSceneHeading();
  select.addEventListener("change", syncSceneHeading);
}

function renderDetectors() {
  const select = $("#detector-select");
  select.replaceChildren();
  for (const detector of state.detectors) {
    select.add(new Option(detector.name, detector.id));
  }
  updateDetectorControls();
}

function updateDetectorControls() {
  const detector = state.detectors.find((item) => item.id === $("#detector-select").value);
  const usesClasses = detector ? detector.uses_num_classes : true;
  $("#detector-help").textContent = detector ? detector.description : "";
  $("#classes-row").classList.toggle("is-hidden", !usesClasses);
  $("#num-classes").classList.toggle("is-hidden", !usesClasses);
  const method = detector ? detector.id : "kmeans";
  $("#fusion-adjustments").classList.toggle("is-hidden", method !== "fusion_ponderada");
  $("#kmeans-adjustments").classList.toggle("is-hidden", !["kmeans", "fusion_ponderada"].includes(method));
  $("#swir-adjustments").classList.toggle("is-hidden", !["swir_histeresis", "fusion_ponderada"].includes(method));
}

function resetTuning() {
  const defaults = {
    "weight-swir-red": 1.25,
    "weight-swir-chroma": 0.18,
    "weight-true-green": -0.62,
    "weight-true-luminance": -0.22,
    "weight-swir-luminance": -0.12,
    "weight-true-chroma": 0.10,
    "weight-swir-red-green": 0.22,
    "weight-true-blue": -0.30,
  };
  Object.entries(defaults).forEach(([id, value]) => $(`#${id}`).value = String(value));
  SWIR_THRESHOLD_FIELDS.forEach(([, id]) => $(`#${id}`).value = "");
  $("#fusion-kmeans-weight").value = "0.5";
  $("#fusion-swir-weight").value = "0.5";
  $("#fusion-threshold").value = "0.55";
  $("#smoke-cyan-weight").value = "0.65";
  $("#smoke-luminance-weight").value = "0.20";
  $("#smoke-neutrality-weight").value = "0.15";
  $("#smoke-threshold").value = "0.55";
  WATER_THRESHOLD_FIELDS.forEach(([, id, value]) => $(`#${id}`).value = String(value));
  [
    ["fusion-kmeans-weight", "fusion-kmeans-weight-value"],
    ["fusion-swir-weight", "fusion-swir-weight-value"],
    ["fusion-threshold", "fusion-threshold-value"],
    ["smoke-cyan-weight", "smoke-cyan-weight-value"],
    ["smoke-luminance-weight", "smoke-luminance-weight-value"],
    ["smoke-neutrality-weight", "smoke-neutrality-weight-value"],
    ["smoke-threshold", "smoke-threshold-value"],
  ].forEach(([inputId, outputId]) => {
    $(`#${outputId}`).textContent = `${Math.round(Number($(`#${inputId}`).value) * 100)} %`;
  });
}

function syncSceneHeading() {
  const option = $("#scene-select").selectedOptions[0];
  state.jobLabel = option ? option.textContent : "Selecciona una escena";
  if (!state.jobId) $("#analysis-scene").textContent = state.jobLabel;
}

function setSource(source) {
  state.source = source;
  document.querySelectorAll(".source-tab").forEach((button) => {
    const active = button.dataset.source === source;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $("#preloaded-source").classList.toggle("is-hidden", source !== "preloaded");
  $("#upload-source").classList.toggle("is-hidden", source !== "upload");
  runButton.disabled = source === "preloaded" && state.scenes.length === 0;
  showFormError("");
}

async function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`No se pudo leer ${file.name}.`));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}

function collectSettings() {
  const method = $("#detector-select").value;
  const detector = state.detectors.find((item) => item.id === method);
  const gsdText = $("#gsd").value.trim().replace(",", ".");
  const minimumArea = Number($("#minimum-area").value);
  const maxDistance = Number($("#max-distance").value);
  const gsd = gsdText === "" ? null : Number(gsdText);
  if (!Number.isFinite(minimumArea) || minimumArea < 0.01 || minimumArea > 1) {
    throw new Error("El área mínima debe estar entre 0,01 y 1 %.");
  }
  if (!$("#keep-separate").checked && (!Number.isInteger(maxDistance) || maxDistance < 3 || maxDistance > 20)) {
    throw new Error("El radio máximo debe estar entre 3 y 20 %.");
  }
  if (gsd !== null && (!Number.isFinite(gsd) || gsd <= 0)) {
    throw new Error("El GSD debe ser un número positivo en metros por píxel.");
  }
  const kmeansWeights = Object.fromEntries(KMEANS_WEIGHT_FIELDS.map(([key, id]) => {
    const value = Number($(`#${id}`).value);
    if (!Number.isFinite(value) || value < -3 || value > 3) {
      throw new Error("Cada peso de K-Means debe estar entre -3 y 3.");
    }
    return [key, value];
  }));
  const swirThresholds = Object.fromEntries(SWIR_THRESHOLD_FIELDS.map(([key, id, minimum, maximum]) => {
    const text = $(`#${id}`).value.trim().replace(",", ".");
    if (text === "") return [key, null];
    const value = Number(text);
    if (!Number.isFinite(value) || value < minimum || value > maximum) {
      throw new Error(`El percentil ${key} debe estar entre ${minimum} y ${maximum}.`);
    }
    return [key, value];
  }));
  const sensitivity = Number($("#sensitivity").value);
  const baseSeedRed = 0.994 - (sensitivity - 1) * 0.006;
  const baseGrowRed = 0.94 - (sensitivity - 1) * 0.010;
  const baseSeedRg = 0.82 - (sensitivity - 1) * 0.005;
  const baseGrowRg = 0.68 - (sensitivity - 1) * 0.012;
  if ((swirThresholds.grow_red ?? baseGrowRed) > (swirThresholds.seed_red ?? baseSeedRed)) {
    throw new Error("El percentil de crecimiento SWIR debe ser menor o igual al de semilla.");
  }
  if ((swirThresholds.grow_red_green ?? baseGrowRg) > (swirThresholds.seed_red_green ?? baseSeedRg)) {
    throw new Error("El percentil rojo/verde de crecimiento debe ser menor o igual al de semilla.");
  }
  const fusionWeights = [Number($("#fusion-kmeans-weight").value), Number($("#fusion-swir-weight").value)];
  if (method === "fusion_ponderada" && fusionWeights[0] + fusionWeights[1] === 0) {
    throw new Error("En la fusión, deja al menos un peso de algoritmo por encima de cero.");
  }
  const smokeWeights = {
    cyan: Number($("#smoke-cyan-weight").value),
    luminance: Number($("#smoke-luminance-weight").value),
    neutrality: Number($("#smoke-neutrality-weight").value),
  };
  if (Object.values(smokeWeights).some((value) => !Number.isFinite(value) || value < 0 || value > 1)
      || Object.values(smokeWeights).every((value) => value === 0)) {
    throw new Error("Los pesos del score de humo deben estar entre 0 y 1 y alguno debe ser positivo.");
  }
  const waterThresholds = Object.fromEntries(WATER_THRESHOLD_FIELDS.map(([key, id]) => {
    const value = Number($(`#${id}`).value);
    if (!Number.isFinite(value) || value < 0.01 || value > 0.99) {
      throw new Error(`El percentil de agua ${key} debe estar entre 0,01 y 0,99.`);
    }
    return [key, value];
  }));
  return {
    method,
    sensitivity,
    num_classes: detector && detector.uses_num_classes ? Number($("#num-classes").value) : 7,
    minimum_area_pct: minimumArea,
    max_distance_pct: $("#keep-separate").checked ? 10 : maxDistance,
    keep_separate: $("#keep-separate").checked,
    gsd_m_per_px: gsd,
    advanced: {
      kmeans_weights: kmeansWeights,
      swir_thresholds: swirThresholds,
      fusion_kmeans_weight: fusionWeights[0],
      fusion_swir_weight: fusionWeights[1],
      fusion_threshold: Number($("#fusion-threshold").value),
      smoke_weights: smokeWeights,
      smoke_threshold: Number($("#smoke-threshold").value),
      water_thresholds: waterThresholds,
    },
  };
}

async function runAnalysis() {
  showFormError("");
  let request;
  try {
    const settings = collectSettings();
    state.settings = settings;
    if (state.source === "preloaded") {
      const scene = $("#scene-select").value;
      if (!scene) throw new Error("Selecciona una escena precargada.");
      request = { source: "preloaded", scene, settings };
    } else {
      const trueFile = $("#true-file").files[0];
      const swirFile = $("#swir-file").files[0];
      if (!trueFile || !swirFile) throw new Error("Carga las dos imágenes: True Color y SWIR.");
      state.jobLabel = "Pareja cargada";
      request = {
        source: "upload",
        true_color: await fileToBase64(trueFile),
        swir: await fileToBase64(swirFile),
        settings,
      };
    }
    state.jobId = null;
    state.metrics = null;
    state.grid = null;
    state.marks = [];
    state.polygonClosed = false;
    state.inspectedPixel = null;
    state.imageUrl = null;
    image.hidden = true;
    canvas.hidden = true;
    $("#empty-state").hidden = false;
    $("#empty-state strong").textContent = "Procesando las imágenes";
    $("#empty-state span:last-child").textContent = "La vista aparecerá al terminar la segmentación.";
    $("#analysis-scene").textContent = state.jobLabel;
    $("#metrics-grid").hidden = true;
    $("#result-caveat").hidden = true;
    $("#result-state").classList.remove("is-error");
    $("#result-state").textContent = "Análisis en curso…";
    setProgress("Preparando análisis", 0);
    enableViewerControls(false);
    setRunning(true);

    const response = await fetchJson("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    state.jobId = response.job_id;
    await pollJob();
  } catch (error) {
    showFormError(error.message);
    $("#result-state").classList.add("is-error");
    $("#result-state").textContent = error.message;
    setProgress("No se pudo iniciar", 0);
    setRunning(false);
  }
}

function setRunning(running) {
  runButton.disabled = running || (state.source === "preloaded" && state.scenes.length === 0);
  runButtonText.textContent = running ? "Analizando…" : "Iniciar segmentación";
  if (running) {
    connectionDot.classList.remove("is-ready", "is-error");
    connectionLabel.textContent = "El motor Python está procesando";
  } else {
    setConnection(true, "Motor Python conectado");
  }
}

function setProgress(label, percentage) {
  const value = Math.max(0, Math.min(100, Number(percentage) || 0));
  $("#progress-label").textContent = label;
  $("#progress-value").textContent = `${value}%`;
  $("#progress-fill").style.width = `${value}%`;
  $("#progress-track").setAttribute("aria-valuenow", String(value));
}

async function pollJob() {
  while (state.jobId) {
    const job = await fetchJson(`/api/jobs/${state.jobId}`);
    setProgress(job.stage || "Procesando", job.progress || 0);
    if (job.state === "complete") {
      state.metrics = job.metrics;
      state.grid = job.grid;
      showCompletedResult(job);
      setRunning(false);
      return;
    }
    if (job.state === "error") {
      const message = job.error || "No se pudo completar el análisis.";
      $("#result-state").classList.add("is-error");
      $("#result-state").textContent = message;
      showFormError(message);
      setProgress(job.stage || "Error en el análisis", job.progress || 0);
      setRunning(false);
      return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 650));
  }
}

function showCompletedResult(job) {
  const metrics = job.metrics;
  $("#analysis-scene").textContent = state.jobLabel;
  $("#result-state").classList.remove("is-error");
  $("#result-state").textContent = `Detector: ${metrics.detector}. Revisa la hipótesis antes de usarla.`;
  $("#metrics-grid").hidden = false;
  $("#result-caveat").hidden = false;
  $("#metric-coverage").textContent = `${formatNumber(metrics.coverage_pct, 1)} %`;
  $("#metric-area").textContent = formatArea(metrics.area, metrics.area_unit);
  $("#metric-perimeter").textContent = formatLength(metrics.perimeter, metrics.perimeter_unit);
  $("#metric-smoke").textContent = `${formatNumber(metrics.smoke_pct, 1)} %`;
  const tuning = describeTuning(state.settings);
  $("#analysis-details").textContent = `${metrics.detector}. Rejilla ${metrics.grid_width} × ${metrics.grid_height} px. Píxeles excluidos como agua: ${formatNumber(metrics.water_excluded, 0)}. Regiones remotas descartadas: ${metrics.remote_regions_discarded}. ${metrics.gsd_x_m ? `GSD efectivo ${formatNumber(metrics.gsd_x_m, 3)} × ${formatNumber(metrics.gsd_y_m, 3)} m/píxel.` : "Sin GSD; las medidas se expresan en píxeles."} ${tuning}`;
  enableViewerControls(true);
  updateImage();
}

function describeTuning(settings) {
  if (!settings) return "";
  const advanced = settings.advanced;
  const smoke = advanced.smoke_weights;
  const sharedSummary = `Humo: cian ${formatNumber(smoke.cyan, 2)}, luminosidad ${formatNumber(smoke.luminance, 2)}, neutralidad ${formatNumber(smoke.neutrality, 2)}, umbral ${formatNumber(advanced.smoke_threshold, 2)}. Agua: ${WATER_THRESHOLD_FIELDS.map(([key]) => `${key} ${formatNumber(advanced.water_thresholds[key], 2)}`).join(", ")}.`;
  if (settings.method === "fusion_ponderada") {
    const k = Math.round(advanced.fusion_kmeans_weight * 100);
    const s = Math.round(advanced.fusion_swir_weight * 100);
    const threshold = Math.round(advanced.fusion_threshold * 100);
    const swir = SWIR_THRESHOLD_FIELDS
      .filter(([key]) => advanced.swir_thresholds[key] !== null)
      .map(([key]) => `${SWIR_THRESHOLD_LABELS[key]} ${formatNumber(advanced.swir_thresholds[key], 3)}`);
    const swirSummary = swir.length ? `SWIR: ${swir.join(", ")}.` : "Umbrales SWIR automáticos.";
    const kmeans = KMEANS_WEIGHT_FIELDS
      .map(([name]) => `${KMEANS_WEIGHT_LABELS[name]} ${formatNumber(advanced.kmeans_weights[name], 2)}`)
      .join(", ");
    return `Fusión: pesos K-Means ${k} %, SWIR ${s} %; voto mínimo ${threshold} %. Score K-Means: ${kmeans}. ${sharedSummary} ${swirSummary}`;
  }
  if (settings.method === "kmeans") {
    const changed = KMEANS_WEIGHT_FIELDS
      .map(([name]) => `${KMEANS_WEIGHT_LABELS[name]} ${formatNumber(advanced.kmeans_weights[name], 2)}`)
      .join(", ");
    return `Pesos del score K-Means: ${changed}. ${sharedSummary}`;
  }
  if (settings.method === "swir_histeresis") {
    const custom = SWIR_THRESHOLD_FIELDS
      .filter(([key]) => advanced.swir_thresholds[key] !== null)
      .map(([key]) => `${SWIR_THRESHOLD_LABELS[key]} ${formatNumber(advanced.swir_thresholds[key], 3)}`);
    return custom.length
      ? `Percentiles SWIR personalizados: ${custom.join(", ")}. ${sharedSummary}`
      : `Percentiles SWIR automáticos según sensibilidad y escena. ${sharedSummary}`;
  }
  return "";
}

function formatNumber(value, decimals = 0) {
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: decimals, minimumFractionDigits: decimals }).format(value);
}

function formatArea(value, unit) {
  if (unit === "m²" && value >= 10000) return `${formatNumber(value / 10000, 2)} ha`;
  if (unit === "m²") return `${formatNumber(value, 0)} m²`;
  return `${formatNumber(value, 0)} px²`;
}

function formatLength(value, unit) {
  if (unit === "m" && value >= 1000) return `${formatNumber(value / 1000, 2)} km`;
  return `${formatNumber(value, value < 10 ? 1 : 0)} ${unit}`;
}

function enableViewerControls(enabled) {
  document.querySelectorAll(".layer-choice").forEach((button) => button.disabled = !enabled);
  $("#show-segmentation").disabled = !enabled;
  $("#show-marks").disabled = !enabled;
  document.querySelectorAll(".tool-button").forEach((button) => button.disabled = !enabled);
  $("#download-map").disabled = !enabled;
  $("#download-mask").disabled = !enabled;
  $("#download-measurements").disabled = !enabled;
  syncViewerControls();
  updateMeasurementButtons();
}

function syncViewerControls() {
  document.querySelectorAll(".layer-choice").forEach((button) => {
    const activo = button.dataset.layer === state.layer;
    button.classList.toggle("is-active", activo);
    button.setAttribute("aria-pressed", String(activo));
  });
  $("#show-segmentation").checked = state.showSegmentation;
  $("#segmentation-label").textContent = state.layer === "candidates" && state.showSegmentation
    ? "Clases + humo"
    : state.showSegmentation ? "Con segmentación" : "Original";
}

function getVisibleLayer() {
  if (!state.showSegmentation) return state.layer === "swir" ? "swir" : "true-color";
  if (state.layer === "swir") return "overlay-swir";
  if (state.layer === "candidates") return "candidates";
  return "overlay-true-color";
}

function updateImage() {
  if (!state.jobId || !state.metrics) return;
  const name = getVisibleLayer();
  const nextUrl = `/api/jobs/${state.jobId}/layers/${name}.png`;
  if (state.imageUrl === nextUrl && !image.hidden) return;
  state.imageUrl = nextUrl;
  image.alt = state.layer === "candidates"
    ? "Candidatos de superficie y humo probable"
    : `${state.layer === "swir" ? "SWIR" : "True Color"}${state.showSegmentation ? " con segmentación" : " original"}`;
  image.onload = () => {
    image.hidden = false;
    $("#empty-state").hidden = true;
    canvas.hidden = false;
    resizeCanvas();
    drawMarks();
  };
  image.onerror = () => showFormError("No se pudo cargar la imagen resultante.");
  image.src = `${nextUrl}?v=${Date.now()}`;
}

function setTool(tool) {
  state.tool = tool;
  document.querySelectorAll(".tool-button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tool === tool);
  });
  stage.classList.toggle("has-tool", tool !== "view");
  if (tool === "pixel") state.inspectedPixel = null;
  updateMeasurement();
  drawMarks();
}

function handleImageClick(event) {
  if (!state.jobId || !state.metrics || state.tool === "view" || image.hidden) return;
  const rect = image.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return;
  const point = {
    x: Math.min(state.grid.ancho_px - 1, Math.max(0, (event.clientX - rect.left) * state.grid.ancho_px / rect.width)),
    y: Math.min(state.grid.alto_px - 1, Math.max(0, (event.clientY - rect.top) * state.grid.alto_px / rect.height)),
  };
  if (state.tool === "pixel") {
    state.inspectedPixel = point;
  } else {
    state.marks.push(point);
    state.polygonClosed = false;
  }
  updateMeasurement();
  drawMarks();
}

function resizeCanvas() {
  if (image.hidden || !image.naturalWidth) return;
  const rect = image.getBoundingClientRect();
  const stageRect = stage.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  canvas.style.left = `${rect.left - stageRect.left}px`;
  canvas.style.top = `${rect.top - stageRect.top}px`;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  canvas.width = Math.max(1, Math.round(rect.width * scale));
  canvas.height = Math.max(1, Math.round(rect.height * scale));
}

function drawMarks() {
  if (image.hidden || canvas.hidden || !image.naturalWidth) return;
  resizeCanvas();
  const rect = image.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const scaleX = rect.width / image.naturalWidth;
  const scaleY = rect.height / image.naturalHeight;
  canvasContext.setTransform(ratio, 0, 0, ratio, 0, 0);
  canvasContext.clearRect(0, 0, rect.width, rect.height);
  if (!state.showMarks) return;
  const points = state.tool === "pixel" && state.inspectedPixel ? [state.inspectedPixel] : state.marks;
  if (points.length > 1) {
    canvasContext.beginPath();
    points.forEach((point, index) => {
      const x = point.x * scaleX;
      const y = point.y * scaleY;
      if (index === 0) canvasContext.moveTo(x, y);
      else canvasContext.lineTo(x, y);
    });
    if (state.tool === "polygon" && state.polygonClosed && points.length > 2) canvasContext.closePath();
    canvasContext.strokeStyle = "#f6dc49";
    canvasContext.lineWidth = 2;
    canvasContext.stroke();
  }
  points.forEach((point, index) => {
    const x = point.x * scaleX;
    const y = point.y * scaleY;
    canvasContext.beginPath();
    canvasContext.arc(x, y, 5, 0, Math.PI * 2);
    canvasContext.fillStyle = "#d94a8b";
    canvasContext.fill();
    canvasContext.strokeStyle = "rgba(255,255,255,.95)";
    canvasContext.lineWidth = 1.5;
    canvasContext.stroke();
    canvasContext.fillStyle = "#fff";
    canvasContext.font = "600 10px ui-monospace, monospace";
    canvasContext.fillText(String(index + 1), x + 8, y - 8);
  });
}

function updateMeasurementButtons() {
  const hasMarks = state.marks.length > 0;
  $("#undo-mark").disabled = !state.jobId || !hasMarks;
  $("#clear-marks").disabled = !state.jobId || (!hasMarks && !state.inspectedPixel);
  $("#close-polygon").disabled = !state.jobId || state.tool !== "polygon" || state.marks.length < 3 || state.polygonClosed;
  $("#download-measurements").disabled = !state.jobId || !state.metrics;
}

function updateMeasurement() {
  const output = $("#measurement-result");
  const readout = $("#pixel-readout");
  readout.hidden = true;
  if (state.tool === "pixel" && state.inspectedPixel && state.grid) {
    const p = state.inspectedPixel;
    const xCoord = p.x * (state.grid.gsd_x_m || 1);
    const yCoord = p.y * (state.grid.gsd_y_m || 1);
    const coords = state.grid.gsd_x_m ? ` · ${formatNumber(xCoord, 1)}, ${formatNumber(yCoord, 1)} m` : "";
    readout.textContent = `Píxel (${Math.round(p.x)}, ${Math.round(p.y)})${coords}`;
    readout.hidden = false;
    output.textContent = "";
  } else if (state.tool === "distance") {
    const pieces = [];
    for (let index = 0; index + 1 < state.marks.length; index += 2) {
      pieces.push(`Tramo ${index / 2 + 1}: ${formatLength(distance(state.marks[index], state.marks[index + 1]), state.grid.gsd_x_m ? "m" : "px")}`);
    }
    if (state.marks.length % 2) pieces.push("Añade otro punto para completar el tramo.");
    output.textContent = pieces.join(" · ");
  } else if (state.tool === "polygon" && state.polygonClosed && state.marks.length >= 3) {
    const area = polygonArea(state.marks);
    const perimeter = polylineLength(state.marks, true);
    output.textContent = `Área manual: ${formatArea(area, state.grid.gsd_x_m ? "m²" : "px²")} · Perímetro: ${formatLength(perimeter, state.grid.gsd_x_m ? "m" : "px")}`;
  } else if (state.tool === "polygon") {
    output.textContent = state.marks.length < 3 ? "Marca al menos tres vértices." : "Cierra el polígono para calcular área y perímetro.";
  } else {
    output.textContent = "";
  }
  updateMeasurementButtons();
  drawMarks();
}

function distance(a, b) {
  const dx = (b.x - a.x) * (state.grid.gsd_x_m || 1);
  const dy = (b.y - a.y) * (state.grid.gsd_y_m || 1);
  return Math.hypot(dx, dy);
}

function polylineLength(points, close) {
  let length = 0;
  for (let index = 1; index < points.length; index += 1) length += distance(points[index - 1], points[index]);
  if (close && points.length > 2) length += distance(points.at(-1), points[0]);
  return length;
}

function polygonArea(points) {
  const scaleX = state.grid.gsd_x_m || 1;
  const scaleY = state.grid.gsd_y_m || 1;
  let twiceArea = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    twiceArea += current.x * scaleX * next.y * scaleY - next.x * scaleX * current.y * scaleY;
  }
  return Math.abs(twiceArea) / 2;
}

function undoMark() {
  if (state.tool === "pixel") state.inspectedPixel = null;
  else {
    state.marks.pop();
    state.polygonClosed = false;
  }
  updateMeasurement();
}

function closePolygon() {
  if (state.marks.length >= 3) state.polygonClosed = true;
  updateMeasurement();
}

function clearMarks() {
  state.marks = [];
  state.inspectedPixel = null;
  state.polygonClosed = false;
  updateMeasurement();
}

async function downloadLayer(layer, filename) {
  if (!state.jobId) return;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/layers/${layer}.png`);
    if (!response.ok) throw new Error("No se pudo preparar el archivo.");
    const blob = await response.blob();
    triggerDownload(blob, filename);
  } catch (error) {
    showFormError(error.message);
  }
}

function downloadMeasurements() {
  if (!state.grid) return;
  const elements = state.marks.map((point, index) => ({
    id: `punto-${index + 1}`,
    tipo: "punto",
    coordenadas_px: [point.x, point.y],
  }));
  if (state.tool === "distance") {
    for (let index = 0; index + 1 < state.marks.length; index += 2) {
      elements.push({
        id: `distancia-${index / 2 + 1}`,
        tipo: "linea",
        vertices_px: [[state.marks[index].x, state.marks[index].y], [state.marks[index + 1].x, state.marks[index + 1].y]],
        distancia: { valor: distance(state.marks[index], state.marks[index + 1]), unidad: state.grid.gsd_x_m ? "m" : "px" },
      });
    }
  }
  if (state.tool === "polygon" && state.polygonClosed && state.marks.length >= 3) {
    elements.push({
      id: "poligono-1",
      tipo: "poligono",
      vertices_px: state.marks.map((point) => [point.x, point.y]),
      area: { valor: polygonArea(state.marks), unidad: state.grid.gsd_x_m ? "m²" : "px²" },
    });
  }
  const payload = {
    esquema: "pyroscope-imagen-v1",
    job_id: state.jobId,
    sistema_coordenadas: state.grid,
    elementos,
  };
  triggerDownload(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }), "pyroscope_mediciones.json");
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderNotes() {
  let notes = [];
  try { notes = JSON.parse(localStorage.getItem("pyroscope-notes") || "[]"); } catch { notes = []; }
  const list = $("#notes-list");
  list.replaceChildren();
  for (const note of notes.slice(0, 12)) {
    const item = document.createElement("li");
    item.textContent = `${note.time} · ${note.text}`;
    list.append(item);
  }
}

function addNote(event) {
  event.preventDefault();
  const text = $("#note-text").value.trim();
  if (!text) return;
  let notes = [];
  try { notes = JSON.parse(localStorage.getItem("pyroscope-notes") || "[]"); } catch { notes = []; }
  notes.unshift({ time: new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }), text });
  localStorage.setItem("pyroscope-notes", JSON.stringify(notes.slice(0, 12)));
  $("#note-text").value = "";
  renderNotes();
}

function showFormError(message) {
  $("#form-error").textContent = message || "";
}

initialize();
