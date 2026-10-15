export function distanceBetween(a, b, grid) {
  const dx = (b.x - a.x) * (grid.gsd_x_m || 1);
  const dy = (b.y - a.y) * (grid.gsd_y_m || 1);
  return Math.hypot(dx, dy);
}

export function polylineLength(points, grid, close = false) {
  let length = 0;
  for (let index = 1; index < points.length; index += 1) {
    length += distanceBetween(points[index - 1], points[index], grid);
  }
  if (close && points.length > 2) {
    length += distanceBetween(points.at(-1), points[0], grid);
  }
  return length;
}

export function polygonArea(points, grid) {
  const scaleX = grid.gsd_x_m || 1;
  const scaleY = grid.gsd_y_m || 1;
  let twiceArea = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    twiceArea += current.x * scaleX * next.y * scaleY - next.x * scaleX * current.y * scaleY;
  }
  return Math.abs(twiceArea) / 2;
}

export function formatNumber(value, decimals = 0) {
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(value);
}

export function formatArea(value, unit) {
  if (unit === "m²" && value >= 10000) return `${formatNumber(value / 10000, 2)} ha`;
  if (unit === "m²") return `${formatNumber(value, 0)} m²`;
  return `${formatNumber(value, 0)} px²`;
}

export function formatLength(value, unit) {
  if (unit === "m" && value >= 1000) return `${formatNumber(value / 1000, 2)} km`;
  return `${formatNumber(value, value < 10 ? 1 : 0)} ${unit}`;
}
