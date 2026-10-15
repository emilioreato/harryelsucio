import { useEffect, useRef, useState } from "react";
import { Button } from "@radix-ui/themes";
import { Eye, EyeOff, Flame, Image as ImageIcon, Layers3, ScanLine } from "lucide-react";
import { api } from "../services/api.js";
import { formatNumber } from "../domain/measurements.js";

const LAYERS = [
  ["true-color", "True Color", ImageIcon],
  ["swir", "SWIR", ScanLine],
  ["candidates", "Clases", Layers3],
];

const CLASSIFICATION_DESCRIPTION = "Vista de clasificación estimada: superficie afectada candidata, humo probable y otras clases contextuales. Es orientativa, no verdad terreno.";

function visibleLayer(layer) {
  if (layer === "candidates") return "candidates";
  if (layer === "reference-wildfires") return "reference-wildfires";
  return layer;
}

function loadMaskImage(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = url;
  });
}

function pixelLabel(point, grid) {
  const x = Math.round(point.x);
  const y = Math.round(point.y);
  if (!grid.gsd_x_m) return `Píxel (${x}, ${y})`;
  return `Píxel (${x}, ${y}) · ${formatNumber(point.x * grid.gsd_x_m, 1)}, ${formatNumber(point.y * grid.gsd_y_m, 1)} m`;
}

function labelMaskRegions(pixels, width, height, grid) {
  const size = width * height;
  const labels = new Uint32Array(size);
  let foregroundCount = 0;
  for (let index = 0; index < size; index += 1) {
    if (pixels[index * 4] >= 128) foregroundCount += 1;
  }
  if (!foregroundCount) return { labels, regions: [], width, height };

  const queue = new Int32Array(foregroundCount);
  const scaleX = grid.gsd_x_m || 1;
  const scaleY = grid.gsd_y_m || 1;
  const metricScale = Number.isFinite(grid.gsd_x_m) && grid.gsd_x_m > 0
    && Number.isFinite(grid.gsd_y_m) && grid.gsd_y_m > 0;
  const regions = [];

  for (let seed = 0; seed < size; seed += 1) {
    if (labels[seed] || pixels[seed * 4] < 128) continue;
    const id = regions.length + 1;
    let head = 0;
    let tail = 0;
    let pixelCount = 0;
    let horizontalEdges = 0;
    let verticalEdges = 0;
    queue[tail++] = seed;
    labels[seed] = id;

    while (head < tail) {
      const index = queue[head++];
      const x = index % width;
      const y = Math.floor(index / width);
      pixelCount += 1;
      if (y === 0 || pixels[(index - width) * 4] < 128) horizontalEdges += 1;
      if (y === height - 1 || pixels[(index + width) * 4] < 128) horizontalEdges += 1;
      if (x === 0 || pixels[(index - 1) * 4] < 128) verticalEdges += 1;
      if (x === width - 1 || pixels[(index + 1) * 4] < 128) verticalEdges += 1;

      for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
        const neighborY = y + offsetY;
        if (neighborY < 0 || neighborY >= height) continue;
        for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
          if (offsetX === 0 && offsetY === 0) continue;
          const neighborX = x + offsetX;
          if (neighborX < 0 || neighborX >= width) continue;
          const neighbor = neighborY * width + neighborX;
          if (!labels[neighbor] && pixels[neighbor * 4] >= 128) {
            labels[neighbor] = id;
            queue[tail++] = neighbor;
          }
        }
      }
    }

    regions.push({
      id,
      pixel_count: pixelCount,
      area: pixelCount * (metricScale ? scaleX * scaleY : 1),
      area_unit: metricScale ? "m²" : "px²",
      perimeter: metricScale
        ? horizontalEdges * scaleX + verticalEdges * scaleY
        : horizontalEdges + verticalEdges,
      perimeter_unit: metricScale ? "m" : "px",
    });
  }

  return { labels, regions, width, height };
}

export default function ImageViewer({
  jobId, grid, layer, setLayer, showSegmentation, setShowSegmentation,
  showMarks, setShowMarks, tool, marks, setMarks, distancePreview,
  setDistancePreview, inspectedPixel, setInspectedPixel, selectedRegion,
  onRegionSelect, onRegionsReady, hasWildfiresReference, errorMessage, onError,
}) {
  const stageRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const regionLabelsRef = useRef(null);
  const semanticOverlayRef = useRef(null);
  const activePointer = useRef(null);
  const dragStart = useRef(null);
  const [maskLayers, setMaskLayers] = useState({});
  const [showVisibleSurface, setShowVisibleSurface] = useState(true);
  const [showSmoke, setShowSmoke] = useState(true);
  const [showUnderSmoke, setShowUnderSmoke] = useState(true);
  const currentLayer = jobId ? visibleLayer(layer) : null;
  const source = currentLayer && jobId ? `${api.layerUrl(jobId, currentLayer)}?v=${jobId}` : "";
  const hasResult = Boolean(jobId && grid);
  const supportsSeparateOverlays = layer === "true-color" || layer === "swir";
  const availableLayers = hasWildfiresReference
    ? [...LAYERS, ["reference-wildfires", "Wildfires · ref.", Layers3]]
    : LAYERS;

  useEffect(() => {
    semanticOverlayRef.current = null;
    setMaskLayers({});
    if (!hasResult) return undefined;
    let cancelled = false;
    const layers = ["visible-surface", "smoke", "smoke-candidates"];
    Promise.all(layers.map(async (name) => [
      name,
      await loadMaskImage(api.layerUrl(jobId, name)),
    ])).then((entries) => {
      if (!cancelled) setMaskLayers(Object.fromEntries(entries));
    });
    return () => { cancelled = true; };
  }, [hasResult, jobId]);

  useEffect(() => {
    regionLabelsRef.current = null;
    onRegionsReady([]);
    if (!hasResult) return undefined;
    let cancelled = false;
    const maskImage = new Image();
    maskImage.onload = () => {
      if (cancelled) return;
      const maskCanvas = document.createElement("canvas");
      maskCanvas.width = grid.ancho_px;
      maskCanvas.height = grid.alto_px;
      const maskContext = maskCanvas.getContext("2d", { willReadFrequently: true });
      maskContext.drawImage(maskImage, 0, 0, maskCanvas.width, maskCanvas.height);
      const pixels = maskContext.getImageData(0, 0, maskCanvas.width, maskCanvas.height).data;
      const labeledMask = labelMaskRegions(pixels, maskCanvas.width, maskCanvas.height, grid);
      regionLabelsRef.current = labeledMask;
      onRegionsReady(labeledMask.regions);
    };
    maskImage.src = api.layerUrl(jobId, "mask");
    return () => {
      cancelled = true;
      regionLabelsRef.current = null;
    };
  }, [hasResult, jobId, grid?.ancho_px, grid?.alto_px, grid?.gsd_x_m, grid?.gsd_y_m, onRegionsReady]);

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

      if (supportsSeparateOverlays) {
        const width = grid.ancho_px;
        const height = grid.alto_px;
        const cached = semanticOverlayRef.current;
        const overlayKey = {
          jobId,
          width,
          height,
          smoke: maskLayers.smoke,
          visible: maskLayers["visible-surface"],
          hidden: maskLayers["smoke-candidates"],
          showSmoke,
          showVisibleSurface,
          showUnderSmoke,
          showContours: showSegmentation,
        };
        const cacheMatches = cached && Object.keys(overlayKey).every(
          (key) => cached.key[key] === overlayKey[key],
        );
        if (!cacheMatches) {
          const overlay = document.createElement("canvas");
          overlay.width = width;
          overlay.height = height;
          const overlayContext = overlay.getContext("2d", { willReadFrequently: true });
          const composite = overlayContext.createImageData(width, height);
          const sampleMask = (image) => {
            if (!image) return null;
            const maskCanvas = document.createElement("canvas");
            maskCanvas.width = width;
            maskCanvas.height = height;
            const maskContext = maskCanvas.getContext("2d", { willReadFrequently: true });
            maskContext.drawImage(image, 0, 0, width, height);
            return maskContext.getImageData(0, 0, width, height).data;
          };
          const smoke = showSmoke ? sampleMask(maskLayers.smoke) : null;
          const visible = showVisibleSurface ? sampleMask(maskLayers["visible-surface"]) : null;
          const hidden = showUnderSmoke ? sampleMask(maskLayers["smoke-candidates"]) : null;
          const inside = (data, pixel) => Boolean(data && data[pixel * 4] >= 128);
          const edge = (data, pixel, x, y) => inside(data, pixel) && (
            x === 0 || !inside(data, pixel - 1)
            || x === width - 1 || !inside(data, pixel + 1)
            || y === 0 || !inside(data, pixel - width)
            || y === height - 1 || !inside(data, pixel + width)
          );
          const putLayer = (pixel, color, alpha) => {
            const offset = pixel * 4;
            const priorAlpha = composite.data[offset + 3] / 255;
            const outputAlpha = alpha + priorAlpha * (1 - alpha);
            if (!outputAlpha) return;
            const priorWeight = priorAlpha * (1 - alpha);
            composite.data[offset] = (color[0] * alpha + composite.data[offset] * priorWeight) / outputAlpha;
            composite.data[offset + 1] = (color[1] * alpha + composite.data[offset + 1] * priorWeight) / outputAlpha;
            composite.data[offset + 2] = (color[2] * alpha + composite.data[offset + 2] * priorWeight) / outputAlpha;
            composite.data[offset + 3] = outputAlpha * 255;
          };

          for (let pixel = 0; pixel < width * height; pixel += 1) {
            const x = pixel % width;
            const y = Math.floor(pixel / width);
            // El humo se pinta primero y las dos superficies después para que
            // el azul no desature el rojo ni oculte la hipótesis SWIR.
            if (inside(smoke, pixel)) putLayer(pixel, [35, 145, 235], 0.27);
            if (inside(visible, pixel)) putLayer(pixel, [230, 38, 30], 0.50);
            if (inside(hidden, pixel)) {
              const hatch = (x + y) % 10 < 2;
              putLayer(pixel, [220, 30, 195], hatch ? 0.62 : 0.34);
            }
            if (showSegmentation && edge(visible, pixel, x, y)) {
              putLayer(pixel, [255, 230, 30], 1);
            } else if (showSegmentation && edge(hidden, pixel, x, y) && (x + y) % 8 < 4) {
              // Borde discontinuo: hipótesis, no perímetro confirmado.
              putLayer(pixel, [255, 45, 220], 1);
            }
          }
          overlayContext.putImageData(composite, 0, 0);
          semanticOverlayRef.current = { key: overlayKey, canvas: overlay };
        }
        if (semanticOverlayRef.current?.canvas) {
          context.drawImage(semanticOverlayRef.current.canvas, 0, 0, imageRect.width, imageRect.height);
        }
      }

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
        context.lineCap = "round";
        context.lineJoin = "round";
        context.setLineDash(dashed ? [7, 5] : []);
        context.strokeStyle = "rgba(24, 15, 30, .88)";
        context.lineWidth = 5;
        context.stroke();
        context.strokeStyle = "#ff4fa3";
        context.lineWidth = 2.6;
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
        context.strokeStyle = "rgba(24, 15, 30, .92)";
        context.lineWidth = 2;
        context.stroke();
        context.fillStyle = "#ff4fa3";
        context.fill();
      };

      if (tool === "distance") {
        for (let index = 0; index + 1 < marks.length; index += 2) drawLine(marks[index], marks[index + 1]);
        if (distancePreview) drawLine(distancePreview.start, distancePreview.end, true);
      } else if (tool === "area" && selectedRegion && regionLabelsRef.current) {
        const { labels, width, height } = regionLabelsRef.current;
        const highlight = document.createElement("canvas");
        highlight.width = width;
        highlight.height = height;
        const highlightContext = highlight.getContext("2d");
        const overlay = highlightContext.createImageData(width, height);
        const selectedId = selectedRegion.id;
        const setPink = (offset, alpha) => {
          overlay.data[offset] = 255;
          overlay.data[offset + 1] = 79;
          overlay.data[offset + 2] = 163;
          overlay.data[offset + 3] = Math.max(overlay.data[offset + 3], alpha);
        };

        for (let index = 0; index < labels.length; index += 1) {
          if (labels[index] !== selectedId) continue;
          const x = index % width;
          const y = Math.floor(index / width);
          const boundary = x === 0 || labels[index - 1] !== selectedId
            || x === width - 1 || labels[index + 1] !== selectedId
            || y === 0 || labels[index - width] !== selectedId
            || y === height - 1 || labels[index + width] !== selectedId;
          const offset = index * 4;
          setPink(offset, boundary ? 255 : 48);
          if (boundary) {
            if (x > 0) setPink((index - 1) * 4, 255);
            if (x + 1 < width) setPink((index + 1) * 4, 255);
            if (y > 0) setPink((index - width) * 4, 255);
            if (y + 1 < height) setPink((index + width) * 4, 255);
          }
        }
        highlightContext.putImageData(overlay, 0, 0);
        context.drawImage(highlight, 0, 0, imageRect.width, imageRect.height);
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
  }, [source, showMarks, marks, distancePreview, tool, inspectedPixel, selectedRegion,
    supportsSeparateOverlays, grid?.ancho_px, grid?.alto_px, jobId, maskLayers,
    showVisibleSurface, showSmoke, showUnderSmoke, showSegmentation]);

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
    if (!hasResult || (tool !== "pixel" && tool !== "area")) return;
    const point = pointAt(event.clientX, event.clientY);
    if (!point) return;
    if (tool === "area") {
      const labelMap = regionLabelsRef.current;
      if (!labelMap) return;
      const x = Math.max(0, Math.min(labelMap.width - 1, Math.floor(point.x)));
      const y = Math.max(0, Math.min(labelMap.height - 1, Math.floor(point.y)));
      const regionId = labelMap.labels[y * labelMap.width + x];
      onRegionSelect(regionId ? labelMap.regions[regionId - 1] : null);
    } else if (tool === "pixel") setInspectedPixel(point);
  };

  const pixelReadout = tool === "pixel" && inspectedPixel ? pixelLabel(inspectedPixel, grid) : "";

  return (
    <>
      <div className="viewer-toolbar">
        <div className="layer-control" role="group" aria-label="Composición visible">
          {availableLayers.map(([id, label, Icon]) => (
            <Button
              className={`layer-choice${layer === id ? " is-active" : ""}`}
              key={id}
              variant="ghost"
              size="1"
              type="button"
              aria-pressed={layer === id}
              disabled={!hasResult}
              title={id === "reference-wildfires" ? "Referencia visual; no es verdad terreno ni se usa para segmentar." : id === "candidates" ? CLASSIFICATION_DESCRIPTION : undefined}
              aria-label={id === "candidates" ? CLASSIFICATION_DESCRIPTION : label}
              onClick={() => {
                setLayer(id);
                if (id === "candidates") setShowSegmentation(true);
                if (id === "reference-wildfires") setShowSegmentation(false);
              }}
            ><Icon size={14} aria-hidden="true" /><span>{label}</span></Button>
          ))}
        </div>
        <div className="layer-control" role="group" aria-label="Capas de segmentación independientes">
          <Button className={`layer-choice${showVisibleSurface ? " is-active" : ""}`} variant="ghost" size="1" type="button"
            disabled={!hasResult || !supportsSeparateOverlays || !maskLayers["visible-surface"]}
            aria-pressed={showVisibleSurface} title="Superficie observada fuera del humo; roja."
            onClick={() => setShowVisibleSurface((visible) => !visible)}>
            <Flame size={13} aria-hidden="true" /><span>Superficie</span>
          </Button>
          <Button className={`layer-choice${showSmoke ? " is-active" : ""}`} variant="ghost" size="1" type="button"
            disabled={!hasResult || !supportsSeparateOverlays || !maskLayers.smoke}
            aria-pressed={showSmoke} title="Humo probable; azul."
            onClick={() => setShowSmoke((visible) => !visible)}>
            <Layers3 size={13} aria-hidden="true" /><span>Humo</span>
          </Button>
          <Button className={`layer-choice${showUnderSmoke ? " is-active" : ""}`} variant="ghost" size="1" type="button"
            disabled={!hasResult || !supportsSeparateOverlays || !maskLayers["smoke-candidates"]}
            aria-pressed={showUnderSmoke} title="Evidencia SWIR bajo humo; fucsia tramado, hipótesis no confirmada."
            onClick={() => setShowUnderSmoke((visible) => !visible)}>
            <ScanLine size={13} aria-hidden="true" /><span>Bajo humo</span>
          </Button>
        </div>
        <Button
          className={`overlay-toggle${showSegmentation ? " is-active" : ""}`}
          variant="ghost"
          size="1"
          type="button"
          disabled={!hasResult || layer === "candidates" || layer === "reference-wildfires"}
          aria-pressed={showSegmentation}
          aria-label={`${showSegmentation ? "Ocultar" : "Mostrar"} los contornos de superficie visible e hipótesis bajo humo.`}
          title="Alternar el contorno confirmado y el borde discontinuo de la hipótesis. Las capas se controlan por separado."
          onClick={() => setShowSegmentation((visible) => !visible)}
        >
          {showSegmentation ? <Flame size={13} aria-hidden="true" /> : <Eye size={13} aria-hidden="true" />}
          <span>{showSegmentation ? "Contornos" : "Sin contorno"}</span>
        </Button>
        <Button className={`mark-toggle${showMarks ? " is-active" : ""}`} variant="ghost" size="1" type="button" disabled={!hasResult} aria-pressed={showMarks} aria-label={`${showMarks ? "Ocultar" : "Mostrar"} marcas`} title={`${showMarks ? "Ocultar" : "Mostrar"} marcas`} onClick={() => setShowMarks((visible) => !visible)}>
          {showMarks ? <EyeOff size={13} aria-hidden="true" /> : <Eye size={13} aria-hidden="true" />}
          <span>Marcas</span>
        </Button>
      </div>

      <div
        className={`image-stage${tool === "distance" ? " is-ruling" : tool === "area" || tool === "pixel" ? " has-tool" : ""}`}
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
              alt={layer === "candidates" ? CLASSIFICATION_DESCRIPTION : layer === "reference-wildfires" ? "Composición Wildfires de referencia; no es verdad terreno" : `${layer === "swir" ? "SWIR" : "True Color"}${supportsSeparateOverlays ? " con capas independientes" : ""}`}
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
