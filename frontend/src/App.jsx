import { useCallback, useEffect, useState } from "react";
import AdvancedSettings from "./components/AdvancedSettings.jsx";
import ImageViewer from "./components/ImageViewer.jsx";
import { api, fileToBase64 } from "./services/api.js";
import { Button, Card } from "@radix-ui/themes";
import { Activity, Crosshair, MousePointer2, Play, Ruler, ScanLine, SlidersHorizontal } from "lucide-react";
import { distanceBetween, formatArea, formatLength, formatNumber } from "./domain/measurements.js";

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
  { id: "area", label: "Área", Icon: Crosshair },
  { id: "pixel", label: "Píxel", Icon: ScanLine },
];

const OCCLUSION_LAYERS = {
  "visible-surface": "Superficie observable",
  smoke: "Humo probable",
  "smoke-candidates": "Hipótesis bajo humo",
  "smoke-unknown": "Terreno indeterminado",
  "smoke-spectral": "Bajo humo: evidencia SWIR",
  "smoke-continuity": "Bajo humo: continuidad espacial",
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
  const [tool, setTool] = useState("view");
  const [marks, setMarks] = useState([]);
  const [distancePreview, setDistancePreview] = useState(null);
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [regionCount, setRegionCount] = useState(0);
  const [inspectedPixel, setInspectedPixel] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.all([api.scenes(), api.detectors()])
      .then(([sceneResponse, detectorResponse]) => {
        if (!active) return;
        const availableScenes = sceneResponse.scenes || [];
        const availableDetectors = detectorResponse.detectors || [];
        setScenes(availableScenes);
        setDetectors(availableDetectors);
        if (availableScenes.length) {
          setSceneId(availableScenes[0].id);
        } else {
          // Sin muestras locales, abre directamente el flujo de carga para no
          // dejar deshabilitado el botón de segmentación en "Escenas".
          setSource("upload");
        }
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
  const diagnosticLayers = (metrics?.available_layers || []).filter((name) => name.startsWith("diagnostic-"));
  const handleRegionsReady = useCallback((regions) => setRegionCount(regions.length), []);
  const hasMetricScale = Number.isFinite(grid?.gsd_x_m) && grid.gsd_x_m > 0
    && Number.isFinite(grid?.gsd_y_m) && grid.gsd_y_m > 0;
  const marksUnit = hasMetricScale ? "m" : "px";
  const currentDistance = grid && (distancePreview
    ? distanceBetween(distancePreview.start, distancePreview.end, grid)
    : tool === "distance" && marks.length >= 2
      ? distanceBetween(marks[marks.length - 2], marks[marks.length - 1], grid)
      : null);
  const selectTool = (nextTool) => {
    if (nextTool === tool) return;
    setTool(nextTool);
    setMarks([]);
    setDistancePreview(null);
    setSelectedRegion(null);
    setInspectedPixel(null);
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
      setSelectedRegion(null);
      setRegionCount(0);
      setInspectedPixel(null);
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
    if (selectedRegion) {
      elements.push({
        id: `region-segmentada-${selectedRegion.id}`,
        tipo: "region_segmentada",
        region_id: selectedRegion.id,
        pixel_count: selectedRegion.pixel_count,
        area: { valor: selectedRegion.area, unidad: selectedRegion.area_unit },
        perimetro: { valor: selectedRegion.perimeter, unidad: selectedRegion.perimeter_unit },
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
    <div className="mission-shell">
      <header className="mission-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">L</span>
          <div className="brand-copy"><strong>LUMBRE</strong><span>CARTOGRAFÍA DE CAMPO</span></div>
        </div>
        <div className="mission-context">
          <span className="header-overline">PLANIFICACIÓN DE RUTA / ANÁLISIS</span>
          <strong>{activeLabel}</strong>
        </div>
        <div className="header-status">
          <span className={`connection-pill${connection.ready ? " is-ready" : error ? " is-error" : ""}`}>
            <span className="status-dot" />{connection.label}
          </span>
          <span className="header-capability">IMAGEN · TERRENO · SEGMENTACIÓN</span>
        </div>
      </header>
      <main className="workspace">
        <aside className="control-panel" aria-label="Configuración del análisis">
          <div className="panel-heading">
            <span className="panel-index">01</span>
            <div className="panel-heading-copy">
              <h1><SlidersHorizontal size={15} aria-hidden="true" />Preparar carga</h1>
              <span>FUENTE / MÉTODO / DETECCIÓN</span>
            </div>
          </div>

          <section className="sidebar-progress" aria-label="Progreso del análisis">
            <div className="progress-summary" aria-live="polite"><span>{progress.label}</span><strong>{progress.value}%</strong></div>
            <div className="progress-track" role="progressbar" aria-label="Progreso del análisis" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress.value}>
              <span style={{ width: `${progress.value}%` }} />
            </div>
          </section>

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
                  {scenes.length ? scenes.map((scene) => <option value={scene.id} key={scene.id}>{scene.label}</option>) : <option value="">{connection.ready ? "No hay escenas precargadas" : "Buscando imágenes…"}</option>}
                </select>
              </section>
            ) : (
              <section className="source-content">
                <label className="field-label" htmlFor="true-color-file">Imagen True Color</label>
                <input className="file-control" name="true-color-file" id="true-color-file" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
                <label className="field-label second-file-label" htmlFor="swir-file">Imagen SWIR</label>
                <input className="file-control" name="swir-file" id="swir-file" type="file" accept=".jpg,.jpeg,.png,.tif,.tiff,image/*" />
                <p className="field-help">{scenes.length === 0
                  ? "No hay escenas precargadas en esta copia. Carga dos imágenes alineadas de la misma escena y fecha para poder segmentar."
                  : "True Color y SWIR de la misma fecha."}</p>
              </section>
            )}

            <div className="section-rule"><span>DETECTOR</span></div>
            <label className="field-label" htmlFor="detector-select">Método</label>
            <select className="field-control" id="detector-select" value={method} onChange={(event) => setMethod(event.target.value)}>
              {detectors.map((detector) => <option value={detector.id} key={detector.id}>{detector.name}</option>)}
            </select>

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

        <section className="analysis-column" aria-label="Visor del análisis">
          <div className="viewer-card">
            <div className="viewer-ident">
              <div><span className="viewer-overline">ÁREA DE OPERACIONES</span><strong>{activeLabel}</strong></div>
              <div className="viewer-mode"><span className="signal-mark" />{hasResult ? (showSegmentation ? "LECTURA SEGMENTADA" : "CAPA ORIGINAL") : "ESPERANDO IMAGEN"}</div>
            </div>
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
              distancePreview={distancePreview}
              setDistancePreview={setDistancePreview}
              inspectedPixel={inspectedPixel}
              setInspectedPixel={setInspectedPixel}
              selectedRegion={selectedRegion}
              onRegionSelect={setSelectedRegion}
              onRegionsReady={handleRegionsReady}
              errorMessage={running ? "La vista aparecerá al terminar la segmentación." : ""}
              onError={setError}
            />
          </div>
        </section>

        <aside className="results-column interaction-panel" aria-label="Herramientas y resultados">
          <div className="panel-heading results-title">
            <span className="panel-index">02</span>
            <div className="panel-heading-copy"><h1>Lectura de campo</h1><span>MEDICIÓN / INFORME</span></div>
          </div>
          <section className="measurement-panel" aria-label="Herramientas de medición">
            <p className="panel-kicker">HERRAMIENTAS</p>
            <div className="tool-grid" role="group" aria-label="Seleccionar herramienta">
              {TOOL_OPTIONS.map(({ id, label, Icon }) => (
                <Button key={id} className={`tool-button${tool === id ? " is-active" : ""}`} variant={tool === id ? "soft" : "ghost"} size="1" type="button" disabled={!hasResult || (id === "distance" && !hasMetricScale) || (id === "area" && !regionCount)} title={id === "distance" && hasResult && !hasMetricScale ? "Introduce un GSD y vuelve a analizar para medir en metros." : undefined} aria-pressed={tool === id} onClick={() => selectTool(id)}>
                  <Icon size={14} aria-hidden="true" /><span>{label}</span>
                </Button>
              ))}
            </div>
            <p className="measurement-hint" aria-live="polite">
              {tool === "distance" && hasResult && !hasMetricScale ? "Introduce el GSD y vuelve a analizar para habilitar la regla en metros." : tool === "distance" ? "Arrastra sobre la imagen para medir una distancia en metros." : tool === "area" && hasResult && !regionCount ? "La máscara no contiene regiones segmentadas para medir." : tool === "area" ? "Haz clic dentro del contorno segmentado para medir esa región." : tool === "pixel" ? "Selecciona un píxel para ver su coordenada." : "Elige una herramienta o compara las capas en el visor."}
            </p>
            {(currentDistance !== null || selectedRegion || (tool === "pixel" && inspectedPixel)) && <div className="measurement-readout" aria-live="polite">
              {currentDistance !== null && <div><span>{distancePreview ? "Midiendo" : "Distancia"}</span><strong>{formatLength(currentDistance, marksUnit)}</strong></div>}
              {selectedRegion && <>
                <div><span>Región seleccionada</span><strong>#{selectedRegion.id}</strong></div>
                <div><span>Área de la región</span><strong>{formatArea(selectedRegion.area, selectedRegion.area_unit)}</strong></div>
                <div><span>Perímetro</span><strong>{formatLength(selectedRegion.perimeter, selectedRegion.perimeter_unit)}</strong></div>
              </>}
              {tool === "pixel" && inspectedPixel && <div><span>Coordenada</span><strong>({formatNumber(inspectedPixel.x)}, {formatNumber(inspectedPixel.y)}) px</strong></div>}
            </div>}
            <div className="measurement-actions">
              <button className="text-button" type="button" disabled={!hasResult || (!marks.length && !inspectedPixel && !selectedRegion)} onClick={() => {
                if (tool === "pixel") setInspectedPixel(null);
                else if (tool === "area") setSelectedRegion(null);
                else setMarks((current) => current.slice(0, tool === "distance" ? -2 : -1));
                setDistancePreview(null);
              }}>Deshacer</button>
              <button className="text-button" type="button" disabled={!hasResult || (!marks.length && !inspectedPixel && !selectedRegion)} onClick={() => {
                setMarks([]); setInspectedPixel(null); setDistancePreview(null); setSelectedRegion(null);
              }}>Borrar marcas</button>
            </div>
            <hr className="measurement-separator" />
            <label className="scale-input" htmlFor="gsd"><span>GSD <small>metros por píxel</small></span>
              <input className="field-control" id="gsd" type="number" min="0.000001" step="any" inputMode="decimal" placeholder="Opcional" value={gsd} onChange={(event) => setGsd(event.target.value)} disabled={running} />
            </label>
            <p className="field-help">Se aplica en el siguiente análisis. La regla solo se habilita si el análisis incluye GSD y mide en metros.</p>
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
              <Card className="metric-card" size="1"><span>Área total segmentada</span><strong>{formatArea(metrics.area, metrics.area_unit)}</strong></Card>
              <Card className="metric-card" size="1"><span>Perímetro</span><strong>{formatLength(metrics.perimeter, metrics.perimeter_unit)}</strong></Card>
              <Card className="metric-card" size="1"><span>Humo probable</span><strong>{formatNumber(metrics.smoke_pct, 1)} %</strong></Card>
            </div>
            <p className="result-caveat">Rojo y borde amarillo: zona afectada candidata, incluida la hipótesis bajo humo. Azul transparente encima: humo probable. De la zona roja, {formatNumber(metrics.smoke_covered_candidates_px)} px son inferidos bajo humo y no se suman al área observada. Terreno desconocido bajo humo{metrics.smoke_unknown_px != null ? `: ${formatNumber(metrics.smoke_unknown_px)} px` : ""}; consulta las capas independientes. No detecta fuego activo.</p>
          </>}

          <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("overlay-true-color", "lumbre_mapa_segmentado.png")}><span>Mapa con contorno</span><span>PNG ↓</span></button>
          <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("mask", "lumbre_mascara_candidata.png")}><span>Máscara segmentada</span><span>PNG ↓</span></button>
          <button className="export-button" type="button" disabled={!hasResult} onClick={downloadMeasurements}><span>Puntos y medidas</span><span>JSON ↓</span></button>

          {hasResult && <details className="details-panel">
            <summary>Capas de humo y diagnóstico</summary>
            <div className="details-content">
              <p>Máscaras PNG independientes. La hipótesis y el humo pueden coincidir; negro significa ausencia en esa capa.</p>
              {(metrics?.available_layers || []).filter((name) => OCCLUSION_LAYERS[name]).map((name) => (
                <button key={name} className="export-button" type="button" onClick={() => downloadLayer(name, `lumbre_${name}.png`)}><span>{OCCLUSION_LAYERS[name]}</span><span>PNG ↓</span></button>
              ))}
              {diagnosticLayers.map((name) => (
                <details key={name}>
                  <summary>{name.replace("diagnostic-", "").replaceAll("-", " ")}</summary>
                  <img loading="lazy" src={api.layerUrl(jobId, name)} alt={`Diagnóstico ${name}`} style={{ width: "100%", height: "auto" }} />
                  <button className="text-button" type="button" onClick={() => downloadLayer(name, `lumbre_${name}.png`)}>Descargar PNG</button>
                </details>
              ))}
            </div>
          </details>}

          {metrics && <details className="details-panel">
            <summary>Detalles</summary>
            <div className="details-content">{summary}</div>
          </details>}
        </aside>
      </main>
    </div>
  );
}

export default App;
