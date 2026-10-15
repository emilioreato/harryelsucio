import { useEffect, useRef } from "react";
import { api } from "../services/api.js";
import { formatNumber, formatArea, formatLength, distanceBetween, polygonArea, polylineLength } from "../domain/measurements.js";

const LAYERS = [
  ["true-color", "True Color"],
  ["swir", "SWIR"],
  ["candidates", "Clases + humo"],
];
const TOOLS = [
  ["view", "Vista"],
  ["distance", "Distancia"],
  ["polygon", "Polígono"],
  ["pixel", "Píxel"],
];

function visibleLayer(layer, showSegmentation) {
  if (!showSegmentation) return layer === "swir" ? "swir" : "true-color";
  if (layer === "swir") return "overlay-swir";
  if (layer === "candidates") return "candidates";
  return "overlay-true-color";
}

function renderMeasurement(tool, marks, inspectedPixel, polygonClosed, grid) {
  if (!grid) return "";
  const unit = grid.gsd_x_m ? "m" : "px";
  if (tool === "pixel" && inspectedPixel) {
    const x = inspectedPixel.x * (grid.gsd_x_m || 1);
    const y = inspectedPixel.y * (grid.gsd_y_m || 1);
    return `Píxel (${Math.round(inspectedPixel.x)}, ${Math.round(inspectedPixel.y)})${grid.gsd_x_m ? ` · ${formatNumber(x, 1)}, ${formatNumber(y, 1)} m` : ""}`;
  }
  if (tool === "distance") {
    const segments = [];
    for (let index = 0; index + 1 < marks.length; index += 2) {
      segments.push(`Tramo ${index / 2 + 1}: ${formatLength(distanceBetween(marks[index], marks[index + 1], grid), unit)}`);
    }
    if (marks.length % 2) segments.push("Añade otro punto para completar el tramo.");
    return segments.join(" · ");
  }
  if (tool === "polygon") {
    if (!polygonClosed || marks.length < 3) {
      return marks.length < 3 ? "Marca al menos tres vértices." : "Cierra el polígono para calcular área y perímetro.";
    }
    return `Área manual: ${formatArea(polygonArea(marks, grid), grid.gsd_x_m ? "m²" : "px²")} · Perímetro: ${formatLength(polylineLength(marks, grid, true), unit)}`;
  }
  return "";
}

export default function ImageViewer({
  jobId, grid, layer, setLayer, showSegmentation, setShowSegmentation, showMarks, setShowMarks,
  tool, setTool, marks, setMarks, inspectedPixel, setInspectedPixel, polygonClosed, setPolygonClosed,
  errorMessage, onError,
}) {
  const stageRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const currentLayer = jobId ? visibleLayer(layer, showSegmentation) : null;
  const source = currentLayer && jobId ? `${api.layerUrl(jobId, currentLayer)}?v=${jobId}` : "";
  const hasResult = Boolean(jobId && grid);
  const marksForDraw = tool === "pixel" && inspectedPixel ? [inspectedPixel] : marks;

  useEffect(() => {
    const image = imageRef.current;
    const canvas = canvasRef.current;
    const stage = stageRef.current;
    if (!image || !canvas || !stage || !image.complete || !image.naturalWidth) return undefined;

    const draw = () => {
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
      if (marksForDraw.length > 1) {
        context.beginPath();
        marksForDraw.forEach((point, index) => {
          const x = point.x * scaleX;
          const y = point.y * scaleY;
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        if (tool === "polygon" && polygonClosed && marksForDraw.length > 2) context.closePath();
        context.strokeStyle = "#f6dc49";
        context.lineWidth = 2;
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
  }, [source, showMarks, marksForDraw, tool, polygonClosed]);

  const handleImageClick = (event) => {
    if (!hasResult || tool === "view" || !imageRef.current) return;
    const rect = imageRef.current.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return;
    const point = {
      x: Math.min(grid.ancho_px - 1, Math.max(0, (event.clientX - rect.left) * grid.ancho_px / rect.width)),
      y: Math.min(grid.alto_px - 1, Math.max(0, (event.clientY - rect.top) * grid.alto_px / rect.height)),
    };
    if (tool === "pixel") setInspectedPixel(point);
    else {
      setMarks((current) => [...current, point]);
      setPolygonClosed(false);
    }
  };

  const undo = () => {
    if (tool === "pixel") setInspectedPixel(null);
    else {
      setMarks((current) => current.slice(0, -1));
      setPolygonClosed(false);
    }
  };
  const clear = () => {
    setMarks([]);
    setInspectedPixel(null);
    setPolygonClosed(false);
  };
  const closePolygon = () => marks.length >= 3 && setPolygonClosed(true);
  const measurement = renderMeasurement(tool, marks, inspectedPixel, polygonClosed, grid);
  const canClosePolygon = tool === "polygon" && marks.length >= 3 && !polygonClosed;

  return (
    <>
      <div className="viewer-toolbar">
        <div className="layer-control" role="group" aria-label="Composición visible">
          {LAYERS.map(([id, label]) => (
            <button
              className={`layer-choice${layer === id ? " is-active" : ""}`}
              key={id}
              type="button"
              aria-pressed={layer === id}
              disabled={!hasResult}
              onClick={() => {
                setLayer(id);
                if (id === "candidates") setShowSegmentation(true);
              }}
            >{label}</button>
          ))}
        </div>
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
          <div className="empty-state">
            <span className="empty-mark" aria-hidden="true">⌁</span>
            <strong>{errorMessage ? "No se pudo mostrar el análisis" : "La imagen aparecerá aquí"}</strong>
            <span>{errorMessage || "Elige una escena y ejecuta la segmentación."}</span>
          </div>
        ) : (
          <>
            <img
              ref={imageRef}
              src={source}
              alt={layer === "candidates" ? "Candidatos de superficie y humo probable" : `${layer === "swir" ? "SWIR" : "True Color"}${showSegmentation ? " con segmentación" : " original"}`}
              onError={() => onError("No se pudo cargar la imagen resultante.")}
            />
            <canvas ref={canvasRef} aria-hidden="true" />
            {tool === "pixel" && inspectedPixel && (
              <div className="pixel-readout">{renderMeasurement(tool, marks, inspectedPixel, polygonClosed, grid)}</div>
            )}
          </>
        )}
      </div>

      <div className="measurement-toolbar" aria-label="Herramientas de medición">
        <div className="tool-group" role="group" aria-label="Herramienta">
          {TOOLS.map(([id, label]) => (
            <button
              key={id}
              className={`tool-button${tool === id ? " is-active" : ""}`}
              type="button"
              disabled={!hasResult}
              onClick={() => {
                setTool(id);
                if (id === "pixel") setInspectedPixel(null);
              }}
            >{label}</button>
          ))}
        </div>
        <div className="mark-actions">
          <button className="text-button" type="button" disabled={!hasResult || (!marks.length && !inspectedPixel)} onClick={undo}>Deshacer</button>
          <button className="text-button" type="button" disabled={!canClosePolygon} onClick={closePolygon}>Cerrar área</button>
          <button className="text-button" type="button" disabled={!hasResult || (!marks.length && !inspectedPixel)} onClick={clear}>Borrar marcas</button>
        </div>
      </div>
      <div className="measurement-result" aria-live="polite">{measurement}</div>
    </>
  );
}
