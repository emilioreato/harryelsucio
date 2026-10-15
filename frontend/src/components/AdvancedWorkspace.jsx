import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Flame, Image as ImageIcon, Layers3, Play, ScanLine } from "lucide-react";
import { advancedApi, fileToBase64 } from "../services/api.js";
import { formatNumber } from "../domain/measurements.js";
import VersionSwitcher from "./VersionSwitcher.jsx";

const INPUT_LAYERS = [
  ["true-color", "True Color", ImageIcon],
  ["swir", "SWIR", ScanLine],
  ["candidates", "Clases", Layers3],
  ["vegetation", "Vegetación", Layers3],
  ["possible-active-fire", "Fuego posible", Flame],
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
  const stageRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const availableLayers = new Set(metrics?.available_layers || []);
  const choices = INPUT_LAYERS.filter(([id]) => availableLayers.has(id));
  if (availableLayers.has("reference-wildfires")) {
    choices.push(["reference-wildfires", "Wildfires · ref.", Layers3]);
  }
  const source = jobId ? `${advancedApi.layerUrl(jobId, layer)}?v=${jobId}` : "";

  const drawScenario = useCallback(() => {
    const stage = stageRef.current;
    const image = imageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas) return;
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    const context = canvas.getContext("2d");
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    context.clearRect(0, 0, width, height);
    if (!image?.naturalWidth || !grid) return;

    const stageRect = stage.getBoundingClientRect();
    const imageRect = image.getBoundingClientRect();
    const left = imageRect.left - stageRect.left;
    const top = imageRect.top - stageRect.top;
    const scaleX = imageRect.width / (grid.ancho_px || image.naturalWidth);
    const scaleY = imageRect.height / (grid.alto_px || image.naturalHeight);
    context.save();
    context.beginPath();
    context.rect(left, top, imageRect.width, imageRect.height);
    context.clip();

    if (progressionFront?.length > 2) {
      context.beginPath();
      progressionFront.forEach(([x, y], index) => {
        const px = left + x * scaleX;
        const py = top + y * scaleY;
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
      const x = left + origin.x * scaleX;
      const y = top + origin.y * scaleY;
      context.beginPath();
      context.arc(x, y, 7, 0, Math.PI * 2);
      context.fillStyle = "#ed335e";
      context.fill();
      context.lineWidth = 2;
      context.strokeStyle = "white";
      context.stroke();
    }
    context.restore();
  }, [grid, origin, progressionFront]);

  useEffect(() => {
    drawScenario();
    const stage = stageRef.current;
    if (!stage || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(drawScenario);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [drawScenario, layer, source]);

  const selectOrigin = (event) => {
    if (!selectingOrigin || !grid) return;
    const image = imageRef.current;
    if (!image?.naturalWidth) return;
    const rect = image.getBoundingClientRect();
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
        {grid && <span className="advanced-grid-label">{grid.ancho_px} × {grid.alto_px} px</span>}
      </div>
      <div className="advanced-image-stage" ref={stageRef}>
        {source ? (
          <>
            <img
              ref={imageRef}
              className={`advanced-result-image${selectingOrigin ? " is-selecting-origin" : ""}`}
              src={source}
              alt={layer === "fire-hotspots"
                ? "Candidatos visuales de focos resaltados para revisión"
                : layer === "reference-wildfires"
                  ? "Referencia Wildfires, solo para comparación visual"
                  : `Capa avanzada ${layer}`}
              draggable="false"
              onLoad={drawScenario}
              onClick={selectOrigin}
              onError={() => onError("No se pudo cargar esta capa del análisis avanzado.")}
            />
            <canvas ref={canvasRef} className="advanced-scenario-canvas" aria-hidden="true" />
          </>
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
          ? "Amarillo: candidato cálido en ambas composiciones. Fucsia: halo visual. No representa temperatura."
          : layer === "vegetation"
            ? "Verde: vegetación estimada por la clasificación visual de la escena."
            : layer === "possible-active-fire"
              ? "Naranja: clase visual de posible fuego activo; requiere revisión independiente."
              : layer === "reference-wildfires"
                ? "Wildfires es una referencia de comparación y no se usa como verdad terreno."
                : "Las capas son estimaciones a partir de composiciones renderizadas."}
      </p>
    </div>
  );
}

export default function AdvancedWorkspace({ version, onVersionChange }) {
  const [scenes, setScenes] = useState([]);
  const [source, setSource] = useState("preloaded");
  const [sceneId, setSceneId] = useState("");
  const [gsd, setGsd] = useState("");
  const [connected, setConnected] = useState(false);
  const [connectionLabel, setConnectionLabel] = useState("Conectando…");
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState(null);
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
        setGsd(available[0].gsd_m_per_px ? String(available[0].gsd_m_per_px) : "");
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

  const selectedScene = scenes.find((item) => item.id === sceneId);
  useEffect(() => {
    if (source !== "preloaded") {
      setGsd("");
      return;
    }
    setGsd(selectedScene?.gsd_m_per_px ? String(selectedScene.gsd_m_per_px) : "");
  }, [source, selectedScene?.id, selectedScene?.gsd_m_per_px]);

  useEffect(() => {
    if (!scenarioPlaying || !scenario?.frames?.length) return undefined;
    if (scenarioFrame >= scenario.frames.length - 1) {
      setScenarioPlaying(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setScenarioFrame((frame) => frame + 1), 240);
    return () => window.clearTimeout(timer);
  }, [scenarioPlaying, scenario, scenarioFrame]);

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
    try {
      const gsdValue = gsd.trim() ? numberFromInput(gsd, "El GSD") : null;
      if (gsdValue !== null && gsdValue <= 0) throw new Error("El GSD debe ser positivo en metros por píxel.");
      if (source === "preloaded") {
        if (!sceneId) throw new Error("Selecciona una escena para analizar.");
        request = { source: "preloaded", scene: sceneId, gsd_m_per_px: gsdValue };
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
          gsd_m_per_px: gsdValue,
        };
      }

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
      saveBlob(await advancedApi.downloadLayer(jobId, name), filename);
    } catch (cause) {
      setError(cause?.message || "No se pudo descargar la capa.");
    }
  };

  const metrics = analysis?.metrics;
  const grid = analysis?.grid;
  const hasResult = analysis?.state === "complete";
  const progressionFront = scenario?.frames?.[scenarioFrame]?.front || null;
  const layerName = INPUT_LAYERS.find(([id]) => id === layer)?.[1]
    || (layer === "reference-wildfires" ? "Wildfires · ref." : "Resultado");

  return (
    <main className="workspace advanced-workspace">
      <aside className="control-panel advanced-control-panel" id="advanced-setup" aria-label="Configuración del análisis avanzado">
        <div className="panel-heading">
          <h1 className="panel-brand-heading">
            <span className="brand-mark-wrap" aria-hidden="true"><span className="brand-pixel-flame" /></span>
            <span className="brand-heading-copy"><strong>LUMBRE</strong><small>Reto avanzado</small></span>
          </h1>
          <span className={`connection-pill${connected ? " is-ready" : error ? " is-error" : ""}`}>
            <span className="status-dot" />{connectionLabel}
          </span>
        </div>
        <VersionSwitcher version={version} onChange={onVersionChange} />

        <section className="advanced-progress" aria-live="polite">
          <div><span>{progress.stage}</span><strong>{progress.value}%</strong></div>
          <span className="advanced-progress-track"><span style={{ width: `${progress.value}%` }} /></span>
        </section>

        <form onSubmit={runAnalysis}>
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
                      <span className="advanced-scene-label"><strong>{scene.label}</strong><small>{scene.has_wildfires_reference ? "Incluye referencia Wildfires" : "Pareja True Color + SWIR"}</small></span>
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
              <label className="field-label" htmlFor="advanced-wildfires">Referencia Wildfires <small>opcional</small></label>
              <input className="file-control" id="advanced-wildfires" name="advanced-wildfires" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
              <p className="field-help">Wildfires solo se muestra para comparar; no entra en la detección.</p>
            </section>
          )}

          <label className="field-label" htmlFor="advanced-gsd">Resolución declarada <small>GSD, m/píxel (opcional)</small></label>
          <input
            id="advanced-gsd"
            className="field-control"
            inputMode="decimal"
            value={gsd}
            onChange={(event) => setGsd(event.target.value)}
            placeholder="Solo si conoces la escala"
          />
          <p className="field-help">Sin una escala fiable, las superficies se informan en píxeles.</p>

          <button className="run-button advanced-run-button" type="submit" disabled={!connected || running || (source === "preloaded" && !scenes.length)}>
            <Activity size={15} aria-hidden="true" />{running ? "Analizando…" : "Analizar reto avanzado"}
          </button>
          {error && <p className="form-error" role="alert">{error}</p>}
          {analysis?.state === "error" && <p className="form-error" role="alert">{analysis.error}</p>}
        </form>
        <p className="advanced-method-note">
          El flujo avanzado ejecuta la clasificación de escena, estima vegetación y resalta candidatos visuales cálidos coincidentes entre True Color y SWIR.
        </p>
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
              <article className="advanced-metric-card"><span>Vegetación estimada</span><strong>{formatNumber(metrics?.vegetation_pct || 0, 1)} %</strong><small>{formatNumber(metrics?.vegetation_pixels || 0)} px</small></article>
              <article className="advanced-metric-card is-hotspot"><span>Candidatos de focos</span><strong>{formatNumber(metrics?.visual_hotspot_components || 0)}</strong><small>{formatNumber(metrics?.visual_hotspot_candidate_pixels || 0)} px</small></article>
              <article className="advanced-metric-card"><span>Clase de fuego posible</span><strong>{formatNumber(metrics?.active_fire_class_pixels || 0)} px</strong></article>
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

            <p className="advanced-caveat">Los focos resaltados son candidatos visuales calculados sobre JPG/PNG renderizados; no miden temperatura ni confirman fuego activo. La progresión es una forma geométrica en píxeles, no una predicción validada. Revisa también la referencia Wildfires: no es verdad terreno.</p>
            {metrics?.reference_warning && <p className="form-error" role="status">{metrics.reference_warning}</p>}
          </>
        ) : (
          <p className="advanced-empty-result">Cuando termine el análisis, aquí aparecerán las clases de escena, los candidatos de focos y las herramientas de progresión.</p>
        )}
      </aside>
    </main>
  );
}
