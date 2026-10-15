import { useEffect, useMemo, useState } from "react";
import AdvancedSettings from "./components/AdvancedSettings.jsx";
import ImageViewer from "./components/ImageViewer.jsx";
import { api, fileToBase64 } from "./services/api.js";
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

function loadNotes() {
  try {
    const notes = JSON.parse(localStorage.getItem("pyroscope-notes") || "[]");
    return Array.isArray(notes) ? notes.slice(0, 12) : [];
  } catch {
    return [];
  }
}

function App() {
  const [scenes, setScenes] = useState([]);
  const [detectors, setDetectors] = useState([]);
  const [connection, setConnection] = useState({ ready: false, label: "Conectando con el motor local…" });
  const [source, setSource] = useState("preloaded");
  const [sceneId, setSceneId] = useState("");
  const [method, setMethod] = useState("kmeans");
  const [sensitivity, setSensitivity] = useState(5);
  const [numClasses, setNumClasses] = useState(7);
  const [minimumArea, setMinimumArea] = useState("0.15");
  const [maxDistance, setMaxDistance] = useState("10");
  const [keepSeparate, setKeepSeparate] = useState(false);
  const [gsd, setGsd] = useState("");
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
  const [tool, setTool] = useState("view");
  const [marks, setMarks] = useState([]);
  const [polygonClosed, setPolygonClosed] = useState(false);
  const [inspectedPixel, setInspectedPixel] = useState(null);
  const [notes, setNotes] = useState(loadNotes);
  const [noteText, setNoteText] = useState("");

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
        setConnection({ ready: true, label: "Motor Python conectado" });
      })
      .catch((cause) => {
        if (!active) return;
        setConnection({ ready: false, label: "No se pudo conectar con el motor local" });
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
  const notesAsText = useMemo(() => notes.map((note) => `${note.time} · ${note.text}`), [notes]);

  const collectSettings = () => {
    const minimum = numberFromInput(minimumArea, "El área mínima");
    if (minimum < 0.01 || minimum > 1) throw new Error("El área mínima debe estar entre 0,01 y 1 %.");
    const distance = numberFromInput(maxDistance, "El radio máximo");
    if (!keepSeparate && (!Number.isInteger(distance) || distance < 3 || distance > 20)) {
      throw new Error("El radio máximo debe ser un entero entre 3 y 20 %.");
    }
    const gsdNumber = gsd.trim() ? numberFromInput(gsd, "El GSD") : null;
    if (gsdNumber !== null && gsdNumber <= 0) throw new Error("El GSD debe ser positivo en metros por píxel.");

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
        const form = event.currentTarget;
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
      setPolygonClosed(false);
      setInspectedPixel(null);
      setRunning(true);
      setConnection({ ready: true, label: "El motor Python está procesando" });
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
          setConnection({ ready: true, label: "Motor Python conectado" });
          return;
        }
        if (job.state === "error") throw new Error(job.error || "No se pudo completar el análisis.");
        await new Promise((resolve) => window.setTimeout(resolve, 650));
      }
    } catch (cause) {
      setError(cause.message);
      setResult({ state: "error", error: cause.message });
      setProgress({ label: "No se pudo completar", value: 0 });
      setRunning(false);
      setConnection((current) => ({ ...current, label: "Motor Python conectado" }));
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
      new Blob([JSON.stringify({ esquema: "pyroscope-imagen-v1", job_id: jobId, sistema_coordenadas: grid, elementos }, null, 2)], { type: "application/json" }),
      "espejo_ustorio_mediciones.json",
    );
  };

  const addNote = (event) => {
    event.preventDefault();
    const text = noteText.trim();
    if (!text) return;
    const next = [
      { time: new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }), text },
      ...notes,
    ].slice(0, 12);
    setNotes(next);
    localStorage.setItem("pyroscope-notes", JSON.stringify(next));
    setNoteText("");
  };

  const detectorDescription = selectedDetector?.description || "";
  const summary = metrics && settingsUsed
    ? `${metrics.detector}. Rejilla ${metrics.grid_width} × ${metrics.grid_height} px. Píxeles excluidos como agua: ${formatNumber(metrics.water_excluded)}. Regiones remotas descartadas: ${metrics.remote_regions_discarded}. ${metrics.gsd_x_m ? `GSD efectivo ${formatNumber(metrics.gsd_x_m, 3)} × ${formatNumber(metrics.gsd_y_m, 3)} m/píxel.` : "Sin GSD; las medidas se expresan en píxeles."}`
    : "Al terminar, aquí se muestran el detector y la rejilla usada.";

  return (
    <>
      <header className="topbar">
        <a className="brand" href="/" aria-label="Espejo Ustorio, inicio">
          <span className="brand-mark" aria-hidden="true">◉</span>
          <span className="brand-copy"><strong>espejo ustorio</strong><small>Observatorio de superficie</small></span>
        </a>
        <div className="topbar-context">
          <span className={`status-dot${connection.ready ? " is-ready" : error ? " is-error" : ""}`} />
          <span>{connection.label}</span>
        </div>
      </header>

      <main className="workspace">
        <aside className="control-panel" aria-label="Configuración del análisis">
          <div className="panel-heading">
            <div><p className="eyebrow">ENTRADA</p><h1>Preparar análisis</h1></div>
            <span className="step-badge">01</span>
          </div>

          <form onSubmit={runAnalysis}>
            <div className="source-switch" role="tablist" aria-label="Origen de las imágenes">
              {[ ["preloaded", "Escenas"], ["upload", "Subir pareja"] ].map(([id, label]) => (
                <button key={id} className={`source-tab${source === id ? " is-active" : ""}`} type="button" role="tab" aria-selected={source === id} onClick={() => setSource(id)}>{label}</button>
              ))}
            </div>

            {source === "preloaded" ? (
              <section className="source-content">
                <label className="field-label" htmlFor="scene-select">Escena precargada</label>
                <select className="field-control" id="scene-select" value={sceneId} onChange={(event) => setSceneId(event.target.value)}>
                  {scenes.length ? scenes.map((scene) => <option value={scene.id} key={scene.id}>{scene.label}</option>) : <option value="">Buscando imágenes…</option>}
                </select>
                <p className="field-help">Cada escena incluye True Color y SWIR de la misma adquisición.</p>
              </section>
            ) : (
              <section className="source-content">
                <label className="field-label" htmlFor="true-color-file">Imagen True Color</label>
                <input className="file-control" name="true-color-file" id="true-color-file" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
                <label className="field-label second-file-label" htmlFor="swir-file">Imagen SWIR</label>
                <input className="file-control" name="swir-file" id="swir-file" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
                <p className="field-help">Usa dos imágenes alineadas de la misma escena y fecha.</p>
              </section>
            )}

            <div className="section-rule"><span>SEGMENTACIÓN</span></div>
            <label className="field-label" htmlFor="detector-select">Método de detección</label>
            <select className="field-control" id="detector-select" value={method} onChange={(event) => setMethod(event.target.value)}>
              {detectors.map((detector) => <option value={detector.id} key={detector.id}>{detector.name}</option>)}
            </select>
            <p className="field-help">{detectorDescription}</p>

            <div className="range-row">
              <label className="field-label" htmlFor="sensitivity">Sensibilidad</label>
              <output className="range-value">{sensitivity}</output>
            </div>
            <input className="range-control" id="sensitivity" type="range" min="1" max="10" value={sensitivity} onChange={(event) => setSensitivity(Number(event.target.value))} />

            {selectedDetector?.uses_num_classes !== false && <>
              <div className="range-row">
                <label className="field-label" htmlFor="num-classes">Grupos de color</label>
                <output className="range-value">{numClasses}</output>
              </div>
              <input className="range-control" id="num-classes" type="range" min="4" max="10" value={numClasses} onChange={(event) => setNumClasses(Number(event.target.value))} />
            </>}

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

            <AdvancedSettings value={advanced} onChange={setAdvanced} onReset={() => setAdvanced(defaultAdvancedSettings())} method={method} />

            <div className="section-rule measurement-rule"><span>MEDICIÓN</span></div>
            <label className="field-label" htmlFor="gsd">GSD · metros por píxel <span className="optional">opcional</span></label>
            <input className="field-control" id="gsd" type="number" min="0.000001" step="any" inputMode="decimal" placeholder="Sin escala: medidas en píxeles" value={gsd} onChange={(event) => setGsd(event.target.value)} />

            <button className="run-button" id="run-analysis" type="submit" disabled={!canRun}>
              <span className="run-icon" aria-hidden="true">▶</span><span>{running ? "Analizando…" : "Iniciar segmentación"}</span>
            </button>
            {error && <p className="form-error" role="alert">{error}</p>}
          </form>
        </aside>

        <section className="analysis-column" aria-label="Plano y progreso">
          <div className="analysis-heading">
            <div className="analysis-title"><p className="eyebrow">PLANO DE ANÁLISIS</p><h2>{jobId || running ? jobLabel : activeLabel}</h2></div>
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
              tool={tool}
              setTool={setTool}
              marks={marks}
              setMarks={setMarks}
              inspectedPixel={inspectedPixel}
              setInspectedPixel={setInspectedPixel}
              polygonClosed={polygonClosed}
              setPolygonClosed={setPolygonClosed}
              errorMessage={running ? "La vista aparecerá al terminar la segmentación." : ""}
              onError={setError}
            />
          </div>
        </section>

        <aside className="results-column" aria-label="Resultado de la segmentación">
          <div className="results-heading"><div><p className="eyebrow">SALIDA</p><h2>Resultado</h2></div><span className="step-badge">02</span></div>
          <div className={`result-state${result?.state === "error" ? " is-error" : ""}`}>
            {running ? "Análisis en curso…" : metrics ? `Detector: ${metrics.detector}. Revisa la hipótesis antes de usarla.` : result?.error || "Aún no hay un análisis."}
          </div>
          {metrics && <>
            <div className="metrics-grid">
              <article className="metric-card metric-primary"><span>Superficie candidata</span><strong>{formatNumber(metrics.coverage_pct, 1)} %</strong></article>
              <article className="metric-card"><span>Área</span><strong>{formatArea(metrics.area, metrics.area_unit)}</strong></article>
              <article className="metric-card"><span>Perímetro</span><strong>{formatLength(metrics.perimeter, metrics.perimeter_unit)}</strong></article>
              <article className="metric-card"><span>Humo probable</span><strong>{formatNumber(metrics.smoke_pct, 1)} %</strong></article>
            </div>
            <p className="result-caveat">Hipótesis automática; requiere revisión humana. Humo y cubiertas oscuras pueden causar zonas indeterminadas o falsos positivos.</p>
          </>}

          <div className="section-rule result-rule"><span>EXPORTAR</span></div>
          <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("overlay-true-color", "pyroscope_mapa_segmentado.png")}><span>Mapa con contorno</span><span>PNG ↓</span></button>
          <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("mask", "pyroscope_mascara_candidata.png")}><span>Máscara segmentada</span><span>PNG ↓</span></button>
          <button className="export-button" type="button" disabled={!hasResult} onClick={downloadMeasurements}><span>Puntos y medidas</span><span>JSON ↓</span></button>

          <details className="details-panel">
            <summary>Detalles del análisis</summary>
            <div className="details-content">{summary}</div>
          </details>

          <details className="details-panel" open>
            <summary>Notas de campo</summary>
            <form className="note-form" onSubmit={addNote}>
              <label className="sr-only" htmlFor="note-text">Añadir una nota</label>
              <input className="field-control" id="note-text" type="text" maxLength="240" placeholder="Añadir una nota…" value={noteText} onChange={(event) => setNoteText(event.target.value)} />
              <button className="icon-button" type="submit" aria-label="Guardar nota">+</button>
            </form>
            <ul className="notes-list">{notesAsText.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul>
          </details>
        </aside>
      </main>
    </>
  );
}

export default App;
