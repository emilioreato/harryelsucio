import { useEffect, useRef, useState } from "react";
import { Button } from "@radix-ui/themes";
import { Eye, EyeOff, Image as ImageIcon, Layers3, ScanLine } from "lucide-react";
import { api } from "../services/api.js";
import { distanceBetween, formatArea, formatLength } from "../domain/measurements.js";
import GsdScaleRuler from "./GsdScaleRuler.jsx";
import ZoomableImageViewport from "./ZoomableImageViewport.jsx";

const LAYERS = [
  ["true-color", "True Color", ImageIcon],
  ["swir", "SWIR", ScanLine],
];

const CLASSIFICATION_DESCRIPTION = "Zona quemada estimada: unión de superficie visible y evidencia SWIR bajo humo. No confirmada en terreno.";

function visibleLayer(layer) {
  if (layer === "candidates") return "true-color";
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

function rulerDistanceLabel(start, end, grid) {
  const hasMetricScale = Number.isFinite(grid?.gsd_x_m) && grid.gsd_x_m > 0
    && Number.isFinite(grid?.gsd_y_m) && grid.gsd_y_m > 0;
  return formatLength(distanceBetween(start, end, grid), hasMetricScale ? "m" : "px");
}

function drawAnnotation(context, annotation, scaleX, scaleY) {
  const points = annotation.points.map((point) => ({
    x: point.x * scaleX,
    y: point.y * scaleY,
  }));
  const lineWidth = Math.max(1.5, annotation.width * scaleX);
  context.save();
  context.strokeStyle = annotation.color;
  context.fillStyle = annotation.color;
  context.lineWidth = lineWidth;
  context.lineCap = "round";
  context.lineJoin = "round";

  if (annotation.kind === "freehand") {
    if (points.length === 1) {
      context.beginPath();
      context.arc(points[0].x, points[0].y, lineWidth / 2, 0, Math.PI * 2);
      context.fill();
    } else {
      context.beginPath();
      context.moveTo(points[0].x, points[0].y);
      points.slice(1).forEach((point) => context.lineTo(point.x, point.y));
      context.stroke();
    }
  } else if (annotation.kind === "line" || annotation.kind === "arrow") {
    const [start, end] = points;
    context.beginPath();
    context.moveTo(start.x, start.y);
    context.lineTo(end.x, end.y);
    context.stroke();
    if (annotation.kind === "arrow") {
      const angle = Math.atan2(end.y - start.y, end.x - start.x);
      const head = Math.max(8, annotation.width * 4 * scaleX);
      context.beginPath();
      context.moveTo(end.x, end.y);
      context.lineTo(end.x - head * Math.cos(angle - Math.PI / 7), end.y - head * Math.sin(angle - Math.PI / 7));
      context.lineTo(end.x - head * Math.cos(angle + Math.PI / 7), end.y - head * Math.sin(angle + Math.PI / 7));
      context.closePath();
      context.fill();
    }
  } else if (annotation.kind === "rectangle" || annotation.kind === "ellipse") {
    const [first, second] = points;
    const left = Math.min(first.x, second.x);
    const top = Math.min(first.y, second.y);
    const width = Math.abs(second.x - first.x);
    const height = Math.abs(second.y - first.y);
    context.beginPath();
    if (annotation.kind === "rectangle") context.rect(left, top, width, height);
    else context.ellipse(left + width / 2, top + height / 2, Math.max(0.5, width / 2), Math.max(0.5, height / 2), 0, 0, Math.PI * 2);
    context.stroke();
  } else if (annotation.kind === "text") {
    const [anchor] = points;
    context.font = `600 ${Math.max(12, 24 * scaleY)}px system-ui, sans-serif`;
    context.textBaseline = "top";
    context.lineWidth = Math.max(3, annotation.width * scaleX * 1.5);
    context.strokeStyle = "rgba(8, 14, 22, .94)";
    context.strokeText(annotation.text, anchor.x, anchor.y);
    context.fillStyle = annotation.color;
    context.fillText(annotation.text, anchor.x, anchor.y);
  }
  context.restore();
}

function distanceToSegment(point, start, end) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;
  if (!lengthSquared) return Math.hypot(point.x - start.x, point.y - start.y);
  const progress = Math.max(0, Math.min(1,
    ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared,
  ));
  return Math.hypot(point.x - (start.x + progress * dx), point.y - (start.y + progress * dy));
}

function annotationHit(annotation, point, tolerance, scaleX, scaleY, context) {
  const [first, second] = annotation.points;
  if (!first) return false;
  const width = Number.isFinite(annotation.width) ? Math.max(1, annotation.width) : 4;
  const strokeTolerance = tolerance + width / 2;

  if (annotation.kind === "text") {
    const fontSize = Math.max(12, 24 * scaleY);
    context?.save();
    if (context) context.font = `600 ${fontSize}px system-ui, sans-serif`;
    const textWidth = (context?.measureText(annotation.text || "").width || 0) / scaleX;
    context?.restore();
    const textHeight = fontSize / scaleY;
    return point.x >= first.x - tolerance
      && point.x <= first.x + textWidth + tolerance
      && point.y >= first.y - tolerance
      && point.y <= first.y + textHeight + tolerance;
  }

  if (annotation.kind === "rectangle") {
    const left = Math.min(first.x, second.x) - strokeTolerance;
    const right = Math.max(first.x, second.x) + strokeTolerance;
    const top = Math.min(first.y, second.y) - strokeTolerance;
    const bottom = Math.max(first.y, second.y) + strokeTolerance;
    return point.x >= left && point.x <= right && point.y >= top && point.y <= bottom;
  }

  if (annotation.kind === "ellipse") {
    const radiusX = Math.max(0.5, Math.abs(second.x - first.x) / 2) + strokeTolerance;
    const radiusY = Math.max(0.5, Math.abs(second.y - first.y) / 2) + strokeTolerance;
    const centerX = (first.x + second.x) / 2;
    const centerY = (first.y + second.y) / 2;
    return ((point.x - centerX) / radiusX) ** 2 + ((point.y - centerY) / radiusY) ** 2 <= 1;
  }

  const points = annotation.points;
  if (points.length === 1) return Math.hypot(point.x - first.x, point.y - first.y) <= strokeTolerance;
  for (let index = 1; index < points.length; index += 1) {
    if (distanceToSegment(point, points[index - 1], points[index]) <= strokeTolerance) return true;
  }
  return annotation.kind === "arrow"
    && Math.hypot(point.x - second.x, point.y - second.y) <= tolerance + width * 4;
}

function drawMeasurementBadge(context, text, centerX, centerY, imageWidth, imageHeight, normal = null) {
  context.save();
  context.font = "400 9px system-ui, sans-serif";
  const badgeHeight = 16;
  const maxWidth = Math.max(24, imageWidth - 8);
  const badgeWidth = Math.min(context.measureText(text).width + 8, maxWidth);
  const margin = 3;
  let x = Math.max(margin, Math.min(imageWidth - badgeWidth - margin, centerX - badgeWidth / 2));
  let y = Math.max(margin, Math.min(imageHeight - badgeHeight - margin, centerY - badgeHeight / 2));
  const radius = 4;

  if (normal && imageWidth >= badgeWidth + margin * 2 && imageHeight >= badgeHeight + margin * 2) {
    const halfExtent = (Math.abs(normal.x) * badgeWidth + Math.abs(normal.y) * badgeHeight) / 2;
    const offset = halfExtent + 4;
    const anchors = [0.5, 0.36, 0.64, 0.22, 0.78];
    const placements = anchors.flatMap((position) => [1, -1].map((side) => {
      const anchorX = centerX + normal.tangentX * normal.lineLength * (position - 0.5);
      const anchorY = centerY + normal.tangentY * normal.lineLength * (position - 0.5);
      const candidateX = anchorX + normal.x * offset * side - badgeWidth / 2;
      const candidateY = anchorY + normal.y * offset * side - badgeHeight / 2;
      const inside = candidateX >= margin && candidateY >= margin
        && candidateX + badgeWidth <= imageWidth - margin
        && candidateY + badgeHeight <= imageHeight - margin;
      return {
        x: candidateX,
        y: candidateY,
        inside,
        score: Math.abs(position - 0.5) * 100 + (side === 1 ? 0 : 1),
      };
    })).filter((placement) => placement.inside).sort((a, b) => a.score - b.score);
    if (placements.length) {
      ({ x, y } = placements[0]);
    } else {
      // Keep the compact label visible on very short or edge-hugging measurements.
      const side = centerY < imageHeight / 2 ? 1 : -1;
      y = Math.max(margin, Math.min(imageHeight - badgeHeight - margin, centerY + normal.y * offset * side - badgeHeight / 2));
      x = Math.max(margin, Math.min(imageWidth - badgeWidth - margin, centerX + normal.x * offset * side - badgeWidth / 2));
    }
  }

  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + badgeWidth - radius, y);
  context.quadraticCurveTo(x + badgeWidth, y, x + badgeWidth, y + radius);
  context.lineTo(x + badgeWidth, y + badgeHeight - radius);
  context.quadraticCurveTo(x + badgeWidth, y + badgeHeight, x + badgeWidth - radius, y + badgeHeight);
  context.lineTo(x + radius, y + badgeHeight);
  context.quadraticCurveTo(x, y + badgeHeight, x, y + badgeHeight - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
  context.fillStyle = "rgba(14, 12, 24, .9)";
  context.fill();
  context.strokeStyle = "rgba(255, 79, 163, .82)";
  context.lineWidth = 0.65;
  context.stroke();
  context.fillStyle = "#ffb2d5";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, x + badgeWidth / 2, y + badgeHeight / 2, Math.max(8, badgeWidth - 8));
  context.restore();
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
  const neighborOffsets = [-width, width, -1, 1];
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
    let sumX = 0;
    let sumY = 0;
    let horizontalEdges = 0;
    let verticalEdges = 0;
    queue[tail++] = seed;
    labels[seed] = id;

    while (head < tail) {
      const index = queue[head++];
      const x = index % width;
      const y = Math.floor(index / width);
      pixelCount += 1;
      sumX += x + 0.5;
      sumY += y + 0.5;
      if (y === 0 || pixels[(index - width) * 4] < 128) horizontalEdges += 1;
      if (y === height - 1 || pixels[(index + width) * 4] < 128) horizontalEdges += 1;
      if (x === 0 || pixels[(index - 1) * 4] < 128) verticalEdges += 1;
      if (x === width - 1 || pixels[(index + 1) * 4] < 128) verticalEdges += 1;

      for (let direction = 0; direction < neighborOffsets.length; direction += 1) {
        if ((direction === 0 && y === 0) || (direction === 1 && y === height - 1)
          || (direction === 2 && x === 0) || (direction === 3 && x === width - 1)) continue;
        const neighbor = index + neighborOffsets[direction];
        if (!labels[neighbor] && pixels[neighbor * 4] >= 128) {
          labels[neighbor] = id;
          queue[tail++] = neighbor;
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
      centroid: { x: sumX / pixelCount, y: sumY / pixelCount },
    });
  }

  return { labels, regions, width, height };
}

export default function ImageViewer({
  jobId, grid, layer, setLayer, showSegmentation, setShowSegmentation,
  showVisibleSurface, setShowVisibleSurface, showSmoke, setShowSmoke,
  showAnnotations, setShowAnnotations, tool,
  annotationTool, annotationColor, annotationWidth, annotationText, setAnnotationText, setAnnotations, annotations,
  marks, setMarks, distancePreview,
  setDistancePreview, selectedRegion,
  onRegionSelect, onRegionsReady, hasWildfiresReference, errorMessage, onError,
}) {
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const surfaceRef = useRef(null);
  const regionLabelsRef = useRef(null);
  const semanticOverlayRef = useRef(null);
  const activePointer = useRef(null);
  const dragStart = useRef(null);
  const annotationPointer = useRef(null);
  const draftAnnotationRef = useRef(null);
  const areaPointer = useRef(null);
  const suppressAreaClick = useRef(false);
  const [maskLayers, setMaskLayers] = useState({});
  const [maskLayersReady, setMaskLayersReady] = useState(false);
  const [draftAnnotation, setDraftAnnotation] = useState(null);
  const currentLayer = jobId ? visibleLayer(layer) : null;
  const source = currentLayer && jobId ? `${api.layerUrl(jobId, currentLayer)}?v=${jobId}` : "";
  const hasResult = Boolean(jobId && grid);
  const supportsSeparateOverlays = hasResult;
  const availableLayers = hasWildfiresReference
    ? [...LAYERS, ["reference-wildfires", "Wildfires · ref.", Layers3]]
    : LAYERS;

  useEffect(() => {
    semanticOverlayRef.current = null;
    setMaskLayers({});
    setMaskLayersReady(false);
    if (!hasResult) return undefined;
    let cancelled = false;
    const layers = [
      "estimated-surface",
      "smoke",
    ];
    Promise.all(layers.map(async (name) => [
      name,
      await loadMaskImage(api.layerUrl(jobId, name)),
    ])).then((entries) => {
      if (!cancelled) {
        setMaskLayers(Object.fromEntries(entries));
        setMaskLayersReady(true);
      }
    });
    return () => { cancelled = true; };
  }, [hasResult, jobId]);

  useEffect(() => {
    regionLabelsRef.current = null;
    onRegionsReady([]);
    if (!hasResult || !maskLayersReady) return undefined;
    let cancelled = false;
    const maskImage = new Image();
    maskImage.onload = () => {
      if (cancelled) return;
      const labelImage = (image) => {
        const maskCanvas = document.createElement("canvas");
        maskCanvas.width = grid.ancho_px;
        maskCanvas.height = grid.alto_px;
        const maskContext = maskCanvas.getContext("2d", { willReadFrequently: true });
        maskContext.drawImage(image, 0, 0, maskCanvas.width, maskCanvas.height);
        const pixels = maskContext.getImageData(0, 0, maskCanvas.width, maskCanvas.height).data;
        return labelMaskRegions(pixels, maskCanvas.width, maskCanvas.height, grid);
      };
      const visible = labelImage(maskImage);
      visible.regions = visible.regions.map((region) => ({ ...region, kind: "visible" }));
      const regions = visible.regions;
      regionLabelsRef.current = visible;
      onRegionsReady(regions);
    };
    maskImage.src = api.layerUrl(jobId, "estimated-surface");
    return () => {
      cancelled = true;
      regionLabelsRef.current = null;
    };
  }, [hasResult, maskLayersReady, jobId, grid?.ancho_px, grid?.alto_px, grid?.gsd_x_m, grid?.gsd_y_m,
    onRegionsReady]);

  useEffect(() => {
    const image = imageRef.current;
    const canvas = canvasRef.current;
    const surface = surfaceRef.current;
    if (!image || !canvas || !surface) return undefined;

    const draw = () => {
      if (!image.complete || !image.naturalWidth) return;
      const baseWidth = Number.parseFloat(surface.style.width) || surface.clientWidth;
      const baseHeight = Number.parseFloat(surface.style.height) || surface.clientHeight;
      if (!baseWidth || !baseHeight) return;
      const ratio = window.devicePixelRatio || 1;
      canvas.style.width = `${baseWidth}px`;
      canvas.style.height = `${baseHeight}px`;
      canvas.width = Math.max(1, Math.round(baseWidth * ratio));
      canvas.height = Math.max(1, Math.round(baseHeight * ratio));
      const context = canvas.getContext("2d");
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, baseWidth, baseHeight);

      if (supportsSeparateOverlays) {
        const width = grid.ancho_px;
        const height = grid.alto_px;
        const cached = semanticOverlayRef.current;
        const overlayKey = {
          jobId,
          width,
          height,
          smoke: maskLayers.smoke,
          visible: maskLayers["estimated-surface"],
          showSmoke,
          showVisibleSurface,
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
          const visible = showVisibleSurface ? sampleMask(maskLayers["estimated-surface"]) : null;
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
            if (inside(visible, pixel)) putLayer(pixel, [230, 38, 30], 0.50);
            if (inside(smoke, pixel)) putLayer(pixel, [30, 120, 221], 0.30);
            if (edge(smoke, pixel, x, y)) putLayer(pixel, [19, 93, 168], 0.42);
            if (showSegmentation && edge(visible, pixel, x, y)) {
              putLayer(pixel, [255, 230, 30], 1);
            }
          }
          overlayContext.putImageData(composite, 0, 0);
          semanticOverlayRef.current = { key: overlayKey, canvas: overlay };
        }
        if (semanticOverlayRef.current?.canvas) {
          context.drawImage(semanticOverlayRef.current.canvas, 0, 0, baseWidth, baseHeight);
        }
      }

      const renderAnnotations = () => {
        const scaleX = baseWidth / grid.ancho_px;
        const scaleY = baseHeight / grid.alto_px;
        [...annotations, ...(draftAnnotation ? [draftAnnotation] : [])]
          .forEach((annotation) => drawAnnotation(context, annotation, scaleX, scaleY));
      };
      const scaleX = baseWidth / grid.ancho_px;
      const scaleY = baseHeight / grid.alto_px;
      const toCanvas = (point) => ({ x: point.x * scaleX, y: point.y * scaleY });
      const drawLine = (start, end, dashed = false, label = "") => {
        const a = toCanvas(start);
        const b = toCanvas(end);
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.lineCap = "round";
        context.lineJoin = "round";
        context.setLineDash(dashed ? [5, 7] : []);
        context.strokeStyle = "rgba(24, 15, 30, .62)";
        context.lineWidth = 2.1;
        context.stroke();
        context.strokeStyle = "#ff4fa3";
        context.lineWidth = 1.25;
        context.stroke();
        context.setLineDash([]);
        const lineLength = Math.hypot(b.x - a.x, b.y - a.y);
        if (lineLength < 2) return;
        if (label) {
          let normalX = -(b.y - a.y) / lineLength;
          let normalY = (b.x - a.x) / lineLength;
          if (normalY > 0) {
            normalX *= -1;
            normalY *= -1;
          }
          const middleX = (a.x + b.x) / 2;
          const middleY = (a.y + b.y) / 2;
          const normal = {
            x: normalX,
            y: normalY,
            tangentX: (b.x - a.x) / lineLength,
            tangentY: (b.y - a.y) / lineLength,
            lineLength,
          };
          drawMeasurementBadge(context, label, middleX, middleY, baseWidth, baseHeight, normal);
        }
      };

      if (tool === "distance") {
        for (let index = 0; index + 1 < marks.length; index += 2) {
          const start = marks[index];
          const end = marks[index + 1];
          drawLine(start, end, false, rulerDistanceLabel(start, end, grid));
        }
        if (distancePreview) {
          drawLine(distancePreview.start, distancePreview.end, true,
            rulerDistanceLabel(distancePreview.start, distancePreview.end, grid));
        }
      } else if (tool === "area" && selectedRegion && regionLabelsRef.current) {
        const selectedMask = regionLabelsRef.current;
        const { labels, width, height } = selectedMask;
        const highlight = document.createElement("canvas");
        highlight.width = width;
        highlight.height = height;
        const highlightContext = highlight.getContext("2d");
        const overlay = highlightContext.createImageData(width, height);
        const selectedId = selectedRegion.id;
        const selectionColor = [255, 79, 163];
        const setPink = (offset, alpha) => {
          overlay.data[offset] = selectionColor[0];
          overlay.data[offset + 1] = selectionColor[1];
          overlay.data[offset + 2] = selectionColor[2];
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
        context.drawImage(highlight, 0, 0, baseWidth, baseHeight);
        if (selectedRegion.centroid) {
          const center = toCanvas(selectedRegion.centroid);
          drawMeasurementBadge(
            context,
            `Área · ${formatArea(selectedRegion.area, selectedRegion.area_unit)}`,
            center.x,
            center.y,
            baseWidth,
            baseHeight,
          );
        }
      }

      marks.forEach((point, index) => {
        const { x, y } = toCanvas(point);
        context.beginPath();
        context.arc(x, y, tool === "distance" ? 2.25 : 5, 0, Math.PI * 2);
        context.fillStyle = tool === "distance" ? "#ff4fa3" : "#d94a8b";
        context.fill();
        context.strokeStyle = tool === "distance" ? "rgba(255,255,255,.8)" : "rgba(255,255,255,.95)";
        context.lineWidth = tool === "distance" ? 0.8 : 1.5;
        context.stroke();
        if (tool !== "distance") {
          context.fillStyle = "#fff";
          context.font = "600 10px ui-monospace, monospace";
          context.fillText(String(index + 1), x + 8, y - 8);
        }
      });
      if (showAnnotations) renderAnnotations();
    };

    draw();
    image.addEventListener("load", draw);
    window.addEventListener("resize", draw);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(draw);
    observer?.observe(surface);
    return () => {
      image.removeEventListener("load", draw);
      window.removeEventListener("resize", draw);
      observer?.disconnect();
    };
  }, [source, showAnnotations, marks, annotations, draftAnnotation, distancePreview, tool, selectedRegion,
    supportsSeparateOverlays, grid?.ancho_px, grid?.alto_px, grid?.gsd_x_m, grid?.gsd_y_m, jobId, maskLayers,
    showVisibleSurface, showSmoke, showSegmentation]);

  const pointAt = (clientX, clientY, clamp = false) => {
    const image = imageRef.current;
    if (!image || !grid) return null;
    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    if (!clamp && (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom)) return null;
    const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
    return {
      x: Math.min(grid.ancho_px - 1, x * grid.ancho_px / rect.width),
      y: Math.min(grid.alto_px - 1, y * grid.alto_px / rect.height),
    };
  };

  const handlePointerDown = (event) => {
    const primaryPointer = event.pointerType !== "mouse" || event.button === 0;
    if (hasResult && tool === "annotate" && annotationTool === "eraser" && primaryPointer) {
      if (!showAnnotations) return;
      const point = pointAt(event.clientX, event.clientY);
      const imageRect = imageRef.current?.getBoundingClientRect();
      const context = canvasRef.current?.getContext("2d");
      if (!point || !imageRect?.width || !imageRect?.height) return;
      event.preventDefault();
      const scaleX = imageRect.width / grid.ancho_px;
      const scaleY = imageRect.height / grid.alto_px;
      const tolerance = 10 / Math.min(scaleX, scaleY);
      setAnnotations((current) => {
        for (let index = current.length - 1; index >= 0; index -= 1) {
          if (annotationHit(current[index], point, tolerance, scaleX, scaleY, context)) {
            return current.filter((_, itemIndex) => itemIndex !== index);
          }
        }
        return current;
      });
      return;
    }
    if (hasResult && tool === "annotate" && annotationTool !== "text" && annotationTool !== "eraser" && primaryPointer) {
      const point = pointAt(event.clientX, event.clientY);
      if (!point) return;
      event.preventDefault();
      const draft = {
        id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
        kind: annotationTool,
        points: [point],
        color: annotationColor,
        width: annotationWidth,
      };
      annotationPointer.current = event.pointerId;
      draftAnnotationRef.current = draft;
      setDraftAnnotation(draft);
      event.currentTarget.setPointerCapture?.(event.pointerId);
      return;
    }
    if (hasResult && tool === "area" && (event.pointerType !== "mouse" || event.button === 0)) {
      suppressAreaClick.current = false;
      areaPointer.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
      return;
    }
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
    if (annotationPointer.current === event.pointerId) {
      const point = pointAt(event.clientX, event.clientY, true);
      const draft = draftAnnotationRef.current;
      if (!point || !draft) return;
      let next;
      if (draft.kind === "freehand") {
        const prior = draft.points[draft.points.length - 1];
        if (Math.hypot(point.x - prior.x, point.y - prior.y) < 1.5) return;
        next = { ...draft, points: [...draft.points, point] };
      } else {
        next = { ...draft, points: [draft.points[0], point] };
      }
      draftAnnotationRef.current = next;
      setDraftAnnotation(next);
      return;
    }
    if (areaPointer.current?.pointerId === event.pointerId) {
      if (Math.hypot(event.clientX - areaPointer.current.x, event.clientY - areaPointer.current.y) >= 4) {
        areaPointer.current.moved = true;
      }
      return;
    }
    if (activePointer.current !== event.pointerId || !dragStart.current) return;
    const end = pointAt(event.clientX, event.clientY, true);
    if (end) setDistancePreview({ start: dragStart.current, end });
  };

  const handlePointerUp = (event) => {
    if (annotationPointer.current === event.pointerId) {
      const draft = draftAnnotationRef.current;
      const end = pointAt(event.clientX, event.clientY, true);
      if (draft && end) {
        const start = draft.points[0];
        let points = draft.points;
        if (draft.kind === "freehand") {
          const prior = points[points.length - 1];
          if (Math.hypot(end.x - prior.x, end.y - prior.y) >= 1.5) points = [...points, end];
        } else {
          points = [start, end];
        }
        const length = Math.hypot(end.x - start.x, end.y - start.y);
        if (draft.kind === "freehand" || length >= 2) {
          setAnnotations((current) => [...current, { ...draft, points }]);
        }
      }
      annotationPointer.current = null;
      draftAnnotationRef.current = null;
      setDraftAnnotation(null);
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      return;
    }
    if (areaPointer.current?.pointerId === event.pointerId) {
      suppressAreaClick.current = areaPointer.current.moved
        || Math.hypot(event.clientX - areaPointer.current.x, event.clientY - areaPointer.current.y) >= 4;
      areaPointer.current = null;
      return;
    }
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
    if (annotationPointer.current === event.pointerId) {
      annotationPointer.current = null;
      draftAnnotationRef.current = null;
      setDraftAnnotation(null);
      return;
    }
    if (areaPointer.current?.pointerId === event.pointerId) {
      areaPointer.current = null;
      suppressAreaClick.current = false;
      return;
    }
    if (activePointer.current !== event.pointerId) return;
    activePointer.current = null;
    dragStart.current = null;
    setDistancePreview(null);
  };

  const handleImageClick = (event) => {
    if (!hasResult || (tool !== "annotate" && tool !== "area")) return;
    if (tool === "annotate") {
      if (annotationTool !== "text" || !annotationText.trim()) return;
      const point = pointAt(event.clientX, event.clientY);
      if (!point) return;
      setAnnotations((current) => [...current, {
        id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
        kind: "text",
        points: [point],
        text: annotationText.trim(),
        color: annotationColor,
        width: annotationWidth,
      }]);
      setAnnotationText("");
      return;
    }
    if (tool === "area" && suppressAreaClick.current) {
      suppressAreaClick.current = false;
      return;
    }
    const point = pointAt(event.clientX, event.clientY);
    if (!point) return;
    if (tool === "area") {
      const labelMap = regionLabelsRef.current;
      if (!labelMap) return;
      const x = Math.max(0, Math.min(grid.ancho_px - 1, Math.floor(point.x)));
      const y = Math.max(0, Math.min(grid.alto_px - 1, Math.floor(point.y)));
      const pixel = y * grid.ancho_px + x;
      const regionId = labelMap.labels[pixel];
      const region = regionId ? labelMap.regions[regionId - 1] : null;
      onRegionSelect(region);
    }
  };

  return (
    <>
      <div className="viewer-toolbar">
        <div className="layer-control layer-control--composition" role="group" aria-label="Composición visible">
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
        <div className="viewer-toolbar__tools">
          <div className="layer-control layer-control--overlays" role="group" aria-label="Detección y humo">
          <Button className={`layer-choice layer-choice--overlay layer-choice--burned${showVisibleSurface ? " is-active" : ""}`} variant="ghost" size="1" type="button"
            disabled={!hasResult || !supportsSeparateOverlays}
            aria-pressed={showVisibleSurface} title="Zona quemada estimada: superficie visible y evidencia SWIR bajo humo unidas; no confirmada en terreno."
            onClick={() => setShowVisibleSurface((visible) => !visible)}>
            <span>Detección</span>
          </Button>
          <Button className={`layer-choice layer-choice--overlay layer-choice--smoke${showSmoke ? " is-active" : ""}`} variant="ghost" size="1" type="button"
            disabled={!hasResult || !supportsSeparateOverlays}
            aria-pressed={showSmoke} title="Humo probable; azul."
            onClick={() => setShowSmoke((visible) => !visible)}>
            <span>Humo</span>
          </Button>
          </div>
          <Button
            className={`overlay-toggle${showSegmentation ? " is-active" : ""}`}
            variant="ghost"
            size="1"
            type="button"
            disabled={!hasResult}
            aria-pressed={showSegmentation}
            aria-label={`${showSegmentation ? "Ocultar" : "Mostrar"} el contorno de la zona quemada estimada.`}
            title="Alternar el contorno de la detección unificada."
            onClick={() => setShowSegmentation((visible) => !visible)}
          >
            <span>Borde</span>
          </Button>
          <Button
            className={`mark-toggle${showAnnotations ? " is-active" : ""}`}
            variant="ghost"
            size="1"
            type="button"
            disabled={!hasResult}
            aria-pressed={showAnnotations}
            aria-label={`${showAnnotations ? "Ocultar" : "Mostrar"} anotaciones`}
            title="Mostrar u ocultar las anotaciones del editor; no afecta las mediciones de Regla o Área."
            onClick={() => setShowAnnotations((visible) => !visible)}
          >
            {showAnnotations ? <Eye size={12} aria-hidden="true" /> : <EyeOff size={12} aria-hidden="true" />}
            <span>Marcas</span>
          </Button>
        </div>
      </div>

      <div
        className={`image-stage${tool === "distance" ? " is-ruling" : tool === "area" || tool === "annotate" ? " has-tool" : ""}${tool === "annotate" ? " is-annotating" : ""}${tool === "annotate" && annotationTool === "eraser" ? " is-erasing" : ""}`}
      >
        {!hasResult ? (
          <div className="empty-state">
            <span className="empty-mark" aria-hidden="true">⌁</span>
            <strong>{errorMessage ? "No se pudo mostrar el análisis" : "La imagen aparecerá aquí"}</strong>
            <span>{errorMessage || "Inicia un análisis para ver la imagen."}</span>
          </div>
        ) : (
          <ZoomableImageViewport
            className="zoomable-viewport--image"
            imageRef={imageRef}
            surfaceRef={surfaceRef}
            src={source}
            alt={layer === "candidates" ? CLASSIFICATION_DESCRIPTION : layer === "reference-wildfires" ? "Composición Wildfires de referencia; no es verdad terreno" : `${layer === "swir" ? "SWIR" : "True Color"}${supportsSeparateOverlays ? " con capas independientes" : ""}`}
            imageClassName="image-viewer-result-image"
            resetKey={jobId}
            allowLeftPan={tool === "view"}
            allowDoubleClick={tool === "view"}
            showCrosshair={tool !== "view"}
            onError={() => onError("No se pudo cargar la imagen resultante.")}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onClick={handleImageClick}
          >
            <canvas ref={canvasRef} aria-hidden="true" />
            <GsdScaleRuler grid={grid} imageRef={imageRef} maskImages={maskLayers} />
          </ZoomableImageViewport>
        )}
      </div>
    </>
  );
}
