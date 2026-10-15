import { useEffect, useRef, useState } from "react";
import { api } from "../services/api.js";
import { formatArea, formatLength, distanceBetween, polygonArea } from "../domain/measurements.js";

const LAYERS = [
  ["true-color", "True Color"],
  ["swir", "SWIR"],
  ["candidates", "Clases + humo"],
];
const TOOLS = [
  ["view", "Vista"],
  ["distance", "Flechas"],
  ["polygon", "Polígono"],
];

function visibleLayer(layer, showSegmentation) {
  if (!showSegmentation) return layer === "swir" ? "swir" : "true-color";
  if (layer === "swir") return "overlay-swir";
  if (layer === "candidates") return "candidates";
  return "overlay-true-color";
}

function renderMeasurement(tool, marks, polygonClosed, grid) {
  if (!grid) return "";
  const unit = grid.gsd_x_m ? "m" : "px";
  if (tool === "distance") {
    const segments = [];
    for (let index = 0; index + 1 < marks.length; index += 2) {
      segments.push(`Flecha ${index / 2 + 1}: ${formatLength(distanceBetween(marks[index], marks[index + 1], grid), unit)}`);
    }
    if (marks.length % 2) segments.push("Añade otro punto para completar la flecha.");
    return segments.join(" · ");
  }
  if (tool === "polygon") {
    if (!polygonClosed || marks.length < 3) {
      return marks.length < 3 ? "Marca al menos tres vértices." : "Cierra el polígono para calcular área y perímetro.";
    }
    return `Área manual: ${formatArea(polygonArea(marks, grid), grid.gsd_x_m ? "m²" : "px²")}`;
  }
  return "";
}

export default function ImageViewer({
  jobId, grid, layer, setLayer, showSegmentation, setShowSegmentation, showMarks, setShowMarks,
  tool, setTool, marks, setMarks, polygonClosed, setPolygonClosed,
  loading, errorMessage, onError,
}) {
  const stageRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const [imageFailed, setImageFailed] = useState(false);
  const currentLayer = jobId ? visibleLayer(layer, showSegmentation) : null;
  const source = currentLayer && jobId ? `${api.layerUrl(jobId, currentLayer)}?v=${jobId}` : "";
  const hasResult = Boolean(jobId && grid);
  const marksForDraw = marks;

  useEffect(() => {
    setImageFailed(false);
  }, [source]);

  useEffect(() => {
    const image = imageRef.current;
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    if (!image || !canvas || !stage) return undefined;

    const draw = () => {
      if (!image.complete || !image.naturalWidth) return;
      const imageRect = image.getBoundingClientRect();
      const stageRect = stage.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.style.left = `${imageRect.left - stageRect.left}px`;
      canvas.style.top = `${imageRect.top - stageRect.top}px`;
      canvas.style.width = `${imageRect.width}px`;
      canvas.style.height = `${imageRect.height}px`;
      canvas.width = Math.max(1, Math.round(imageRect.width * ratio));
      canvas.height = Math.max(1, Math.round(imageRect.height * ratio));
      const context = canvas.getContext("2d");
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, imageRect.width, imageRect.height);
      if (!showMarks) return;
      const scaleX = imageRect.width / image.naturalWidth;
      const scaleY = imageRect.height / image.naturalHeight;
      context.strokeStyle = "#f0bd72";
      context.fillStyle = "#f0bd72";
      context.lineWidth = 2;
      context.lineCap = "round";
      context.lineJoin = "round";

      if (tool === "distance") {
        // Cada pareja de clics es una flecha independiente, no un trazo continuo.
        for (let index = 0; index + 1 < marksForDraw.length; index += 2) {
          const start = marksForDraw[index];
          const end = marksForDraw[index + 1];
          const x1 = start.x * scaleX;
          const y1 = start.y * scaleY;
          const x2 = end.x * scaleX;
          const y2 = end.y * scaleY;
          const angle = Math.atan2(y2 - y1, x2 - x1);
          const headLength = 14;
          context.beginPath();
          context.moveTo(x1, y1);
          context.lineTo(x2, y2);
          context.stroke();
          context.beginPath();
          context.moveTo(x2, y2);
          context.lineTo(x2 - headLength * Math.cos(angle - Math.PI / 7), y2 - headLength * Math.sin(angle - Math.PI / 7));
          context.lineTo(x2 - headLength * Math.cos(angle + Math.PI / 7), y2 - headLength * Math.sin(angle + Math.PI / 7));
          context.closePath();
          context.fill();
        }
      } else if (tool === "polygon" && marksForDraw.length > 1) {
        context.beginPath();
        marksForDraw.forEach((point, index) => {
          const x = point.x * scaleX;
          const y = point.y * scaleY;
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        if (polygonClosed && marksForDraw.length > 2) context.closePath();
        context.stroke();
      }
      marksForDraw.forEach((point, index) => {
        const x = point.x * scaleX;
        const y = point.y * scaleY;
        context.beginPath();
        context.arc(x, y, 5, 0, Math.PI * 2);
        context.fillStyle = "#d94a8b";
        context.fill();
        context.strokeStyle = "rgba(255,255,255,.95)";
        context.lineWidth = 1.5;
        context.stroke();
        context.fillStyle = "#fff";
        context.font = "600 10px ui-monospace, monospace";
        context.fillText(String(index + 1), x + 8, y - 8);
      });
    };

    draw();
    image.addEventListener("load", draw);
    window.addEventListener("resize", draw);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(draw);
    observer?.observe(stage);
    return () => {
      image.removeEventListener("load", draw);
      window.removeEventListener("resize", draw);
      observer?.disconnect();
    };
  }, [source, showMarks, marksForDraw, tool, polygonClosed, imageFailed]);

  const handleImageClick = (event) => {
    if (!hasResult || tool === "view" || !imageRef.current) return;
    const rect = imageRef.current.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return;
    const point = {
      x: Math.min(grid.ancho_px - 1, Math.max(0, (event.clientX - rect.left) * grid.ancho_px / rect.width)),
      y: Math.min(grid.alto_px - 1, Math.max(0, (event.clientY - rect.top) * grid.alto_px / rect.height)),
    };
    setMarks((current) => [...current, point]);
    setPolygonClosed(false);
  };

  const undo = () => {
    setMarks((current) => current.slice(0, -1));
    setPolygonClosed(false);
  };
  const clear = () => {
    setMarks([]);
    setPolygonClosed(false);
  };
  const closePolygon = () => marks.length >= 3 && setPolygonClosed(true);
  const measurement = renderMeasurement(tool, marks, polygonClosed, grid);
  const canClosePolygon = tool === "polygon" && marks.length >= 3 && !polygonClosed;

  return (
    <>
      <div className="viewer-toolbar">
        <label className="viewer-select-label">
          <span>Composición</span>
          <select className="viewer-select" aria-label="Composición visible" value={layer} disabled={!hasResult} onChange={(event) => {
            setLayer(event.target.value);
            if (event.target.value === "candidates") setShowSegmentation(true);
          }}>
            {LAYERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label className="toggle-control">
          <input
            type="checkbox"
            checked={showSegmentation}
            disabled={!hasResult}
            onChange={(event) => {
              setShowSegmentation(event.target.checked);
              if (!event.target.checked && layer === "candidates") setLayer("true-color");
            }}
          />
          <span className="toggle-track"><span /></span>
          <span>{layer === "candidates" && showSegmentation ? "Clases + humo" : showSegmentation ? "Con segmentación" : "Original"}</span>
        </label>
        <label className="toggle-control">
          <input type="checkbox" checked={showMarks} disabled={!hasResult} onChange={(event) => setShowMarks(event.target.checked)} />
          <span className="toggle-track"><span /></span><span>Marcas</span>
        </label>
      </div>

      <div className="image-stage" ref={stageRef} onClick={handleImageClick}>
        {!hasResult ? (
          <div className={`empty-state${errorMessage ? " is-error" : ""}`}>
            <span className="empty-mark" aria-hidden="true">{loading ? "◌" : errorMessage ? "!" : "⌁"}</span>
            <strong>{loading ? "Procesando imágenes…" : errorMessage ? "No se pudo mostrar el análisis" : "Haz la segmentación"}</strong>
            <span>{loading ? "La máscara y las composiciones estarán aquí cuando termine." : errorMessage || "Elige una escena o sube una pareja True Color + SWIR y pulsa «Iniciar segmentación»."}</span>
          </div>
        ) : (
          <>
            {imageFailed ? (
              <div className="empty-state is-error">
                <span className="empty-mark" aria-hidden="true">!</span>
                <strong>No se pudo cargar esta vista</strong>
                <span>Prueba a cambiar la composición o vuelve a ejecutar el análisis.</span>
              </div>
            ) : (
              <>
                <img
                  ref={imageRef}
                  src={source}
                  alt={layer === "candidates" ? "Candidatos de superficie y humo probable" : `${layer === "swir" ? "SWIR" : "True Color"}${showSegmentation ? " con segmentación" : " original"}`}
                  onError={() => {
                    setImageFailed(true);
                    onError("No se pudo cargar la imagen resultante.");
                  }}
                />
                <canvas ref={canvasRef} aria-hidden="true" />
              </>
            )}
          </>
        )}
      </div>

      <div className="measurement-toolbar" aria-label="Herramientas de medición">
        <label className="measurement-select-label">
          <span>Herramienta</span>
          <select className="viewer-select" aria-label="Herramienta de medición" value={tool} disabled={!hasResult} onChange={(event) => {
            const nextTool = event.target.value;
            if (nextTool !== tool) {
              setMarks([]);
              setPolygonClosed(false);
            }
            setTool(nextTool);
          }}>
            {TOOLS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <div className="mark-actions">
          <button className="text-button" type="button" disabled={!hasResult || !marks.length} onClick={undo}>Deshacer</button>
          {tool === "polygon" && <button className="text-button" type="button" disabled={!canClosePolygon} onClick={closePolygon}>Cerrar área</button>}
          <button className="text-button" type="button" disabled={!hasResult || !marks.length} onClick={clear}>Limpiar</button>
        </div>
      </div>
      <div className="measurement-result" aria-live="polite">{measurement}</div>
    </>
  );
}
