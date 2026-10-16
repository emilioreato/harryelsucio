import { useEffect, useRef, useState } from "react";
import { formatNumber } from "../domain/measurements.js";

const MASK_SAMPLE_SIZE = 64;

function formatScaleDistance(meters) {
  if (meters >= 1000) {
    const kilometers = meters / 1000;
    const decimals = Number.isInteger(kilometers) ? 0 : 1;
    return `${formatNumber(kilometers, decimals)} km`;
  }
  const decimals = Number.isInteger(meters) ? 0 : 1;
  return `${formatNumber(meters, decimals)} m`;
}

function niceStep(totalMeters, axisPixels) {
  if (!Number.isFinite(totalMeters) || totalMeters <= 0 || axisPixels <= 0) return null;
  const targetPixels = Math.min(60, axisPixels / 3);
  const targetMeters = totalMeters * targetPixels / axisPixels;
  const exponent = Math.floor(Math.log10(targetMeters));
  const minimumPixels = Math.min(14, targetPixels * 0.55);
  const maximumPixels = Math.max(axisPixels / 2, targetPixels * 1.45);
  const candidates = [];

  for (let power = exponent - 2; power <= exponent + 2; power += 1) {
    for (const multiplier of [1, 2, 5]) {
      const meters = multiplier * (10 ** power);
      const pixels = meters * axisPixels / totalMeters;
      if (pixels >= minimumPixels && pixels <= maximumPixels) {
        candidates.push({ meters, pixels });
      }
    }
  }

  if (!candidates.length) return { meters: totalMeters, pixels: axisPixels };
  return candidates.reduce((best, candidate) => (
    Math.abs(candidate.pixels - targetPixels) < Math.abs(best.pixels - targetPixels)
      ? candidate
      : best
  ));
}

function measureMaskEdges(maskImages) {
  const occupancy = new Uint8Array(MASK_SAMPLE_SIZE * MASK_SAMPLE_SIZE);
  let hasMask = false;
  const canvas = document.createElement("canvas");
  canvas.width = MASK_SAMPLE_SIZE;
  canvas.height = MASK_SAMPLE_SIZE;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return { horizontal: "top", vertical: "right" };

  for (const image of Object.values(maskImages || {})) {
    if (!image?.naturalWidth || !image.naturalHeight) continue;
    try {
      context.clearRect(0, 0, MASK_SAMPLE_SIZE, MASK_SAMPLE_SIZE);
      context.drawImage(image, 0, 0, MASK_SAMPLE_SIZE, MASK_SAMPLE_SIZE);
      const { data } = context.getImageData(0, 0, MASK_SAMPLE_SIZE, MASK_SAMPLE_SIZE);
      for (let pixel = 0; pixel < occupancy.length; pixel += 1) {
        const offset = pixel * 4;
        if (data[offset + 3] > 40 && (data[offset] + data[offset + 1] + data[offset + 2]) / 3 > 80) {
          occupancy[pixel] = 1;
          hasMask = true;
        }
      }
    } catch {
      // A missing or unreadable mask must not hide the scale.
    }
  }

  if (!hasMask) return { horizontal: "top", vertical: "right" };
  const depth = Math.max(2, Math.round(MASK_SAMPLE_SIZE * 0.08));
  let top = 0;
  let bottom = 0;
  let left = 0;
  let right = 0;
  for (let y = 0; y < depth; y += 1) {
    for (let x = 0; x < MASK_SAMPLE_SIZE; x += 1) {
      top += occupancy[y * MASK_SAMPLE_SIZE + x];
      bottom += occupancy[(MASK_SAMPLE_SIZE - depth + y) * MASK_SAMPLE_SIZE + x];
    }
  }
  for (let x = 0; x < depth; x += 1) {
    for (let y = 0; y < MASK_SAMPLE_SIZE; y += 1) {
      left += occupancy[y * MASK_SAMPLE_SIZE + x];
      right += occupancy[y * MASK_SAMPLE_SIZE + MASK_SAMPLE_SIZE - depth + x];
    }
  }
  return {
    horizontal: top <= bottom ? "top" : "bottom",
    vertical: left < right ? "left" : "right",
  };
}

function axisTicks(start, end, step) {
  if (!step?.pixels || !Number.isFinite(start) || !Number.isFinite(end)) return [];
  const length = end - start;
  const count = Math.floor(length / step.pixels);
  return Array.from({ length: count + 1 }, (_, index) => start + index * step.pixels);
}

export default function GsdScaleRuler({ grid, imageRef, maskImages }) {
  const rulerRef = useRef(null);
  const [layout, setLayout] = useState(null);

  useEffect(() => {
    const image = imageRef?.current;
    const ruler = rulerRef.current;
    if (!image || !ruler) {
      setLayout(null);
      return undefined;
    }

    let frame = 0;
    const measure = () => {
      const imageWidth = Number(grid?.ancho_px || image.naturalWidth);
      const imageHeight = Number(grid?.alto_px || image.naturalHeight);
      const gsdX = Number(grid?.gsd_x_m);
      const gsdY = Number(grid?.gsd_y_m);
      const width = Number.parseFloat(image.style.width) || image.clientWidth;
      const height = Number.parseFloat(image.style.height) || image.clientHeight;
      const stageWidth = ruler.clientWidth;
      const stageHeight = ruler.clientHeight;
      if (!image.complete || !image.naturalWidth || width <= 0 || height <= 0
        || !Number.isFinite(gsdX) || gsdX <= 0 || !Number.isFinite(gsdY) || gsdY <= 0) {
        setLayout(null);
        return;
      }

      const left = image.offsetLeft;
      const top = image.offsetTop;
      const horizontalStep = niceStep(imageWidth * gsdX, width);
      const verticalStep = niceStep(imageHeight * gsdY, height);
      const edges = measureMaskEdges(maskImages);
      if (!horizontalStep || !verticalStep) {
        setLayout(null);
        return;
      }

      setLayout({
        left, top, width, height,
        stageWidth,
        stageHeight,
        horizontal: edges.horizontal,
        vertical: edges.vertical,
        horizontalStep,
        verticalStep,
        horizontalTicks: axisTicks(left, left + width, horizontalStep),
        verticalTicks: axisTicks(top, top + height, verticalStep),
      });
    };
    const scheduleMeasure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };

    scheduleMeasure();
    image.addEventListener("load", scheduleMeasure);
    window.addEventListener("resize", scheduleMeasure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleMeasure);
    observer?.observe(image);
    observer?.observe(ruler);
    return () => {
      cancelAnimationFrame(frame);
      image.removeEventListener("load", scheduleMeasure);
      window.removeEventListener("resize", scheduleMeasure);
      observer?.disconnect();
    };
  }, [grid?.ancho_px, grid?.alto_px, grid?.gsd_x_m, grid?.gsd_y_m, imageRef, maskImages]);

  if (!layout) return <div ref={rulerRef} className="gsd-scale-ruler" aria-hidden="true" />;

  const horizontalY = layout.horizontal === "top" ? layout.top : layout.top + layout.height;
  const verticalX = layout.vertical === "left" ? layout.left : layout.left + layout.width;
  const horizontalDirection = layout.horizontal === "top" ? 1 : -1;
  const verticalDirection = layout.vertical === "left" ? 1 : -1;
  const horizontalLabelX = layout.left + layout.horizontalStep.pixels / 2;
  const horizontalLabelY = horizontalY + horizontalDirection * 11;
  const verticalLabelX = verticalX + verticalDirection * 7;
  const verticalLabelY = layout.top + layout.verticalStep.pixels / 2;
  const horizontalLabel = formatScaleDistance(layout.horizontalStep.meters);
  const verticalLabel = formatScaleDistance(layout.verticalStep.meters);
  const accessibleDescription = `Escala horizontal: marcas cada ${horizontalLabel}; escala vertical: marcas cada ${verticalLabel}.`;
  const linePath = [
    `M ${layout.left} ${horizontalY} H ${layout.left + layout.width}`,
    ...layout.horizontalTicks.map((x) => `M ${x} ${horizontalY - 4} V ${horizontalY + 4}`),
    `M ${verticalX} ${layout.top} V ${layout.top + layout.height}`,
    ...layout.verticalTicks.map((y) => `M ${verticalX - 4} ${y} H ${verticalX + 4}`),
  ].join(" ");

  return (
    <div ref={rulerRef} className="gsd-scale-ruler" role="img" aria-label={accessibleDescription}>
      <svg
        className="gsd-scale-ruler__line"
        width={layout.stageWidth}
        height={layout.stageHeight}
        viewBox={`0 0 ${layout.stageWidth} ${layout.stageHeight}`}
        aria-hidden="true"
      >
        <path d={linePath} />
      </svg>
      <span
        className="gsd-scale-ruler__label gsd-scale-ruler__label--horizontal"
        style={{ left: horizontalLabelX, top: horizontalLabelY }}
        aria-hidden="true"
      >
        {horizontalLabel}
      </span>
      <span
        className="gsd-scale-ruler__label gsd-scale-ruler__label--vertical"
        data-side={layout.vertical}
        style={{ left: verticalLabelX, top: verticalLabelY }}
        aria-hidden="true"
      >
        {verticalLabel}
      </span>
    </div>
  );
}
