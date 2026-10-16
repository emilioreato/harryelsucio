import { useCallback, useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import AdvancedSettings from "./components/AdvancedSettings.jsx";
import ImageViewer from "./components/ImageViewer.jsx";
import PipelineTimeline from "./components/PipelineTimeline.jsx";
import CheckpointViewer from "./components/CheckpointViewer.jsx";
import AdvancedWorkspace from "./components/AdvancedWorkspace.jsx";
import VersionSwitcher from "./components/VersionSwitcher.jsx";
import { api, fileToBase64 } from "./services/api.js";
import { Button } from "@radix-ui/themes";
import { Activity, ArrowUpRight, Circle, Copy, Crosshair, Eraser, LoaderCircle, Minus, MousePointer2, Package, Pencil, Play, Ruler, ScanLine, SlidersHorizontal, Square, Type } from "lucide-react";
import { distanceBetween, formatArea, formatAreaKm2, formatLength, formatLengthKm } from "./domain/measurements.js";

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
  swir_red_green_max: 0.85,
};

// Perfil de arranque intencional: los controles de esta sesión no se guardan
// en localStorage y la página vuelve a estos valores al recargar la aplicación.
const DEFAULT_SEGMENTATION_PROFILE = Object.freeze({
  method: "contextual_hibrida",
  sensitivity: 6,
  numClasses: 7,
  minimumArea: "0.15",
  maxDistance: "10",
  keepSeparate: false,
});

const TOOL_OPTIONS = [
  { id: "view", label: "Ver", Icon: MousePointer2 },
  { id: "distance", label: "Regla", Icon: Ruler },
  { id: "area", label: "Área", Icon: Crosshair },
  { id: "annotate", label: "Anotar", Icon: Pencil },
];

const ANNOTATION_TOOLS = [
  { id: "freehand", label: "Dibujo libre", Icon: Pencil },
  { id: "line", label: "Línea", Icon: Minus },
  { id: "arrow", label: "Flecha", Icon: ArrowUpRight },
  { id: "rectangle", label: "Rectángulo", Icon: Square },
  { id: "ellipse", label: "Elipse", Icon: Circle },
  { id: "text", label: "Texto", Icon: Type },
  { id: "eraser", label: "Borrador", Icon: Eraser },
];

const ANNOTATION_COLORS = [
  { value: "#ff4fa3", label: "Rosa" },
  { value: "#ffdf45", label: "Amarillo" },
  { value: "#38d8ff", label: "Cian" },
  { value: "#ffffff", label: "Blanco" },
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
    use_random_forest: false,
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

function BasicWorkspace({ version, onVersionChange, isActive }) {
  const [scenes, setScenes] = useState([]);
  const [detectors, setDetectors] = useState([]);
  const [connection, setConnection] = useState({ ready: false, label: "Conectando…" });
  const [source, setSource] = useState("preloaded");
  const [sceneId, setSceneId] = useState("");
  const [method, setMethod] = useState(DEFAULT_SEGMENTATION_PROFILE.method);
  const [sensitivity, setSensitivity] = useState(DEFAULT_SEGMENTATION_PROFILE.sensitivity);
  const [numClasses, setNumClasses] = useState(DEFAULT_SEGMENTATION_PROFILE.numClasses);
  const [minimumArea, setMinimumArea] = useState(DEFAULT_SEGMENTATION_PROFILE.minimumArea);
  const [maxDistance, setMaxDistance] = useState(DEFAULT_SEGMENTATION_PROFILE.maxDistance);
  const [keepSeparate, setKeepSeparate] = useState(DEFAULT_SEGMENTATION_PROFILE.keepSeparate);
  const [advanced, setAdvanced] = useState(defaultAdvancedSettings);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [selectedCheckpointId, setSelectedCheckpointId] = useState(null);
  const [checkpointWarnings, setCheckpointWarnings] = useState([]);
  const followingLiveRef = useRef(true);
  const analysisRunRef = useRef(0);
  const [jobLabel, setJobLabel] = useState("Selecciona una escena");
  const [layer, setLayer] = useState("swir");
  const [showSegmentation, setShowSegmentation] = useState(true);
  const [showVisibleSurface, setShowVisibleSurface] = useState(true);
  const [showSmoke, setShowSmoke] = useState(true);
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [tool, setTool] = useState("view");
  const [annotationTool, setAnnotationTool] = useState("freehand");
  const [annotationColor, setAnnotationColor] = useState(ANNOTATION_COLORS[0].value);
  const [annotationWidth, setAnnotationWidth] = useState(4);
  const [annotationText, setAnnotationText] = useState("");
  const [annotations, setAnnotations] = useState([]);
  const annotationsRef = useRef([]);
  const annotationUndoHistory = useRef([]);
  const [canUndoAnnotations, setCanUndoAnnotations] = useState(false);
  const [exportingPackage, setExportingPackage] = useState(false);
  const [marks, setMarks] = useState([]);
  const [distancePreview, setDistancePreview] = useState(null);
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [regionCount, setRegionCount] = useState(0);
  const [installPrompt, setInstallPrompt] = useState(null);
  const [showInstallHelp, setShowInstallHelp] = useState(false);
  const [mobileAccess, setMobileAccess] = useState(null);
  const [mobileQr, setMobileQr] = useState("");
  const [mobileLinkCopied, setMobileLinkCopied] = useState(false);

  const desktopMobileSetup = Boolean(
    mobileAccess?.enabled && ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname),
  );

  const updateAnnotations = useCallback((next) => {
    const current = annotationsRef.current;
    const updated = typeof next === "function" ? next(current) : next;
    if (updated === current) return;

    annotationUndoHistory.current.push(current);
    if (annotationUndoHistory.current.length > 100) annotationUndoHistory.current.shift();
    annotationsRef.current = updated;
    setAnnotations(updated);
    setCanUndoAnnotations(true);
  }, []);

  const undoAnnotation = useCallback(() => {
    const previous = annotationUndoHistory.current.pop();
    if (!previous) return false;

    annotationsRef.current = previous;
    setAnnotations(previous);
    setCanUndoAnnotations(annotationUndoHistory.current.length > 0);
    return true;
  }, []);

  const resetAnnotations = useCallback(() => {
    annotationsRef.current = [];
    annotationUndoHistory.current = [];
    setAnnotations([]);
    setCanUndoAnnotations(false);
  }, []);

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
  const selectedCheckpoint = checkpoints.find((item) => item.id === selectedCheckpointId) || null;
  const showingHistory = Boolean(selectedCheckpoint && !selectedCheckpoint.final);
  const showFinalViewer = hasResult && !showingHistory;
  const canMeasure = hasResult && !showingHistory;
  const grid = result?.grid || null;
  const metrics = result?.metrics || null;
  const handleRegionsReady = useCallback((regions) => setRegionCount(regions.length), []);
  const hasMetricScale = Number.isFinite(grid?.gsd_x_m) && grid.gsd_x_m > 0
    && Number.isFinite(grid?.gsd_y_m) && grid.gsd_y_m > 0;
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
  };

  const selectCheckpoint = useCallback((checkpointId) => {
    followingLiveRef.current = checkpoints.at(-1)?.id === checkpointId;
    setSelectedCheckpointId(checkpointId);
    setMarks([]);
    setDistancePreview(null);
    setSelectedRegion(null);
  }, [checkpoints]);

  useEffect(() => {
    const handleHistoryKeys = (event) => {
      if (!checkpoints.length || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable='true']")) return;
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;

      const currentIndex = checkpoints.findIndex((item) => item.id === selectedCheckpointId);
      const startIndex = currentIndex < 0 ? checkpoints.length - 1 : currentIndex;
      const nextIndex = event.key === "Home"
        ? 0
        : event.key === "End"
          ? checkpoints.length - 1
          : Math.max(0, Math.min(checkpoints.length - 1, startIndex + (event.key === "ArrowRight" ? 1 : -1)));
      if (nextIndex === currentIndex) return;
      event.preventDefault();
      selectCheckpoint(checkpoints[nextIndex].id);
    };

    window.addEventListener("keydown", handleHistoryKeys);
    return () => window.removeEventListener("keydown", handleHistoryKeys);
  }, [checkpoints, selectedCheckpointId, selectCheckpoint]);

  useEffect(() => {
    if (tool !== "annotate" || !canMeasure || !canUndoAnnotations) return undefined;

    const handleUndoAnnotation = (event) => {
      if ((!event.ctrlKey && !event.metaKey) || event.altKey || event.shiftKey || event.key.toLowerCase() !== "z") return;
      if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable='true']")) return;
      event.preventDefault();
      undoAnnotation();
    };

    window.addEventListener("keydown", handleUndoAnnotation);
    return () => window.removeEventListener("keydown", handleUndoAnnotation);
  }, [canMeasure, canUndoAnnotations, tool, undoAnnotation]);

  const collectSettings = () => {
    const minimum = numberFromInput(minimumArea, "El área mínima");
    if (minimum < 0.01 || minimum > 1) throw new Error("El área mínima debe estar entre 0,01 y 1 %.");
    const distance = numberFromInput(maxDistance, "El radio máximo");
    if (!keepSeparate && (!Number.isInteger(distance) || distance < 3 || distance > 20)) {
      throw new Error("El radio máximo debe ser un entero entre 3 y 20 %.");
    }
    for (const [name, value] of Object.entries(advanced.kmeans_weights)) {
      if (!Number.isFinite(value) || value < -3 || value > 3) throw new Error(`El peso K-Means ${name} debe estar entre -3 y 3.`);
    }
    const sensitivityNumber = Number(sensitivity);
    const seedRed = advanced.swir_thresholds.seed_red ?? (0.958 - (sensitivityNumber - 1) * 0.009);
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
      gsd_m_per_px: null,
      advanced,
    };
  };

  const runAnalysis = async (event) => {
    const runToken = ++analysisRunRef.current;
    event.preventDefault();
    setError("");
    let request;
    try {
      const settings = collectSettings();
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
          true_color_filename: trueFile.name,
          swir_filename: swirFile.name,
          settings,
        };
      }

      setJobLabel(activeLabel);
      setJobId(null);
      setCheckpoints([]);
      setSelectedCheckpointId(null);
      followingLiveRef.current = true;
      setCheckpointWarnings([]);
      setResult(null);
      setMarks([]);
      setDistancePreview(null);
      setSelectedRegion(null);
      resetAnnotations();
      setAnnotationText("");
      setRegionCount(0);
      setRunning(true);
      setConnection({ ready: true, label: "Analizando…" });

      const started = await api.analyze(request);
      if (runToken !== analysisRunRef.current) return;
      const nextJobId = started.job_id;
      setJobId(nextJobId);
      while (true) {
        const job = await api.job(nextJobId);
        if (runToken !== analysisRunRef.current) return;
        const availableCheckpoints = Array.isArray(job.checkpoints) ? job.checkpoints : [];
        setCheckpoints(availableCheckpoints);
        setCheckpointWarnings(Array.isArray(job.checkpoint_warnings) ? job.checkpoint_warnings : []);
        if (availableCheckpoints.length > 0) {
          setSelectedCheckpointId((current) => {
            if (followingLiveRef.current) return availableCheckpoints.at(-1).id;
            return availableCheckpoints.some((item) => item.id === current)
              ? current
              : availableCheckpoints[0].id;
          });
        }
        if (job.state === "complete") {
          if (followingLiveRef.current && availableCheckpoints.length) {
            setSelectedCheckpointId(availableCheckpoints.at(-1).id);
          }
          setResult(job);
          setRunning(false);
          setConnection({ ready: true, label: "Conectado" });
          return;
        }
        if (job.state === "error") {
          const message = job.error || "El análisis quedó incompleto.";
          setResult({ state: "error", error: message });
          setError(message);
          setRunning(false);
          setConnection({ ready: true, label: "Conectado" });
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 650));
      }
    } catch (cause) {
      if (runToken !== analysisRunRef.current) return;
      const message = cause?.message || "No se pudo iniciar el análisis.";
      setError(message);
      setResult({ state: "error", error: message });
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

  const downloadPackage = async () => {
    if (!jobId || !hasResult || exportingPackage) return;
    setExportingPackage(true);
    try {
      const paquete = await api.downloadPackage(jobId, {
        annotations,
        view: {
          layer,
          show_segmentation: showSegmentation,
          show_smoke: showSmoke,
          show_visible_surface: showVisibleSurface,
          show_under_smoke: showVisibleSurface,
        },
      });
      saveBlob(paquete, `lumbre_paquete_ia_${jobId.slice(0, 8)}.zip`);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setExportingPackage(false);
    }
  };

  return (
    <>
      <header className={`mobile-appbar${isActive ? "" : " mode-panel-hidden"}`}>
        <a className="mobile-brand" href="#mobile-setup" aria-label="Lumbre, ir al análisis">
          <span className="brand-pixel-flame" aria-hidden="true" />
          <span><strong>LUMBRE</strong><small>FIELD ANALYSIS</small></span>
        </a>
        <button className="install-button" type="button" onClick={installMobileApp}>Instalar app</button>
      </header>
      {showInstallHelp && <div className={`install-help${isActive ? "" : " mode-panel-hidden"}`} role="status">
        <span>iPhone/iPad: Compartir → Añadir a pantalla de inicio. Android: menú del navegador → Instalar aplicación o Añadir a pantalla de inicio.</span>
        <button type="button" aria-label="Cerrar ayuda" onClick={() => setShowInstallHelp(false)}>×</button>
      </div>}
      <main className={`workspace${isActive ? "" : " mode-panel-hidden"}`}>
        <aside className="control-panel" id="mobile-setup" aria-label="Configuración del análisis">
          <div className="sidebar-fixed">
            <div className="panel-heading">
              <h1 className="panel-brand-heading">
                <span className="brand-mark-wrap" aria-hidden="true"><span className="brand-pixel-flame" /></span>
                <span className="brand-heading-copy"><strong>LUMBRE</strong><small><SlidersHorizontal size={10} aria-hidden="true" />Análisis</small></span>
              </h1>
              <VersionSwitcher version={version} onChange={onVersionChange} />
              <span className="sr-only" role="status">{connection.label}</span>
            </div>
            <div className="sidebar-heading-divider" aria-hidden="true" />

            <section className="sidebar-timeline" aria-label="Etapas de la segmentación">
              <PipelineTimeline
                checkpoints={checkpoints}
                jobId={jobId}
                selectedCheckpointId={selectedCheckpointId}
                checkpointWarnings={checkpointWarnings}
                onSelectCheckpoint={selectCheckpoint}
              />
            </section>

            <Button className="run-button" id="run-analysis" type="submit" form="basic-analysis-form" disabled={!canRun} size="3">
              {running ? <Activity size={16} aria-hidden="true" /> : <Play size={15} aria-hidden="true" fill="currentColor" />}
              <span>{running ? "Analizando…" : "Iniciar segmentación"}</span>
            </Button>
            {error && <p className="form-error" role="alert">{error}</p>}
          </div>

          <div className="sidebar-scroll">
          <form id="basic-analysis-form" onSubmit={runAnalysis}>
            <div className="source-switch" role="tablist" aria-label="Origen de las imágenes">
              {[ ["preloaded", "Escenas"], ["upload", "Subir imágenes"] ].map(([id, label]) => (
                <button key={id} className={`source-tab${source === id ? " is-active" : ""}`} type="button" role="tab" aria-selected={source === id} onClick={() => setSource(id)}>{label}</button>
              ))}
            </div>

            {source === "preloaded" ? (
              <section className="source-content">
                <span className="field-label">Escena</span>
                {scenes.length ? <div className="scene-gallery" role="group" aria-label="Elegir escena">
                  {scenes.map((scene) => (
                    <button
                      key={scene.id}
                      className={`scene-card${scene.id === sceneId ? " is-selected" : ""}`}
                      type="button"
                      aria-pressed={scene.id === sceneId}
                      aria-label={`Elegir ${scene.label}, True Color y SWIR`}
                      onClick={() => setSceneId(scene.id)}
                    >
                      <span className="scene-card-previews">
                        <span className="scene-preview">
                          <img src={api.scenePreviewUrl(scene.id, "true-color")} alt="" loading="lazy" />
                          <span>True Color</span>
                        </span>
                        <span className="scene-preview">
                          <img src={api.scenePreviewUrl(scene.id, "swir")} alt="" loading="lazy" />
                          <span>SWIR</span>
                        </span>
                      </span>
                      <span className="scene-card-label">
                        <strong>{scene.label}</strong>
                      </span>
                    </button>
                  ))}
                </div> : <p className="field-help">{connection.ready ? "No hay escenas precargadas." : "Cargando escenas…"}</p>}
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

            {desktopMobileSetup && <details className="phone-access">
              <summary>Abrir Lumbre en el móvil</summary>
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
            </details>}

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

            <details className="details-panel parameter-settings" open>
              <summary>Parámetros</summary>
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

            <AdvancedSettings
              value={advanced}
              onChange={setAdvanced}
              onReset={() => setAdvanced(defaultAdvancedSettings())}
              method={method}
              randomForestAvailable={detectors.some((item) => item.id === "random_forest")}
            />

          </form>
          </div>
        </aside>

        <section className="analysis-column" id="mobile-map" aria-label="Visor del análisis">
          <div className="viewer-card">
            {showFinalViewer ? (
              <ImageViewer
                jobId={jobId}
                grid={grid}
                layer={layer}
                setLayer={setLayer}
                showSegmentation={showSegmentation}
                setShowSegmentation={setShowSegmentation}
                showVisibleSurface={showVisibleSurface}
                setShowVisibleSurface={setShowVisibleSurface}
                showSmoke={showSmoke}
                setShowSmoke={setShowSmoke}
                showAnnotations={showAnnotations}
                setShowAnnotations={setShowAnnotations}
                tool={tool}
                annotationTool={annotationTool}
                annotationColor={annotationColor}
                annotationWidth={annotationWidth}
                annotationText={annotationText}
                setAnnotationText={setAnnotationText}
                annotations={annotations}
                setAnnotations={updateAnnotations}
                marks={marks}
                setMarks={setMarks}
                distancePreview={distancePreview}
                setDistancePreview={setDistancePreview}
                selectedRegion={selectedRegion}
                onRegionSelect={setSelectedRegion}
                onRegionsReady={handleRegionsReady}
                hasWildfiresReference={metrics?.available_layers?.includes("reference-wildfires") || false}
                onError={setError}
              />
            ) : (
              <CheckpointViewer
                checkpoint={selectedCheckpoint}
                jobId={jobId}
                running={running}
                incomplete={result?.state === "error"}
              />
            )}
          </div>
        </section>

        <aside className="results-column interaction-panel" id="mobile-results" aria-label="Herramientas y resultados">
          <div className="results-heading"><h2>Análisis</h2></div>
          <section className="measurement-panel" aria-label="Herramientas de medición y anotación">
            <p className="panel-kicker">HERRAMIENTAS</p>
            <div className="tool-grid" role="group" aria-label="Seleccionar herramienta">
              {TOOL_OPTIONS.map(({ id, label, Icon }) => (
                <Button key={id} className={`tool-button${tool === id ? " is-active" : ""}`} variant="ghost" size="1" type="button" disabled={!canMeasure || (id === "area" && !regionCount)} aria-pressed={tool === id} onClick={() => selectTool(id)}>
                  <Icon size={14} aria-hidden="true" /><span>{label}</span>
                </Button>
              ))}
            </div>
            {tool === "annotate" && <div className="annotation-controls" role="toolbar" aria-label="Controles de anotación">
              <div className="annotation-tool-grid" role="group" aria-label="Tipo de anotación">
                {ANNOTATION_TOOLS.map(({ id, label, Icon }) => (
                  <button
                    key={id}
                    className={`annotation-tool-button${annotationTool === id ? " is-active" : ""}`}
                    type="button"
                    title={id === "eraser" ? "Clic para borrar una anotación completa" : label}
                    aria-label={id === "eraser" ? "Borrador: clic para borrar una anotación completa" : label}
                    aria-pressed={annotationTool === id}
                    onClick={() => setAnnotationTool(id)}
                  ><Icon size={14} aria-hidden="true" /></button>
                ))}
              </div>
              {annotationTool !== "eraser" && <label className="annotation-width-control">
                <span><span>Grosor</span><output>{annotationWidth} px</output></span>
                <input
                  type="range"
                  min="1"
                  max="20"
                  step="1"
                  value={annotationWidth}
                  aria-label="Grosor de la anotación en píxeles de imagen"
                  onChange={(event) => setAnnotationWidth(Number(event.target.value))}
                />
              </label>}
              {annotationTool !== "eraser" && <div className="annotation-color-row" role="group" aria-label="Color de anotación">
                {ANNOTATION_COLORS.map(({ value, label }) => (
                  <button
                    key={value}
                    className={`annotation-color${annotationColor === value ? " is-active" : ""}`}
                    type="button"
                    title={label}
                    aria-label={`Color ${label}`}
                    aria-pressed={annotationColor === value}
                    onClick={() => setAnnotationColor(value)}
                  ><span style={{ backgroundColor: value }} /></button>
                ))}
              </div>}
              {annotationTool === "text" && <input
                className="annotation-text-input"
                type="text"
                maxLength={500}
                placeholder="Escribe una nota…"
                aria-label="Texto de la anotación"
                value={annotationText}
                onChange={(event) => setAnnotationText(event.target.value)}
              />}
              {annotationTool === "eraser" && <p className="annotation-help">Selecciona el borrador y haz clic en el trazo o elemento que quieras quitar; cada clic borra solo ese elemento.</p>}
            </div>}
            {(currentDistance !== null || selectedRegion) && <div className="measurement-readout" aria-live="polite">
              {currentDistance !== null && <div><span>{distancePreview ? "Midiendo" : "Distancia"}</span><strong>{hasMetricScale ? formatLengthKm(currentDistance) : formatLength(currentDistance, "px")}</strong></div>}
              {selectedRegion && <>
                <div><span>Zona quemada estimada</span><strong>#{selectedRegion.id}</strong></div>
                <div><span>Área de la región</span><strong>{selectedRegion.area_unit === "m²" ? formatAreaKm2(selectedRegion.area, selectedRegion.area_unit) : formatArea(selectedRegion.area, selectedRegion.area_unit)}</strong></div>
                <div><span>Perímetro</span><strong>{selectedRegion.perimeter_unit === "m" ? formatLengthKm(selectedRegion.perimeter) : formatLength(selectedRegion.perimeter, selectedRegion.perimeter_unit)}</strong></div>
              </>}
            </div>}
            <div className="measurement-actions">
              <button className="text-button" type="button" title={tool === "annotate" ? "Deshacer última anotación (Ctrl+Z)" : undefined} aria-keyshortcuts={tool === "annotate" ? "Control+Z Meta+Z" : undefined} disabled={!canMeasure || (tool === "annotate" ? !canUndoAnnotations : (!marks.length && !selectedRegion))} onClick={() => {
                if (tool === "annotate") undoAnnotation();
                else if (tool === "area") setSelectedRegion(null);
                else setMarks((current) => current.slice(0, tool === "distance" ? -2 : -1));
                setDistancePreview(null);
              }}>Deshacer</button>
              {tool !== "annotate" && <button className="text-button" type="button" disabled={!canMeasure || (!marks.length && !selectedRegion)} onClick={() => {
                setMarks([]);
                setDistancePreview(null);
                setSelectedRegion(null);
              }}>Borrar marcas</button>}
            </div>
          </section>

          <div className="results-heading results-subheading package-export-heading">
            <h2>Guardar resultado</h2>
            <button
              className={`package-export-button${exportingPackage ? " is-loading" : ""}`}
              type="button"
              title={exportingPackage ? "Preparando paquete" : "Exportar paquete completo"}
              aria-label={exportingPackage ? "Preparando paquete" : "Exportar paquete completo"}
              disabled={!hasResult || exportingPackage}
              onClick={downloadPackage}
            >{exportingPackage ? <LoaderCircle size={15} aria-hidden="true" /> : <Package size={15} aria-hidden="true" />}</button>
          </div>
          <div className="export-actions">
            <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("overlay-true-color", "lumbre_mapa_segmentado.png")}><span>Mapa</span><span>PNG ↓</span></button>
            <button className="export-button" type="button" disabled={!hasResult} onClick={() => downloadLayer("estimated-surface", "lumbre_zona_quemada_estimada.png")}><span>Máscara</span><span>PNG ↓</span></button>
          </div>
        </aside>
      </main>
      <nav className={`mobile-dock${isActive ? "" : " mode-panel-hidden"}`} aria-label="Secciones">
        <a href="#mobile-setup"><SlidersHorizontal size={18} aria-hidden="true" /><span>Analizar</span></a>
        <a href="#mobile-map"><ScanLine size={18} aria-hidden="true" /><span>Mapa</span></a>
        <a href="#mobile-results"><Activity size={18} aria-hidden="true" /><span>Resultados</span></a>
      </nav>
    </>
  );
}

function App() {
  const [version, setVersion] = useState("basic");
  const [advancedVisited, setAdvancedVisited] = useState(false);
  const changeVersion = (nextVersion) => {
    if (nextVersion === "advanced") setAdvancedVisited(true);
    setVersion(nextVersion);
  };

  return (
    <>
      <BasicWorkspace
        version={version}
        onVersionChange={changeVersion}
        isActive={version === "basic"}
      />
      {advancedVisited && <AdvancedWorkspace
        version={version}
        onVersionChange={changeVersion}
        isActive={version === "advanced"}
      />}
    </>
  );
}

export default App;
