import { useEffect, useState } from "react";
import QRCode from "qrcode";
import AdvancedSettings from "./components/AdvancedSettings.jsx";
import ImageViewer from "./components/ImageViewer.jsx";
import { api, fileToBase64 } from "./services/api.js";
import { Button, Card } from "@radix-ui/themes";
import { Activity, Crosshair, Copy, MapPin, MousePointer2, Pause, Play, Ruler, ScanLine, SlidersHorizontal } from "lucide-react";
import { distanceBetween, formatArea, formatLength, formatNumber, polygonArea, polylineLength } from "./domain/measurements.js";

const DEFAULT_KMEANS_WEIGHTS = {
  swir_red: 1.25,
  swir_chroma: 0.18,
  true_green: -0.62,
  true_luminance: -0.22,
  swir_luminance: -0.12,
  true_chroma: 0.1,
  swir_red_green: 0.22,
  true_blue: -0.3,
};
const DEFAULT_SWIR_THRESHOLDS = {
  seed_red: null,
  grow_red: null,
  seed_red_green: null,
  grow_red_green: null,
  vegetation_max: null,
};
const DEFAULT_WATER_THRESHOLDS = {
  true_color_darkness: 0.2,
  swir_darkness: 0.1,
  swir_red_max: 0.55,
  swir_red_green_max: 0.55,
};

const TOOL_OPTIONS = [
  { id: "view", label: "Ver", Icon: MousePointer2 },
  { id: "distance", label: "Regla", Icon: Ruler },
  { id: "polygon", label: "Área", Icon: Crosshair },
  { id: "pixel", label: "Píxel", Icon: ScanLine },
  { id: "seed", label: "Origen", Icon: MapPin },
];

function defaultAdvancedSettings() {
  return {
    kmeans_weights: { ...DEFAULT_KMEANS_WEIGHTS },
    swir_thresholds: { ...DEFAULT_SWIR_THRESHOLDS },
    smoke_weights: { cyan: 0.65, luminance: 0.2, neutrality: 0.15 },
    smoke_threshold: 0.55,
    water_thresholds: { ...DEFAULT_WATER_THRESHOLDS },
    fusion_kmeans_weight: 0.5,
    fusion_swir_weight: 0.5,
    fusion_threshold: 0.55,
  };
}

function numberFromInput(value, label) {
  const normalized = String(value).trim().replace(",", ".");
  const number = Number(normalized);
  if (!normalized || !Number.isFinite(number)) throw new Error(`${label} debe ser un número válido.`);
  return number;
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function App() {
  const [scenes, setScenes] = useState([]);
  const [detectors, setDetectors] = useState([]);
  const [connection, setConnection] = useState({ ready: false, label: "Conectando…" });
  const [source, setSource] = useState("preloaded");
  const [sceneId, setSceneId] = useState("");
  const [method, setMethod] = useState("kmeans");
  const [sensitivity, setSensitivity] = useState(5);
  const [numClasses, setNumClasses] = useState(7);
  const [minimumArea, setMinimumArea] = useState("0.15");
  const [maxDistance, setMaxDistance] = useState("10");
  const [gsd, setGsd] = useState("");
  const [keepSeparate, setKeepSeparate] = useState(false);
  const [advanced, setAdvanced] = useState(defaultAdvancedSettings);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ label: "Listo para analizar", value: 0 });
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobLabel, setJobLabel] = useState("Selecciona una escena");
  const [settingsUsed, setSettingsUsed] = useState(null);
  const [layer, setLayer] = useState("swir");
  const [showSegmentation, setShowSegmentation] = useState(true);
  const [showMarks, setShowMarks] = useState(true);
  const [airTemperature, setAirTemperature] = useState("25");
  const [airHumidity, setAirHumidity] = useState("35");
  const [windFrom, setWindFrom] = useState("270");
  const [windSpeed, setWindSpeed] = useState("20");
  const [baseAdvance, setBaseAdvance] = useState("2.5");
  const [weatherTime, setWeatherTime] = useState("");
  const [weatherSource, setWeatherSource] = useState("");
  const [scenarioSeed, setScenarioSeed] = useState(null);
  const [scenario, setScenario] = useState(null);
  const [scenarioFrame, setScenarioFrame] = useState(0);
  const [scenarioPlaying, setScenarioPlaying] = useState(false);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const [tool, setTool] = useState("view");
  const [marks, setMarks] = useState([]);
  const [distancePreview, setDistancePreview] = useState(null);
  const [polygonClosed, setPolygonClosed] = useState(false);
  const [inspectedPixel, setInspectedPixel] = useState(null);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [showInstallHelp, setShowInstallHelp] = useState(false);
  const [mobileAccess, setMobileAccess] = useState(null);
  const [mobileQr, setMobileQr] = useState("");
  const [mobileLinkCopied, setMobileLinkCopied] = useState(false);

  const desktopMobileSetup = Boolean(
    mobileAccess?.enabled && ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname),
  );

  useEffect(() => {
    let active = true;
    api.mobileAccess().then((access) => {
      if (active) setMobileAccess(access);
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (!desktopMobileSetup || !mobileAccess?.url) {
      setMobileQr("");
      return () => { active = false; };
    }
    QRCode.toDataURL(mobileAccess.url, { width: 176, margin: 1, errorCorrectionLevel: "M" })
      .then((dataUrl) => { if (active) setMobileQr(dataUrl); })
      .catch(() => { if (active) setMobileQr(""); });
    return () => { active = false; };
  }, [desktopMobileSetup, mobileAccess?.url]);

  useEffect(() => {
    const rememberInstallPrompt = (event) => {
      event.preventDefault();
      setInstallPrompt(event);
    };
    window.addEventListener("beforeinstallprompt", rememberInstallPrompt);
    return () => window.removeEventListener("beforeinstallprompt", rememberInstallPrompt);
  }, []);

  const installMobileApp = async () => {
    if (!installPrompt) {
      setShowInstallHelp((visible) => !visible);
      return;
    }
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  };

  useEffect(() => {
    let active = true;
    Promise.all([api.scenes(), api.detectors()])
      .then(([sceneResponse, detectorResponse]) => {
        if (!active) return;
        const availableScenes = sceneResponse.scenes || [];
        const availableDetectors = detectorResponse.detectors || [];
        setScenes(availableScenes);
        setDetectors(availableDetectors);
        if (availableScenes.length) setSceneId(availableScenes[0].id);
        if (availableDetectors.length && !availableDetectors.some((item) => item.id === method)) {
          setMethod(availableDetectors[0].id);
        }
        setConnection({ ready: true, label: "Conectado" });
      })
      .catch((cause) => {
        if (!active) return;
        setConnection({ ready: false, label: "Sin conexión" });
        setError(cause.message);
      });
    return () => { active = false; };
  }, []);

  const selectedScene = scenes.find((item) => item.id === sceneId);
  const selectedDetector = detectors.find((item) => item.id === method);
  const activeLabel = source === "upload" ? "Pareja cargada" : selectedScene?.label || "Selecciona una escena";
  const canRun = connection.ready && !running && (source === "upload" || scenes.length > 0);
  const hasResult = Boolean(result && result.state === "complete");
  const grid = result?.grid || null;
  const metrics = result?.metrics || null;
  const marksUnit = grid?.gsd_x_m ? "m" : "px";
  const currentDistance = grid && (distancePreview
    ? distanceBetween(distancePreview.start, distancePreview.end, grid)
    : tool === "distance" && marks.length >= 2
      ? distanceBetween(marks[marks.length - 2], marks[marks.length - 1], grid)
      : null);
  const manualArea = grid && tool === "polygon" && marks.length >= 3 ? polygonArea(marks, grid) : null;
  const manualPerimeter = grid && tool === "polygon" && marks.length >= 2
    ? polylineLength(marks, grid, polygonClosed)
    : null;
  const progressionFront = scenario?.frames?.[scenarioFrame]?.front || null;

  useEffect(() => {
    if (!scenarioPlaying || !scenario?.frames?.length) return undefined;
    const lastFrame = scenario.frames.length - 1;
    if (scenarioFrame >= lastFrame) {
      setScenarioPlaying(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setScenarioFrame((frame) => frame + 1), 240);
    return () => window.clearTimeout(timer);
  }, [scenarioPlaying, scenario, scenarioFrame]);

  const selectTool = (nextTool) => {
    if (nextTool === tool) return;
    setTool(nextTool);
    setMarks([]);
    setDistancePreview(null);
    setPolygonClosed(false);
    setInspectedPixel(null);
  };

  const chooseScenarioOrigin = (point) => {
    setScenarioSeed(point);
    setScenario(null);
    setScenarioFrame(0);
    setScenarioPlaying(false);
    setScenarioError("");
    setTool("view");
  };

  const runProgressionScenario = async () => {
    setScenarioError("");
    try {
      if (!hasResult || !jobId) throw new Error("Primero termina un análisis de imagen.");
      if (!scenarioSeed) throw new Error("Elige un único origen en la imagen.");
      const temperature = numberFromInput(airTemperature, "La temperatura");
      const humidity = numberFromInput(airHumidity, "La humedad relativa");
      const direction = numberFromInput(windFrom, "La dirección del viento");
      const speed = numberFromInput(windSpeed, "La velocidad del viento");
      const advance = numberFromInput(baseAdvance, "El avance visual");
      if (temperature < -20 || temperature > 60) throw new Error("La temperatura debe estar entre -20 y 60 °C.");
      if (humidity < 0 || humidity > 100) throw new Error("La humedad relativa debe estar entre 0 y 100 %.");
      if (direction < 0 || direction >= 360) throw new Error("La dirección debe estar entre 0° y 359,9°.");
      if (speed < 0 || speed > 160) throw new Error("La velocidad debe estar entre 0 y 160 km/h.");
      if (advance < 0.5 || advance > 16) throw new Error("El avance visual debe estar entre 0,5 y 16 px por paso.");
      setScenarioLoading(true);
      const generated = await api.fireProgression(jobId, {
        origin: scenarioSeed,
        temperature_c: temperature,
        relative_humidity_pct: humidity,
        wind_from_deg: direction,
        wind_speed_kmh: speed,
        base_advance_px: advance,
        weather_time: weatherTime,
        weather_source: weatherSource,
        steps: 16,
      });
      setScenario(generated);
      setScenarioFrame(0);
      setScenarioPlaying(true);
      setTool("view");
    } catch (cause) {
      setScenarioError(cause?.message || "No se pudo generar el escenario.");
    } finally {
      setScenarioLoading(false);
    }
  };

  const collectSettings = () => {
    const minimum = numberFromInput(minimumArea, "El área mínima");
    if (minimum < 0.01 || minimum > 1) throw new Error("El área mínima debe estar entre 0,01 y 1 %.");
    const distance = numberFromInput(maxDistance, "El radio máximo");
    const gsdNumber = gsd.trim() ? numberFromInput(gsd, "El GSD") : null;
    if (gsdNumber !== null && gsdNumber <= 0) throw new Error("El GSD debe ser positivo en metros por píxel.");
    if (!keepSeparate && (!Number.isInteger(distance) || distance < 3 || distance > 20)) {
      throw new Error("El radio máximo debe ser un entero entre 3 y 20 %.");
    }
    for (const [name, value] of Object.entries(advanced.kmeans_weights)) {
      if (!Number.isFinite(value) || value < -3 || value > 3) throw new Error(`El peso K-Means ${name} debe estar entre -3 y 3.`);
    }
    const sensitivityNumber = Number(sensitivity);
    const seedRed = advanced.swir_thresholds.seed_red ?? (0.994 - (sensitivityNumber - 1) * 0.006);
    const growRed = advanced.swir_thresholds.grow_red ?? (0.94 - (sensitivityNumber - 1) * 0.01);
    const seedRG = advanced.swir_thresholds.seed_red_green ?? (0.82 - (sensitivityNumber - 1) * 0.005);
    const growRG = advanced.swir_thresholds.grow_red_green ?? (0.68 - (sensitivityNumber - 1) * 0.012);
    if (growRed > seedRed || growRG > seedRG) throw new Error("El percentil de crecimiento SWIR debe ser menor o igual al de semilla.");
    if (Object.values(advanced.smoke_weights).some((value) => value < 0 || value > 1)
        || Object.values(advanced.smoke_weights).every((value) => value === 0)) {
      throw new Error("Los pesos del score de humo deben estar entre 0 y 1 y alguno debe ser positivo.");
    }
    for (const [name, value] of Object.entries(advanced.water_thresholds)) {
      if (!Number.isFinite(value) || value < 0.01 || value > 0.99) throw new Error(`El percentil de agua ${name} debe estar entre 0,01 y 0,99.`);
    }
    if (method === "fusion_ponderada" && advanced.fusion_kmeans_weight + advanced.fusion_swir_weight <= 0) {
      throw new Error("En la fusión, deja al menos un peso de algoritmo por encima de cero.");
    }

    return {
      method,
      sensitivity: sensitivityNumber,
      num_classes: selectedDetector?.uses_num_classes ? Number(numClasses) : 7,
      minimum_area_pct: minimum,
      max_distance_pct: keepSeparate ? 10 : distance,
      keep_separate: keepSeparate,
      gsd_m_per_px: gsdNumber,
      advanced,
    };
  };

  const runAnalysis = async (event) => {
    event.preventDefault();
    setError("");
    let request;
    try {
      const settings = collectSettings();
      setSettingsUsed(settings);
      if (source === "preloaded") {
        if (!sceneId) throw new Error("Selecciona una escena precargada.");
        request = { source: "preloaded", scene: sceneId, settings };
      } else {
        const form = event.currentTarget?.form || event.currentTarget;
        const trueFile = form.elements.namedItem("true-color-file")?.files?.[0];
        const swirFile = form.elements.namedItem("swir-file")?.files?.[0];
        if (!trueFile || !swirFile) throw new Error("Carga las dos imágenes: True Color y SWIR.");
        request = {
          source: "upload",
          true_color: await fileToBase64(trueFile),
          swir: await fileToBase64(swirFile),
          settings,
        };
      }

      setJobLabel(activeLabel);
      setJobId(null);
      setResult(null);
      setMarks([]);
      setDistancePreview(null);
      setPolygonClosed(false);
      setInspectedPixel(null);
      setScenarioSeed(null);
      setScenario(null);
      setScenarioFrame(0);
      setScenarioPlaying(false);
      setScenarioError("");
      setRunning(true);
      setConnection({ ready: true, label: "Analizando…" });
      setProgress({ label: "Preparando análisis", value: 0 });

      const started = await api.analyze(request);
      const nextJobId = started.job_id;
      setJobId(nextJobId);
      while (true) {
        const job = await api.job(nextJobId);
        setProgress({ label: job.stage || "Procesando", value: job.progress || 0 });
        if (job.state === "complete") {
          setResult(job);
          setRunning(false);
          setConnection({ ready: true, label: "Conectado" });
          return;
        }
        if (job.state === "error") throw new Error(job.error || "No se pudo completar el análisis.");
        await new Promise((resolve) => window.setTimeout(resolve, 650));
      }
    } catch (cause) {
      const message = cause?.message || "No se pudo iniciar el análisis.";
      setError(message);
      setResult({ state: "error", error: message });
      setProgress({ label: "No se pudo completar", value: 0 });
      setRunning(false);
      if (cause instanceof TypeError) {
        setConnection({ ready: false, label: "Sin conexión" });
      } else {
        setConnection({ ready: true, label: "Conectado" });
      }
    }
  };

  const downloadLayer = async (name, filename) => {
    if (!jobId) return;
    try {
      saveBlob(await api.downloadLayer(jobId, name), filename);
    } catch (cause) {
      setError(cause.message);
    }
  };

  const downloadMeasurements = () => {
    if (!jobId || !grid) return;
    const elements = marks.map((point, index) => ({
      id: `punto-${index + 1}`,
      tipo: "punto",
      coordenadas_px: [point.x, point.y],
    }));
    if (tool === "distance") {
      for (let index = 0; index + 1 < marks.length; index += 2) {
        elements.push({
          id: `distancia-${index / 2 + 1}`,
          tipo: "linea",
          vertices_px: [[marks[index].x, marks[index].y], [marks[index + 1].x, marks[index + 1].y]],
          distancia: { valor: distanceBetween(marks[index], marks[index + 1], grid), unidad: marksUnit },
        });
      }
    }
    if (tool === "polygon" && polygonClosed && marks.length >= 3) {
      elements.push({
        id: "poligono-1",
        tipo: "poligono",
        vertices_px: marks.map((point) => [point.x, point.y]),
        area: { valor: polygonArea(marks, grid), unidad: grid.gsd_x_m ? "m²" : "px²" },
        perimetro: { valor: polylineLength(marks, grid, true), unidad: marksUnit },
      });
    }
    saveBlob(
      new Blob([JSON.stringify({ esquema: "lumbre-imagen-v1", job_id: jobId, sistema_coordenadas: grid, elementos }, null, 2)], { type: "application/json" }),
      "lumbre_mediciones.json",
    );
  };

  const summary = metrics && settingsUsed
    ? `${metrics.detector}. Rejilla ${metrics.grid_width} × ${metrics.grid_height} px. Píxeles excluidos como agua: ${formatNumber(metrics.water_excluded)}. Regiones remotas descartadas: ${metrics.remote_regions_discarded}. ${metrics.gsd_x_m ? `GSD efectivo ${formatNumber(metrics.gsd_x_m, 3)} × ${formatNumber(metrics.gsd_y_m, 3)} m/píxel.` : "Sin GSD; las medidas se expresan en píxeles."}`
    : "Al terminar, aquí se muestran el detector y la rejilla usada.";
  return (
    <>
      <header className="mobile-appbar">
        <a className="mobile-brand" href="#mobile-setup" aria-label="Lumbre, ir al análisis">
          <span className="brand-pixel-flame" aria-hidden="true" />
          <span><strong>LUMBRE</strong><small>FIELD ANALYSIS</small></span>
        </a>
        <button className="install-button" type="button" onClick={installMobileApp}>Instalar app</button>
      </header>
      {showInstallHelp && <div className="install-help" role="status">
        <span>iPhone/iPad: Compartir → Añadir a pantalla de inicio. Android: menú del navegador → Instalar aplicación o Añadir a pantalla de inicio.</span>
        <button type="button" aria-label="Cerrar ayuda" onClick={() => setShowInstallHelp(false)}>×</button>
      </div>}
      <main className="workspace">
        <aside className="control-panel" id="mobile-setup" aria-label="Configuración del análisis">
          <div className="panel-heading">
            <h1><SlidersHorizontal size={15} aria-hidden="true" />Análisis</h1>
            <span className={`connection-pill${connection.ready ? " is-ready" : error ? " is-error" : ""}`}>
              <span className="status-dot" />{connection.label}
            </span>
          </div>

          {desktopMobileSetup && <section className="phone-access" aria-label="Abrir Lumbre en el móvil">
            <h2>Abre Lumbre en tu móvil</h2>
            <p>Conecta el móvil a la misma Wi‑Fi y escanea este código con la cámara.</p>
            {mobileQr ? <img className="phone-access-qr" src={mobileQr} alt="Código QR para abrir Lumbre en el móvil" /> : <p>Preparando el código…</p>}
            <code className="phone-access-url">{mobileAccess.url}</code>
            <button className="phone-access-copy" type="button" onClick={async () => {
              try {
                await navigator.clipboard.writeText(mobileAccess.url);
                setMobileLinkCopied(true);
                window.setTimeout(() => setMobileLinkCopied(false), 1800);
              } catch {
                setMobileLinkCopied(false);
              }
            }}><Copy size={14} aria-hidden="true" />{mobileLinkCopied ? "Enlace copiado" : "Copiar enlace"}</button>
          </section>}

          <form onSubmit={runAnalysis}>
            <div className="source-switch" role="tablist" aria-label="Origen de las imágenes">
              {[ ["preloaded", "Escenas"], ["upload", "Subir imágenes"] ].map(([id, label]) => (
                <button key={id} className={`source-tab${source === id ? " is-active" : ""}`} type="button" role="tab" aria-selected={source === id} onClick={() => setSource(id)}>{label}</button>
              ))}
            </div>

            {source === "preloaded" ? (
              <section className="source-content">
                <label className="field-label" htmlFor="scene-select">Escena</label>
                <select className="field-control" id="scene-select" value={sceneId} onChange={(event) => setSceneId(event.target.value)}>
                  {scenes.length ? scenes.map((scene) => <option value={scene.id} key={scene.id}>{scene.label}</option>) : <option value="">Buscando imágenes…</option>}
                </select>
              </section>
            ) : (
              <section className="source-content">
                <label className="field-label" htmlFor="true-color-file">Imagen True Color</label>
                <input className="file-control" name="true-color-file" id="true-color-file" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
                <label className="field-label second-file-label" htmlFor="swir-file">Imagen SWIR</label>
                <input className="file-control" name="swir-file" id="swir-file" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
                <p className="field-help">True Color y SWIR de la misma fecha.</p>
              </section>
            )}

            <div className="section-rule"><span>DETECTOR</span></div>
            <label className="field-label" htmlFor="detector-select">Método</label>
            <select className="field-control" id="detector-select" value={method} onChange={(event) => setMethod(event.target.value)}>
              {detectors.map((detector) => <option value={detector.id} key={detector.id}>{detector.name}</option>)}
            </select>

            {selectedDetector?.uses_sensitivity !== false && <>
              <div className="range-row">
                <label className="field-label" htmlFor="sensitivity">Sensibilidad</label>
                <output className="range-value">{sensitivity}</output>
              </div>
              <input className="range-control" id="sensitivity" type="range" min="1" max="10" value={sensitivity} onChange={(event) => setSensitivity(Number(event.target.value))} />
            </>}

            {selectedDetector?.uses_num_classes !== false && <>
              <div className="range-row">
                <label className="field-label" htmlFor="num-classes">Grupos de color</label>
                <output className="range-value">{numClasses}</output>
              </div>
              <input className="range-control" id="num-classes" type="range" min="4" max="10" value={numClasses} onChange={(event) => setNumClasses(Number(event.target.value))} />
            </>}

            <details className="details-panel parameter-settings">
              <summary>Parámetros y escala</summary>
              <div className="parameter-content">
                <div className="compact-fields">
                  <div>
                    <label className="field-label" htmlFor="minimum-area">Área mínima (%)</label>
                    <input className="field-control" id="minimum-area" type="number" min="0.01" max="1" step="0.01" value={minimumArea} onChange={(event) => setMinimumArea(event.target.value)} />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="max-distance">Radio máximo (%)</label>
                    <input className="field-control" id="max-distance" type="number" min="3" max="20" step="1" value={maxDistance} disabled={keepSeparate} onChange={(event) => setMaxDistance(event.target.value)} />
                  </div>
                </div>
                <label className="check-row" htmlFor="keep-separate">
                  <input id="keep-separate" type="checkbox" checked={keepSeparate} onChange={(event) => setKeepSeparate(event.target.checked)} />
                  <span>Conservar focos separados</span>
                </label>
              </div>
            </details>

            <AdvancedSettings value={advanced} onChange={setAdvanced} onReset={() => setAdvanced(defaultAdvancedSettings())} method={method} />

            <Button className="run-button" id="run-analysis" type="button" onClick={runAnalysis} disabled={!canRun} size="3">
              {running ? <Activity size={16} aria-hidden="true" /> : <Play size={15} aria-hidden="true" fill="currentColor" />}
              <span>{running ? "Analizando…" : "Iniciar segmentación"}</span>
            </Button>
            {error && <p className="form-error" role="alert">{error}</p>}
          </form>
        </aside>

        <section className="analysis-column" id="mobile-map" aria-label="Plano y progreso">
          <div className="analysis-heading">
            <div className="analysis-title"><h2>{jobId || running ? jobLabel : activeLabel}</h2></div>
            <div className="progress-summary" aria-live="polite"><span>{progress.label}</span><strong>{progress.value}%</strong></div>
          </div>
          <div className="progress-track" role="progressbar" aria-label="Progreso del análisis" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress.value}>
            <span style={{ width: `${progress.value}%` }} />
          </div>

          <div className="viewer-card">
            <ImageViewer
              jobId={hasResult ? jobId : null}
              grid={hasResult ? grid : null}
              layer={layer}
              setLayer={setLayer}
              showSegmentation={showSegmentation}
              setShowSegmentation={setShowSegmentation}
              showMarks={showMarks}
              setShowMarks={setShowMarks}
              seedPoint={scenarioSeed}
              progressionFront={progressionFront}
              onSeedSelect={chooseScenarioOrigin}
              tool={tool}
              setTool={setTool}
              marks={marks}
              setMarks={setMarks}
              distancePreview={distancePreview}
              setDistancePreview={setDistancePreview}
              inspectedPixel={inspectedPixel}
              setInspectedPixel={setInspectedPixel}
              polygonClosed={polygonClosed}
              setPolygonClosed={setPolygonClosed}
              errorMessage={running ? "La vista aparecerá al terminar la segmentación." : ""}
              onError={setError}
            />
          </div>
        </section>

        <aside className="results-column interaction-panel" id="mobile-results" aria-label="Herramientas y resultados">
          <div className="results-heading"><h2>Medir y analizar</h2></div>
          <section className="measurement-panel scenario-panel" aria-label="Escenario ilustrativo de progresión">
            <p className="panel-kicker">ESCENARIO DE PROGRESIÓN</p>
            <Button className="scenario-origin-button" variant="outline" size="2" type="button" disabled={!hasResult} aria-pressed={tool === "seed"} onClick={() => selectTool("seed")}>
              <MapPin size={14} aria-hidden="true" />{scenarioSeed ? "Cambiar origen en imagen" : "Elegir origen en imagen"}
            </Button>
            <p className="field-help">Elige un solo punto donde observes fuego activo; el área quemada no se usa como origen.</p>
            {scenarioSeed && <p className="scenario-origin-readout" aria-live="polite">Origen: ({formatNumber(scenarioSeed.x, 1)}, {formatNumber(scenarioSeed.y, 1)}) px</p>}
            <div className="compact-fields scenario-fields">
              <div><label className="field-label" htmlFor="scenario-temp">Temperatura del aire · °C</label><input className="field-control" id="scenario-temp" type="number" min="-20" max="60" step="any" value={airTemperature} onChange={(event) => setAirTemperature(event.target.value)} /></div>
              <div><label className="field-label" htmlFor="scenario-humidity">Humedad relativa · %</label><input className="field-control" id="scenario-humidity" type="number" min="0" max="100" step="any" value={airHumidity} onChange={(event) => setAirHumidity(event.target.value)} /></div>
              <div><label className="field-label" htmlFor="scenario-wind-from">Viento desde · °</label><input className="field-control" id="scenario-wind-from" type="number" min="0" max="359.9" step="any" value={windFrom} onChange={(event) => setWindFrom(event.target.value)} /></div>
              <div><label className="field-label" htmlFor="scenario-wind-speed">Velocidad · km/h</label><input className="field-control" id="scenario-wind-speed" type="number" min="0" max="160" step="any" value={windSpeed} onChange={(event) => setWindSpeed(event.target.value)} /></div>
            </div>
            <p className="field-help">Dirección meteorológica: 0° = norte y crece en sentido horario; el modelo la invierte hacia el destino.</p>
            <div>
              <label className="field-label" htmlFor="scenario-weather-time">Hora de esos datos y zona horaria</label>
              <input className="field-control" id="scenario-weather-time" type="text" maxLength="120" placeholder="p. ej., 2026-10-15 14:00 UTC" value={weatherTime} onChange={(event) => setWeatherTime(event.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor="scenario-weather-source">Fuente meteorológica</label>
              <input className="field-control" id="scenario-weather-source" type="text" maxLength="120" placeholder="p. ej., estación local" value={weatherSource} onChange={(event) => setWeatherSource(event.target.value)} />
            </div>
            <p className="field-help">Anota datos próximos a la adquisición y su procedencia. La app no consulta meteorología automáticamente.</p>
            <label className="field-label scenario-advance-label" htmlFor="scenario-advance">Avance base · px por paso visual</label>
            <input className="field-control" id="scenario-advance" type="number" min="0.5" max="16" step="0.5" value={baseAdvance} onChange={(event) => setBaseAdvance(event.target.value)} />
            <Button className="scenario-run-button" variant="solid" size="2" type="button" disabled={!hasResult || scenarioLoading || !scenarioSeed} onClick={runProgressionScenario}>
              {scenarioLoading ? <Activity size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" fill="currentColor" />}
              {scenarioLoading ? "Calculando…" : "Generar progresión"}
            </Button>
            {scenario && <>
              <div className="scenario-playback">
                <Button variant="outline" size="1" type="button" onClick={() => {
                  if (scenarioFrame >= scenario.frames.length - 1) setScenarioFrame(0);
                  setScenarioPlaying((playing) => !playing);
                }}>
                  {scenarioPlaying ? <Pause size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" fill="currentColor" />}
                  {scenarioPlaying ? "Pausar" : "Animar"}
                </Button>
                <span>Paso {scenarioFrame + 1}/{scenario.frames.length}</span>
              </div>
              <input className="range-control scenario-timeline" aria-label="Paso de la progresión ilustrativa" type="range" min="0" max={scenario.frames.length - 1} step="1" value={scenarioFrame} onChange={(event) => { setScenarioFrame(Number(event.target.value)); setScenarioPlaying(false); }} />
              <p className="field-help">La dirección meteorológica se convierte de «desde» a «hacia». El avance y los pasos se expresan solo en píxeles.</p>
              <details className="details-panel scenario-formula">
                <summary>Fórmula del escenario</summary>
                <p className="field-help">D = ((T + 20) / 80) × (1 − HR / 100); factor de ambiente = 0,75 + 0,5D; sesgo de viento = 0,45 × v / (v + 20); radio(θ, k) = k × avance × factor × [1 + sesgo × cos(θ − θviento)]. Los coeficientes sirven solo para dibujar esta hipótesis.</p>
              </details>
            </>}
            {scenarioError && <p className="form-error" role="alert">{scenarioError}</p>}
            <p className="scenario-caveat">Escenario matemático exploratorio, no pronóstico validado. La humedad del aire no es humedad del combustible. Sin combustible, pendiente ni calibración no se calcula una tasa real.</p>
          </section>
          <section className="measurement-panel" aria-label="Herramientas de medición">
            <p className="panel-kicker">HERRAMIENTAS</p>
            <div className="tool-grid" role="group" aria-label="Seleccionar herramienta">
              {TOOL_OPTIONS.map(({ id, label, Icon }) => (
                <Button key={id} className={`tool-button${tool === id ? " is-active" : ""}`} variant={tool === id ? "soft" : "ghost"} size="1" type="button" disabled={!hasResult} aria-pressed={tool === id} onClick={() => selectTool(id)}>
                <Icon size={14} aria-hidden="true" /><span>{label}</span>
                </Button>
              ))}
            </div>
            <p className="measurement-hint" aria-live="polite">
              {tool === "distance" ? "Arrastra sobre la imagen para medir una distancia." : tool === "polygon" ? "Marca vértices en la imagen para medir un área." : tool === "pixel" ? "Selecciona un píxel para ver su coordenada." : tool === "seed" ? "Haz clic en un punto de fuego activo para fijar el origen del escenario." : "Elige una herramienta o compara las capas en el visor."}
            </p>
            {(currentDistance !== null || manualArea !== null || (tool === "pixel" && inspectedPixel)) && <div className="measurement-readout" aria-live="polite">
              {currentDistance !== null && <div><span>{distancePreview ? "Midiendo" : "Distancia"}</span><strong>{formatLength(currentDistance, marksUnit)}</strong></div>}
              {manualArea !== null && <div><span>{polygonClosed ? "Área dibujada" : "Área aproximada"}</span><strong>{formatArea(manualArea, grid.gsd_x_m ? "m²" : "px²")}</strong></div>}
              {manualPerimeter !== null && <div><span>Perímetro del área</span><strong>{formatLength(manualPerimeter, marksUnit)}</strong></div>}
              {tool === "pixel" && inspectedPixel && <div><span>Coordenada</span><strong>({formatNumber(inspectedPixel.x)}, {formatNumber(inspectedPixel.y)}) px</strong></div>}
            </div>}
            <div className="measurement-actions">
              <button className="text-button" type="button" disabled={!hasResult || (!marks.length && !inspectedPixel)} onClick={() => {
                if (tool === "pixel") setInspectedPixel(null);
                else setMarks((current) => current.slice(0, tool === "distance" ? -2 : -1));
                setDistancePreview(null);
                setPolygonClosed(false);
              }}>Deshacer</button>
              {tool === "polygon" && <button className="text-button" type="button" disabled={!hasResult || marks.length < 3 || polygonClosed} onClick={() => setPolygonClosed(true)}>Cerrar área</button>}
              <button className="text-button" type="button" disabled={!hasResult || (!marks.length && !inspectedPixel)} onClick={() => {
                setMarks([]); setInspectedPixel(null); setDistancePreview(null); setPolygonClosed(false);
              }}>Borrar marcas</button>
            </div>
            <hr className="measurement-separator" />
            <label className="scale-input" htmlFor="gsd"><span>GSD <small>metros por píxel</small></span>
              <input className="field-control" id="gsd" type="number" min="0.000001" step="any" inputMode="decimal" placeholder="Opcional" value={gsd} onChange={(event) => setGsd(event.target.value)} disabled={running} />
            </label>
            <p className="field-help">Se aplica en el siguiente análisis. Sin GSD, las medidas quedan en píxeles.</p>
            <details className="resolution-reference">
              <summary>Área por píxel y referencia</summary>
              <p className="resolution-formula">Para píxeles cuadrados: superficie/píxel = tamaño de píxel²</p>
              <table className="resolution-table">
                <tbody>
                  <tr><th scope="row">Resolución</th><td>10 m</td><td>20 m</td><td>60 m</td></tr>
                  <tr><th scope="row">Superficie</th><td>100 m²</td><td>400 m²</td><td>3.600 m²</td></tr>
                </tbody>
              </table>
              <p className="resolution-warning">Valores nominales. 60 m corresponde a bandas atmosféricas, no a True Color ni SWIR. JPG puede estar reescalado; el área queda en píxeles hasta verificar escala y georreferenciación.</p>
              <details className="resolution-details">
                <summary>Referencia técnica y límites</summary>
              <div className="resolution-longform">
                <p>Como referencia inicial, True Color basado en bandas visibles de Sentinel‑2 suele asociarse a bandas de 10 m y SWIR B11/B12 a 20 m. Solo se pueden aplicar 100 m²/píxel a True Color o 400 m²/píxel a SWIR si la exportación conserva esa escala. El nombre del JPG no demuestra su resolución efectiva; no se ha confirmado la composición espectral exacta de los productos <code>Wildfires</code>.</p>
                <p>Ejemplo: 5.000 píxeles clasificados como quemados equivaldrían nominalmente a 500.000 m² (50 ha) a 10 m/píxel, o 2.000.000 m² (200 ha) a 20 m/píxel. Es solo ilustrativo; no mide las imágenes del repositorio.</p>
                <p>El artículo “Ground Resolved Distance Estimation of Sentinel‑2 Imagery Using Edge‑based Scene‑Driven Approach” (PFG Journal, 2025) distingue GSD —distancia entre centros de píxeles— de GRD —capacidad efectiva de resolución—. En las escenas estudiadas estima una GRD media de aproximadamente 12,4–12,7 m para las bandas visibles y NIR con GSD nominal de 10 m. El tamaño nominal del píxel no indica el detalle mínimo que se puede resolver.</p>
                <p>Para afirmar una superficie real hay que verificar dimensiones de los ocho JPG, bandas, remuestreo, CRS, geotransformación y tamaño de celda. Sin referencia geográfica, la máscara se puede contar en píxeles, pero no atribuirle una superficie terrestre exacta. Un cálculo defendible requiere un raster georreferenciado y sumar las celdas quemadas; área quemada y fuego activo son fenómenos distintos.</p>
                <p><strong>Siguiente paso:</strong> confirmar la composición de cada producto y documentar cualquier remuestreo antes de calcular hectáreas.</p>
              </div>
              </details>
            </details>
          </section>

          <div className="results-heading results-subheading"><h2>Resultado</h2></div>
          <div className={`result-state${result?.state === "error" ? " is-error" : ""}`}>
            {running ? "Analizando…" : metrics ? `Detector: ${metrics.detector}` : result?.error || "Pendiente"}
          </div>
          {metrics && <>
            <div className="metrics-grid">
              <Card className="metric-card metric-primary" size="1"><span>Superficie candidata</span><strong>{formatNumber(metrics.coverage_pct, 1)} %</strong></Card>
              <Card className="metric-card" size="1"><span>Área</span><strong>{formatArea(metrics.area, metrics.area_unit)}</strong></Card>
              <Card className="metric-card" size="1"><span>Perímetro</span><strong>{formatLength(metrics.perimeter, metrics.perimeter_unit)}</strong></Card>
              <Card className="metric-card" size="1"><span>Humo probable</span><strong>{formatNumber(metrics.smoke_pct, 1)} %</strong></Card>
              {metrics.active_fire_px > 0 && <Card className="metric-card" size="1"><span>Fuego activo posible</span><strong>{formatNumber(metrics.active_fire_px)} px</strong></Card>}
            </div>
            <p className="result-caveat">Resultado orientativo; revisa la máscara. En fucsia: {formatNumber(metrics.smoke_covered_candidates_px)} px con evidencia de superficie afectada bajo humo; es una hipótesis y no se suma al área. El fuego activo se informa aparte cuando el modelo lo clasifica.</p>
          </>}

          <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("overlay-true-color", "lumbre_mapa_segmentado.png")}><span>Mapa con contorno</span><span>PNG ↓</span></button>
          <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("mask", "lumbre_mascara_candidata.png")}><span>Máscara segmentada</span><span>PNG ↓</span></button>
          <button className="export-button" type="button" disabled={!hasResult} onClick={downloadMeasurements}><span>Puntos y medidas</span><span>JSON ↓</span></button>

          {metrics && <details className="details-panel">
            <summary>Detalles</summary>
            <div className="details-content">{summary}</div>
          </details>}
        </aside>
      </main>
      <nav className="mobile-dock" aria-label="Secciones">
        <a href="#mobile-setup"><SlidersHorizontal size={18} aria-hidden="true" /><span>Analizar</span></a>
        <a href="#mobile-map"><ScanLine size={18} aria-hidden="true" /><span>Mapa</span></a>
        <a href="#mobile-results"><Activity size={18} aria-hidden="true" /><span>Resultados</span></a>
      </nav>
    </>
  );
}

export default App;
