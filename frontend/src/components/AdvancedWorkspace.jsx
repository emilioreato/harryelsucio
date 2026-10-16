import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Flame, Image as ImageIcon, Layers3, Play, ScanLine } from "lucide-react";
import { advancedApi, fileToBase64 } from "../services/api.js";
import { formatNumber } from "../domain/measurements.js";
import VersionSwitcher from "./VersionSwitcher.jsx";
import GsdScaleRuler from "./GsdScaleRuler.jsx";
import ZoomableImageViewport from "./ZoomableImageViewport.jsx";

const INPUT_LAYERS = [
  ["true-color", "True Color", ImageIcon],
  ["swir", "SWIR", ScanLine],
  ["candidates", "Clases", Layers3],
  ["vegetation", "Verdor aparente", Layers3],
  ["possible-active-fire", "Clase de fuego posible", Flame],
  ["fire-hotspots", "Candidatos de focos", Flame],
];

function numberFromInput(value, label) {
  const number = Number(String(value).trim().replace(",", "."));
  if (!String(value).trim() || !Number.isFinite(number)) {
    throw new Error(`${label} debe ser un número válido.`);
  }
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

function slugForFilename(value) {
  return String(value || "analisis")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48) || "analisis";
}

function localDateStamp(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}_${pad(date.getHours())}-${pad(date.getMinutes())}-${pad(date.getSeconds())}`;
}

function loadRulerMask(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = url;
  });
}

function AdvancedViewer({
  jobId,
  grid,
  metrics,
  layer,
  setLayer,
  origin,
  progressionFront,
  selectingOrigin,
  onOriginSelect,
  onError,
}) {
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const surfaceRef = useRef(null);
  const [rulerMasks, setRulerMasks] = useState({});
  const availableLayers = new Set(metrics?.available_layers || []);
  const choices = INPUT_LAYERS.filter(([id]) => availableLayers.has(id));
  if (availableLayers.has("reference-wildfires")) {
    choices.push(["reference-wildfires", "Wildfires", Layers3]);
  }
  const source = jobId ? `${advancedApi.layerUrl(jobId, layer)}?v=${jobId}` : "";

  useEffect(() => {
    setRulerMasks({});
    if (!jobId) return undefined;
    let cancelled = false;
    const names = ["mask", "vegetation-mask", "fire-hotspots-mask", "possible-active-fire-mask"]
      .filter((name) => availableLayers.has(name));
    Promise.all(names.map(async (name) => [
      name,
      await loadRulerMask(`${advancedApi.layerUrl(jobId, name)}?v=${jobId}`),
    ])).then((entries) => {
      if (!cancelled) setRulerMasks(Object.fromEntries(entries));
    });
    return () => { cancelled = true; };
  }, [jobId, metrics?.available_layers]);

  const drawScenario = useCallback(() => {
    const surface = surfaceRef.current;
    const image = imageRef.current;
    const canvas = canvasRef.current;
    if (!surface || !canvas) return;
    const width = Number.parseFloat(surface.style.width) || surface.clientWidth;
    const height = Number.parseFloat(surface.style.height) || surface.clientHeight;
    if (!width || !height) return;
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const context = canvas.getContext("2d");
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, width, height);
    if (!image?.naturalWidth || !grid) return;

    const scaleX = width / (grid.ancho_px || image.naturalWidth);
    const scaleY = height / (grid.alto_px || image.naturalHeight);

    if (progressionFront?.length > 2) {
      context.beginPath();
      progressionFront.forEach(([x, y], index) => {
        const px = x * scaleX;
        const py = y * scaleY;
        if (index === 0) context.moveTo(px, py);
        else context.lineTo(px, py);
      });
      context.closePath();
      context.fillStyle = "rgba(255, 96, 33, .16)";
      context.fill();
      context.strokeStyle = "#ff5b27";
      context.lineWidth = 2.25;
      context.setLineDash([7, 5]);
      context.stroke();
      context.setLineDash([]);
    }

    if (origin) {
      const x = origin.x * scaleX;
      const y = origin.y * scaleY;
      context.beginPath();
      context.arc(x, y, 7, 0, Math.PI * 2);
      context.fillStyle = "#ed335e";
      context.fill();
      context.lineWidth = 2;
      context.strokeStyle = "white";
      context.stroke();
    }
  }, [grid, origin, progressionFront]);

  useEffect(() => {
    drawScenario();
    const surface = surfaceRef.current;
    if (!surface || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(drawScenario);
    observer.observe(surface);
    return () => observer.disconnect();
  }, [drawScenario, layer, source]);

  const selectOrigin = (event) => {
    if (!selectingOrigin || !grid) return;
    const image = imageRef.current;
    if (!image?.naturalWidth) return;
    const rect = image.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right
      || event.clientY < rect.top || event.clientY > rect.bottom || !rect.width || !rect.height) return;
    const x = ((event.clientX - rect.left) / rect.width) * grid.ancho_px;
    const y = ((event.clientY - rect.top) / rect.height) * grid.alto_px;
    onOriginSelect({
      x: Math.max(0, Math.min(grid.ancho_px - 1, Number(x.toFixed(2)))),
      y: Math.max(0, Math.min(grid.alto_px - 1, Number(y.toFixed(2)))),
    });
  };

  return (
    <div className="advanced-viewer">
      <div className="advanced-viewer-toolbar">
        <div className="advanced-layer-control" role="group" aria-label="Capas del análisis avanzado">
          {choices.map(([id, label, Icon]) => (
            <button
              key={id}
              className={`advanced-layer-choice${layer === id ? " is-active" : ""}`}
              type="button"
              aria-pressed={layer === id}
              onClick={() => setLayer(id)}
            >
              <Icon size={13} aria-hidden="true" />{label}
            </button>
          ))}
        </div>
        <div className="advanced-viewer-meta">
          {grid && <span className="advanced-grid-label">{grid.ancho_px} × {grid.alto_px} px</span>}
        </div>
      </div>
      <div className="advanced-image-stage">
        {source ? (
          <ZoomableImageViewport
            className="zoomable-viewport--advanced"
            imageRef={imageRef}
            surfaceRef={surfaceRef}
            imageClassName={`advanced-result-image${selectingOrigin ? " is-selecting-origin" : ""}`}
            src={source}
            alt={layer === "fire-hotspots"
                ? "Candidatos visuales de focos resaltados para revisión"
                : layer === "reference-wildfires"
                  ? "Composición Wildfires usada para extraer los focos"
                  : `Capa avanzada ${layer}`}
            resetKey={jobId}
            allowLeftPan={!selectingOrigin}
            allowDoubleClick={!selectingOrigin}
            showCrosshair={selectingOrigin}
            suppressClickAfterDrag={selectingOrigin}
            onLoad={drawScenario}
            onClick={selectOrigin}
            onError={() => onError("No se pudo cargar esta capa del análisis avanzado.")}
          >
            <canvas ref={canvasRef} className="advanced-scenario-canvas" aria-hidden="true" />
            <GsdScaleRuler grid={grid} imageRef={imageRef} maskImages={rulerMasks} />
          </ZoomableImageViewport>
        ) : (
          <div className="advanced-viewer-empty">
            <Flame size={32} aria-hidden="true" />
            <strong>El resultado avanzado aparecerá aquí</strong>
            <span>Selecciona una escena o carga True Color y SWIR.</span>
          </div>
        )}
        {selectingOrigin && <span className="advanced-origin-hint">Haz clic en un foco observado para fijar un único origen</span>}
      </div>
      <p className="advanced-viewer-caption">
        {layer === "fire-hotspots"
          ? "Amarillo con halo fucsia: marcas extraídas directamente de Wildfires, también bajo humo."
          : layer === "vegetation"
            ? "Verde: verdor aparente coincidente entre composiciones; no es una clasificación validada de cobertura vegetal."
            : layer === "possible-active-fire"
              ? "Naranja: píxeles etiquetados como posible fuego por el clasificador activo; requiere revisión independiente."
              : layer === "reference-wildfires"
                ? "Los focos se extraen de las marcas cálidas brillantes de esta composición Wildfires."
                : "Las capas son estimaciones a partir de composiciones renderizadas."}
      </p>
    </div>
  );
}

export default function AdvancedWorkspace({ version, onVersionChange, isActive }) {
  const [scenes, setScenes] = useState([]);
  const [source, setSource] = useState("preloaded");
  const [sceneId, setSceneId] = useState("");
  const [connected, setConnected] = useState(false);
  const [connectionLabel, setConnectionLabel] = useState("Conectando…");
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [jobLabel, setJobLabel] = useState("pareja_cargada");
  const [jobTimestamp, setJobTimestamp] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [progress, setProgress] = useState({ stage: "Listo para analizar", value: 0 });
  const [error, setError] = useState("");
  const [layer, setLayer] = useState("fire-hotspots");
  const [origin, setOrigin] = useState(null);
  const [selectingOrigin, setSelectingOrigin] = useState(false);
  const [temperature, setTemperature] = useState("30");
  const [humidity, setHumidity] = useState("30");
  const [windFrom, setWindFrom] = useState("270");
  const [windSpeed, setWindSpeed] = useState("20");
  const [advance, setAdvance] = useState("3");
  const [weatherTime, setWeatherTime] = useState("");
  const [weatherSource, setWeatherSource] = useState("");
  const [scenario, setScenario] = useState(null);
  const [scenarioFrame, setScenarioFrame] = useState(0);
  const [scenarioPlaying, setScenarioPlaying] = useState(false);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const analysisRunRef = useRef(0);

  useEffect(() => {
    let active = true;
    advancedApi.scenes().then((response) => {
      if (!active) return;
      const available = response.scenes || [];
      setScenes(available);
      if (available.length) {
        setSceneId(available[0].id);
      } else {
        setSource("upload");
      }
      setConnected(true);
      setConnectionLabel("Conectado");
    }).catch((cause) => {
      if (!active) return;
      setConnected(false);
      setConnectionLabel("Sin conexión");
      setError(cause?.message || "No se pudieron cargar las escenas avanzadas.");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!isActive || !scenarioPlaying || !scenario?.frames?.length) return undefined;
    if (scenarioFrame >= scenario.frames.length - 1) {
      setScenarioPlaying(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setScenarioFrame((frame) => frame + 1), 240);
    return () => window.clearTimeout(timer);
  }, [isActive, scenarioPlaying, scenario, scenarioFrame]);

  const resetAnalysis = () => {
    analysisRunRef.current += 1;
    setRunning(false);
    setJobId(null);
    setAnalysis(null);
    setProgress({ stage: "Listo para analizar", value: 0 });
    setOrigin(null);
    setSelectingOrigin(false);
    setScenario(null);
    setScenarioFrame(0);
    setScenarioPlaying(false);
    setScenarioError("");
    setError("");
  };

  const handleSourceChange = (nextSource) => {
    if (source === nextSource) return;
    setSource(nextSource);
    resetAnalysis();
  };

  const handleSceneChange = (nextScene) => {
    if (sceneId === nextScene) return;
    setSceneId(nextScene);
    resetAnalysis();
  };

  const runAnalysis = async (event) => {
    event.preventDefault();
    const runToken = ++analysisRunRef.current;
    setError("");
    let request;
    let nextJobLabel = scenes.find((scene) => scene.id === sceneId)?.label || "pareja_cargada";
    try {
      if (source === "preloaded") {
        if (!sceneId) throw new Error("Selecciona una escena para analizar.");
        request = { source: "preloaded", scene: sceneId };
      } else {
        const form = event.currentTarget;
        const trueFile = form.elements.namedItem("advanced-true-color")?.files?.[0];
        const swirFile = form.elements.namedItem("advanced-swir")?.files?.[0];
        const wildfireFile = form.elements.namedItem("advanced-wildfires")?.files?.[0];
        if (!trueFile || !swirFile) throw new Error("Carga True Color y SWIR; Wildfires es opcional.");
        request = {
          source: "upload",
          true_color: await fileToBase64(trueFile),
          swir: await fileToBase64(swirFile),
          wildfires_reference: wildfireFile ? await fileToBase64(wildfireFile) : "",
        };
        nextJobLabel = trueFile.name.replace(/\.[^.]+$/, "") || "pareja_cargada";
      }

      setJobLabel(nextJobLabel);
      setJobTimestamp(localDateStamp());
      setJobId(null);
      setAnalysis(null);
      setOrigin(null);
      setSelectingOrigin(false);
      setScenario(null);
      setScenarioFrame(0);
      setScenarioPlaying(false);
      setScenarioError("");
      setRunning(true);
      setConnectionLabel("Analizando avanzado…");
      setProgress({ stage: "Preparando análisis avanzado", value: 0 });
      const started = await advancedApi.analyze(request);
      if (runToken !== analysisRunRef.current) return;
      setJobId(started.job_id);

      while (true) {
        const job = await advancedApi.job(started.job_id);
        if (runToken !== analysisRunRef.current) return;
        setProgress({ stage: job.stage || "Procesando", value: job.progress ?? 0 });
        if (job.state === "complete") {
          setAnalysis(job);
          setLayer(job.metrics?.available_layers?.includes("fire-hotspots") ? "fire-hotspots" : "candidates");
          setRunning(false);
          setConnectionLabel("Conectado");
          return;
        }
        if (job.state === "error") {
          const message = job.error || "El análisis avanzado quedó incompleto.";
          setAnalysis(job);
          setError(message);
          setRunning(false);
          setConnectionLabel("Conectado");
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 650));
      }
    } catch (cause) {
      if (runToken !== analysisRunRef.current) return;
      setError(cause?.message || "No se pudo iniciar el análisis avanzado.");
      setRunning(false);
      setConnectionLabel(cause instanceof TypeError ? "Sin conexión" : "Conectado");
      if (cause instanceof TypeError) setConnected(false);
    }
  };

  const runProgression = async (event) => {
    event.preventDefault();
    setScenarioError("");
    setScenarioLoading(true);
    try {
      if (!jobId || analysis?.state !== "complete") throw new Error("Primero termina el análisis avanzado.");
      if (!origin) throw new Error("Selecciona un único origen en la imagen.");
      const generated = await advancedApi.fireProgression(jobId, {
        origin,
        temperature_c: numberFromInput(temperature, "La temperatura"),
        relative_humidity_pct: numberFromInput(humidity, "La humedad relativa"),
        wind_from_deg: numberFromInput(windFrom, "La dirección del viento"),
        wind_speed_kmh: numberFromInput(windSpeed, "La velocidad del viento"),
        base_advance_px: numberFromInput(advance, "El avance visual"),
        weather_time: weatherTime,
        weather_source: weatherSource,
        steps: 16,
      });
      setScenario(generated);
      setScenarioFrame(0);
      setScenarioPlaying(true);
      setSelectingOrigin(false);
    } catch (cause) {
      setScenarioError(cause?.message || "No se pudo generar el escenario.");
    } finally {
      setScenarioLoading(false);
    }
  };

  const downloadLayer = async (name, filename) => {
    if (!jobId) return;
    try {
      const extension = filename.match(/\.[^.]+$/)?.[0] || "";
      const artifact = filename.slice(0, filename.length - extension.length).replace(/^lumbre_/, "");
      const exportFilename = `lumbre_${slugForFilename(jobLabel)}_${jobTimestamp || localDateStamp()}_${jobId.slice(0, 8)}_${slugForFilename(artifact)}${extension}`;
      saveBlob(await advancedApi.downloadLayer(jobId, name), exportFilename);
    } catch (cause) {
      setError(cause?.message || "No se pudo descargar la capa.");
    }
  };

  const metrics = analysis?.metrics;
  const grid = analysis?.grid;
  const hasResult = analysis?.state === "complete";
  const progressionFront = scenario?.frames?.[scenarioFrame]?.front || null;
  const layerName = INPUT_LAYERS.find(([id]) => id === layer)?.[1]
    || (layer === "reference-wildfires" ? "Wildfires" : "Resultado");

  return (
    <main className={`workspace advanced-workspace${isActive ? "" : " mode-panel-hidden"}`}>
      <aside className="control-panel advanced-control-panel" id="advanced-setup" aria-label="Configuración del análisis avanzado">
        <div className="sidebar-fixed">
          <div className="panel-heading">
            <h1 className="panel-brand-heading">
              <span className="brand-mark-wrap" aria-hidden="true"><span className="brand-pixel-flame" /></span>
              <span className="brand-heading-copy"><strong>LUMBRE</strong><small>Análisis</small></span>
            </h1>
            <VersionSwitcher version={version} onChange={onVersionChange} />
            <span className="sr-only" role="status">{connectionLabel}</span>
          </div>
          <div className="sidebar-heading-divider" aria-hidden="true" />

          <section className="advanced-progress" aria-live="polite">
            <div><span>{progress.stage}</span><strong>{progress.value}%</strong></div>
            <span className="advanced-progress-track"><span style={{ width: `${progress.value}%` }} /></span>
          </section>

          <button className="run-button advanced-run-button" type="submit" form="advanced-analysis-form" disabled={!connected || running || (source === "preloaded" && !scenes.length)}>
            <Activity size={15} aria-hidden="true" />{running ? "Analizando…" : "Analizar reto avanzado"}
          </button>
          {error && <p className="form-error" role="alert">{error}</p>}
          {analysis?.state === "error" && <p className="form-error" role="alert">{analysis.error}</p>}
        </div>

        <div className="sidebar-scroll">
        <form id="advanced-analysis-form" onSubmit={runAnalysis}>
          <div className="source-switch" role="tablist" aria-label="Origen de imágenes para avanzado">
            {[["preloaded", "Escenas"], ["upload", "Subir imágenes"]].map(([id, label]) => (
              <button
                key={id}
                className={`source-tab${source === id ? " is-active" : ""}`}
                type="button"
                role="tab"
                aria-selected={source === id}
                onClick={() => handleSourceChange(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {source === "preloaded" ? (
            <section className="source-content">
              <span className="field-label">Escena del reto</span>
              {scenes.length ? (
                <div className="advanced-scene-gallery" role="group" aria-label="Elegir escena avanzada">
                  {scenes.map((scene) => (
                    <button
                      key={scene.id}
                      type="button"
                      className={`advanced-scene-card${scene.id === sceneId ? " is-selected" : ""}`}
                      aria-pressed={scene.id === sceneId}
                      onClick={() => handleSceneChange(scene.id)}
                    >
                      <span className={`advanced-scene-previews${scene.has_wildfires_reference ? " has-reference" : ""}`}>
                        <span><img src={advancedApi.scenePreviewUrl(scene.id, "true-color")} alt="" loading="lazy" /><small>True Color</small></span>
                        <span><img src={advancedApi.scenePreviewUrl(scene.id, "swir")} alt="" loading="lazy" /><small>SWIR</small></span>
                        {scene.has_wildfires_reference && <span><img src={advancedApi.scenePreviewUrl(scene.id, "wildfires")} alt="" loading="lazy" /><small>Wildfires</small></span>}
                      </span>
                      <span className="advanced-scene-label"><strong>{scene.label}</strong><small>{scene.has_wildfires_reference ? "Incluye Wildfires para los focos" : "Pareja True Color + SWIR"}</small></span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="field-help">{connected ? "No hay escenas precargadas." : "Cargando escenas…"}</p>
              )}
            </section>
          ) : (
            <section className="source-content advanced-upload-fields">
              <label className="field-label" htmlFor="advanced-true-color">Imagen True Color</label>
              <input className="file-control" id="advanced-true-color" name="advanced-true-color" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
              <label className="field-label" htmlFor="advanced-swir">Imagen SWIR</label>
              <input className="file-control" id="advanced-swir" name="advanced-swir" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
              <label className="field-label" htmlFor="advanced-wildfires">Wildfires <small>para obtener focos</small></label>
              <input className="file-control" id="advanced-wildfires" name="advanced-wildfires" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
              <p className="field-help">Wildfires solo se muestra para comparar; no entra en la detección.</p>
            </section>
          )}

          <p className="field-help">Las escenas precargadas aplican su escala automáticamente. Las imágenes propias sin georreferencia se miden en píxeles.</p>
        </form>
        <p className="advanced-method-note">
          Los focos se extraen directamente de Wildfires, también bajo humo. True Color y SWIR se usan para las demás capas.
        </p>
        </div>
      </aside>

      <section className="analysis-column advanced-analysis-column" id="advanced-map" aria-label="Resultado avanzado">
        <div className="viewer-card advanced-viewer-card">
          <AdvancedViewer
            jobId={hasResult ? jobId : null}
            grid={grid}
            metrics={metrics}
            layer={layer}
            setLayer={setLayer}
            origin={origin}
            progressionFront={progressionFront}
            selectingOrigin={selectingOrigin}
            onOriginSelect={(point) => {
              setOrigin(point);
              setScenario(null);
              setScenarioFrame(0);
              setScenarioPlaying(false);
              setScenarioError("");
            }}
            onError={setError}
          />
        </div>
      </section>

      <aside className="results-column advanced-results-column" id="advanced-results" aria-label="Métricas y escenario avanzado">
        <div className="results-heading"><h2>Resultado avanzado</h2></div>
        {hasResult ? (
          <>
            <p className="advanced-result-layer-label">Capa visible: <strong>{layerName}</strong></p>
            <div className="advanced-metric-grid">
              <article className="advanced-metric-card"><span>Verdor aparente</span><strong>{formatNumber(metrics?.vegetation_pct || 0, 1)} %</strong><small>{formatNumber(metrics?.vegetation_pixels || 0)} px · visual</small></article>
              <article className="advanced-metric-card is-hotspot"><span>Focos Wildfires</span><strong>{metrics?.hotspot_source === "wildfires" ? formatNumber(metrics.hotspot_wildfires_components || 0) : "—"}</strong><small>{metrics?.hotspot_source === "wildfires" ? `${formatNumber(metrics.hotspot_wildfires_pixels || 0)} px · extraídos de Wildfires` : "Wildfires no disponible"}</small></article>
              {metrics?.active_fire_class_available && <article className="advanced-metric-card"><span>Clase de fuego posible</span><strong>{formatNumber(metrics.active_fire_class_pixels)} px</strong></article>}
              <article className="advanced-metric-card"><span>Superficie afectada candidata</span><strong>{formatNumber(metrics?.burned_surface_candidate_pct || 0, 2)} %</strong><small>{formatNumber(metrics?.burned_surface_area || 0, 1)} {metrics?.burned_surface_area_unit}</small></article>
              <article className="advanced-metric-card"><span>Humo probable</span><strong>{formatNumber(metrics?.smoke_pct || 0, 1)} %</strong></article>
              <article className="advanced-metric-card"><span>Agua posible</span><strong>{formatNumber(metrics?.water_possible_pixels || 0)} px</strong></article>
            </div>

            <div className="advanced-export-actions">
              <button type="button" className="export-button" onClick={() => downloadLayer("fire-hotspots", "lumbre_candidatos_focos.png")}>Candidatos de focos <span>PNG ↓</span></button>
              <button type="button" className="export-button" onClick={() => downloadLayer("candidates", "lumbre_clasificacion_avanzada.png")}>Clases <span>PNG ↓</span></button>
              <button type="button" className="export-button" onClick={() => downloadLayer("mask", "lumbre_superficie_candidata.png")}>Máscara de superficie <span>PNG ↓</span></button>
            </div>

            <section className="advanced-scenario-panel" aria-label="Escenario de progresión ilustrativo">
              <div className="advanced-section-heading"><h3>Progresión ilustrativa</h3><span>experimental</span></div>
              <p className="advanced-scenario-intro">Elige un foco observado y fija un único origen manual. La cicatriz completa no se usa como fuego.</p>
              <button
                className={`advanced-origin-button${selectingOrigin ? " is-active" : ""}`}
                type="button"
                disabled={!hasResult}
                onClick={() => {
                  setSelectingOrigin((active) => !active);
                  setScenario(null);
                  setScenarioPlaying(false);
                  setScenarioError("");
                }}
              >
                <Flame size={14} aria-hidden="true" />{selectingOrigin ? "Haz clic en el foco observado…" : origin ? `Origen: (${formatNumber(origin.x, 1)}, ${formatNumber(origin.y, 1)}) px · cambiar` : "Elegir origen en imagen"}
              </button>

              <form className="advanced-weather-form" onSubmit={runProgression}>
                <div className="advanced-weather-grid">
                  <label>Temperatura del aire · °C<input value={temperature} inputMode="decimal" onChange={(event) => setTemperature(event.target.value)} /></label>
                  <label>Humedad relativa · %<input value={humidity} inputMode="decimal" onChange={(event) => setHumidity(event.target.value)} /></label>
                  <label>Viento «desde» · °<input value={windFrom} inputMode="decimal" onChange={(event) => setWindFrom(event.target.value)} /></label>
                  <label>Velocidad del viento · km/h<input value={windSpeed} inputMode="decimal" onChange={(event) => setWindSpeed(event.target.value)} /></label>
                  <label>Avance visual · px/paso<input value={advance} inputMode="decimal" onChange={(event) => setAdvance(event.target.value)} /></label>
                </div>
                <label className="advanced-weather-source">Hora y zona de los datos<input value={weatherTime} maxLength={120} onChange={(event) => setWeatherTime(event.target.value)} placeholder="Ej.: 2026-07-29 13:00 UTC" /></label>
                <label className="advanced-weather-source">Fuente meteorológica<input value={weatherSource} maxLength={120} onChange={(event) => setWeatherSource(event.target.value)} placeholder="Fuente y URL o estación, si se conocen" /></label>
                <p className="advanced-weather-note">Introduce datos de la hora de adquisición. La aplicación no los completa automáticamente.</p>
                <button className="advanced-generate-button" type="submit" disabled={!hasResult || !origin || scenarioLoading}>
                  {scenarioLoading ? "Generando…" : "Generar progresión visual"}
                </button>
                {scenarioError && <p className="form-error" role="alert">{scenarioError}</p>}
              </form>

              {scenario && <div className="advanced-scenario-playback">
                <div className="advanced-playback-heading"><strong>Paso {scenarioFrame + 1} / {scenario.frames.length}</strong><button type="button" onClick={() => setScenarioPlaying((playing) => !playing)}><Play size={13} aria-hidden="true" />{scenarioPlaying ? "Pausar" : "Reproducir"}</button></div>
                <input aria-label="Recorrer pasos de progresión" type="range" min="0" max={scenario.frames.length - 1} value={scenarioFrame} onChange={(event) => {
                  setScenarioPlaying(false);
                  setScenarioFrame(Number(event.target.value));
                }} />
                <p>{scenario.weather_provenance?.source || "Fuente sin indicar"}{scenario.weather_provenance?.time_and_timezone ? ` · ${scenario.weather_provenance.time_and_timezone}` : ""}</p>
              </div>}
            </section>

            <p className="advanced-caveat">Los focos reproducen las marcas cálidas brillantes de Wildfires; el humo y la máscara de superficie no las descartan. La extracción trabaja con colores JPG/PNG y no mide temperatura. El verdor es aparente. La progresión es geométrica en píxeles, no una predicción validada.</p>
            {metrics?.reference_warning && <p className="form-error" role="status">{metrics.reference_warning}</p>}
          </>
        ) : (
          <p className="advanced-empty-result">Cuando termine el análisis, aquí aparecerán las clases de escena, los candidatos de focos y las herramientas de progresión.</p>
        )}
      </aside>
    </main>
  );
}
