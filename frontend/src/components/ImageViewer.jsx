import { useEffect, useRef } from "react";
import { Button } from "@radix-ui/themes";
import { Eye, EyeOff, Flame, Image as ImageIcon, Layers3, ScanLine } from "lucide-react";
import { api } from "../services/api.js";
import { formatNumber } from "../domain/measurements.js";

const LAYERS = [
  ["true-color", "True Color", ImageIcon],
  ["swir", "SWIR", ScanLine],
  ["candidates", "Clases + humo", Layers3],
];

function visibleLayer(layer, showSegmentation, showFireHotspots) {
  if (showFireHotspots) return "fire-hotspots";
  if (layer === "candidates") return "candidates";
  if (!showSegmentation) return layer;
  return layer === "swir" ? "overlay-swir" : "overlay-true-color";
}

function pixelLabel(point, grid) {
  const x = Math.round(point.x);
  const y = Math.round(point.y);
  if (!grid.gsd_x_m) return `Píxel (${x}, ${y})`;
  return `Píxel (${x}, ${y}) · ${formatNumber(point.x * grid.gsd_x_m, 1)}, ${formatNumber(point.y * grid.gsd_y_m, 1)} m`;
}

export default function ImageViewer({
  jobId, grid, layer, setLayer, showSegmentation, setShowSegmentation,
  showFireHotspots, setShowFireHotspots,
  showMarks, setShowMarks, tool, marks, setMarks, distancePreview,
  setDistancePreview, inspectedPixel, setInspectedPixel, polygonClosed,
  setPolygonClosed, errorMessage, onError,
}) {
  const stageRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const activePointer = useRef(null);
  const dragStart = useRef(null);
  const currentLayer = jobId ? visibleLayer(layer, showSegmentation, showFireHotspots) : null;
  const source = currentLayer && jobId ? `${api.layerUrl(jobId, currentLayer)}?v=${jobId}` : "";
  const hasResult = Boolean(jobId && grid);

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
      const toCanvas = (point) => ({ x: point.x * scaleX, y: point.y * scaleY });
      const drawLine = (start, end, dashed = false) => {
        const a = toCanvas(start);
        const b = toCanvas(end);
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.setLineDash(dashed ? [7, 5] : []);
        context.strokeStyle = "#f6dc49";
        context.lineWidth = 2;
        context.stroke();
        context.setLineDash([]);
        const lineLength = Math.hypot(b.x - a.x, b.y - a.y);
        if (lineLength < 2) return;
        const angle = Math.atan2(b.y - a.y, b.x - a.x);
        const headLength = 14;
        context.beginPath();
        context.moveTo(b.x, b.y);
        context.lineTo(b.x - headLength * Math.cos(angle - Math.PI / 7), b.y - headLength * Math.sin(angle - Math.PI / 7));
        context.lineTo(b.x - headLength * Math.cos(angle + Math.PI / 7), b.y - headLength * Math.sin(angle + Math.PI / 7));
        context.closePath();
        context.fillStyle = "#f6dc49";
        context.fill();
      };

      if (tool === "distance") {
        for (let index = 0; index + 1 < marks.length; index += 2) drawLine(marks[index], marks[index + 1]);
        if (distancePreview) drawLine(distancePreview.start, distancePreview.end, true);
      } else if (tool === "polygon" && marks.length > 1) {
        context.beginPath();
        marks.forEach((point, index) => {
          const p = toCanvas(point);
          if (index === 0) context.moveTo(p.x, p.y);
          else context.lineTo(p.x, p.y);
        });
        if (polygonClosed && marks.length > 2) context.closePath();
        context.strokeStyle = "#f6dc49";
        context.lineWidth = 2;
        context.stroke();
      }

      const points = tool === "pixel" && inspectedPixel ? [inspectedPixel] : marks;
      points.forEach((point, index) => {
        const { x, y } = toCanvas(point);
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
  }, [source, showMarks, marks, distancePreview, tool, polygonClosed, inspectedPixel]);

  const pointAt = (clientX, clientY, clamp = false) => {
    const image = imageRef.current;
    if (!image || !grid) return null;
    const rect = image.getBoundingClientRect();
    if (!clamp && (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom)) return null;
    const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
    return {
      x: Math.min(grid.ancho_px - 1, x * grid.ancho_px / rect.width),
      y: Math.min(grid.alto_px - 1, y * grid.alto_px / rect.height),
    };
  };

  const handlePointerDown = (event) => {
    if (!hasResult || tool !== "distance" || (event.pointerType === "mouse" && event.button !== 0)) return;
    const point = pointAt(event.clientX, event.clientY);
    if (!point) return;
    event.preventDefault();
    activePointer.current = event.pointerId;
    dragStart.current = point;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDistancePreview({ start: point, end: point });
  };

  const handlePointerMove = (event) => {
    if (activePointer.current !== event.pointerId || !dragStart.current) return;
    const end = pointAt(event.clientX, event.clientY, true);
    if (end) setDistancePreview({ start: dragStart.current, end });
  };

  const handlePointerUp = (event) => {
    if (activePointer.current !== event.pointerId || !dragStart.current) return;
    const start = dragStart.current;
    const end = pointAt(event.clientX, event.clientY, true);
    const moved = end && Math.hypot(end.x - start.x, end.y - start.y) >= 2;
    if (moved) setMarks((current) => [...current, start, end]);
    activePointer.current = null;
    dragStart.current = null;
    setDistancePreview(null);
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  };

  const handlePointerCancel = (event) => {
    if (activePointer.current !== event.pointerId) return;
    activePointer.current = null;
    dragStart.current = null;
    setDistancePreview(null);
  };

  const handleImageClick = (event) => {
    if (!hasResult || (tool !== "pixel" && tool !== "polygon")) return;
    const point = pointAt(event.clientX, event.clientY);
    if (!point) return;
    if (tool === "pixel") setInspectedPixel(point);
    else {
      setMarks((current) => [...current, point]);
      setPolygonClosed(false);
    }
  };

  const pixelReadout = tool === "pixel" && inspectedPixel ? pixelLabel(inspectedPixel, grid) : "";

  return (
    <>
      <div className="viewer-toolbar">
        <div className="layer-control" role="group" aria-label="Composición visible">
          {LAYERS.map(([id, label, Icon]) => (
            <Button
              className={`layer-choice${layer === id ? " is-active" : ""}`}
              key={id}
              variant={layer === id ? "soft" : "ghost"}
              size="1"
              type="button"
              aria-pressed={layer === id}
              disabled={!hasResult}
              onClick={() => {
                setLayer(id);
                if (id === "candidates") setShowSegmentation(true);
              }}
            ><Icon size={14} aria-hidden="true" /><span>{label}</span></Button>
          ))}
        </div>
        <div className="overlay-control" role="group" aria-label="Original o segmentación">
          <Button className={`overlay-choice${!showSegmentation ? " is-active" : ""}`} variant={!showSegmentation ? "soft" : "ghost"} size="1" type="button" disabled={!hasResult} aria-pressed={!showSegmentation} onClick={() => {
            if (layer === "candidates") setLayer("true-color");
            setShowSegmentation(false);
          }}><Eye size={13} aria-hidden="true" />Original</Button>
          <Button className={`overlay-choice${showSegmentation ? " is-active" : ""}`} variant={showSegmentation ? "soft" : "ghost"} size="1" type="button" disabled={!hasResult || layer === "candidates"} aria-pressed={showSegmentation} onClick={() => setShowSegmentation(true)}><Flame size={13} aria-hidden="true" />Contorno</Button>
        </div>
        <Button className={`mark-toggle${showMarks ? " is-active" : ""}`} variant="outline" size="1" type="button" disabled={!hasResult} aria-pressed={showMarks} onClick={() => setShowMarks((visible) => !visible)}>
          {showMarks ? <EyeOff size={13} aria-hidden="true" /> : <Eye size={13} aria-hidden="true" />}
          {showMarks ? "Marcas" : "Ver marcas"}
        </Button>
        <Button className={`mark-toggle${showFireHotspots ? " is-active" : ""}`} variant="outline" size="1" type="button" disabled={!hasResult} aria-pressed={showFireHotspots} onClick={() => setShowFireHotspots((visible) => !visible)}>
          <Flame size={13} aria-hidden="true" />{showFireHotspots ? "Focos: sí" : "Focos: no"}
        </Button>
      </div>

      <div
        className={`image-stage${tool === "distance" ? " is-ruling" : tool === "polygon" || tool === "pixel" ? " has-tool" : ""}`}
        ref={stageRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onClick={handleImageClick}
      >
        {!hasResult ? (
          <div className="empty-state">
            <span className="empty-mark" aria-hidden="true">⌁</span>
            <strong>{errorMessage ? "No se pudo mostrar el análisis" : "La imagen aparecerá aquí"}</strong>
            <span>{errorMessage || "Inicia un análisis para ver la imagen."}</span>
          </div>
        ) : (
          <>
            <img
              ref={imageRef}
              src={source}
              alt={showFireHotspots ? "Composición True Color con focos visuales candidatos resaltados" : layer === "candidates" ? "Clases de superficie y humo probable" : `${layer === "swir" ? "SWIR" : "True Color"}${showSegmentation ? " con segmentación" : " original"}`}
              draggable="false"
              onError={() => onError("No se pudo cargar la imagen resultante.")}
            />
            <canvas ref={canvasRef} aria-hidden="true" />
            {pixelReadout && <div className="pixel-readout">{pixelReadout}</div>}
          </>
        )}
      </div>
    </>
  );
}
