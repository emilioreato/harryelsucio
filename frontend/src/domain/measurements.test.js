import test from "node:test";
import assert from "node:assert/strict";
import {
  distanceBetween,
  polygonArea,
  formatArea,
  formatLength,
} from "./measurements.js";

test("distance is measured in pixels when no GSD is available", () => {
  const grid = { gsd_x_m: null, gsd_y_m: null };
  assert.equal(distanceBetween({ x: 0, y: 0 }, { x: 3, y: 4 }, grid), 5);
});

test("distance respects a different scale on each axis", () => {
  const grid = { gsd_x_m: 2, gsd_y_m: 3 };
  assert.equal(distanceBetween({ x: 0, y: 0 }, { x: 3, y: 4 }, grid), Math.hypot(6, 12));
});

test("manual area uses the polygon area in square pixels without a GSD", () => {
  const grid = { gsd_x_m: null, gsd_y_m: null };
  const triangle = [{ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 4, y: 3 }];
  assert.equal(polygonArea(triangle, grid), 6);
});

test("manual area applies the scale on both axes", () => {
  const grid = { gsd_x_m: 2, gsd_y_m: 5 };
  const rectangle = [{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 2, y: 3 }, { x: 0, y: 3 }];
  assert.equal(polygonArea(rectangle, grid), 60);
});

test("small manual areas retain one decimal", () => {
  assert.equal(formatArea(0.4, "m²"), "0,4 m²");
});

test("large metric areas are converted to hectares", () => {
  assert.equal(formatArea(12500, "m²"), "1,25 ha");
});

test("long arrows are displayed in kilometres", () => {
  assert.equal(formatLength(2500, "m"), "2,50 km");
});
