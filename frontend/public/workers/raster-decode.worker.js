const TRANSPARENT = [0, 0, 0, 0];

function rampColor(stops, v) {
  if (!Number.isFinite(v) || v < (stops[0]?.min ?? Infinity)) return null;
  let hit = stops[0];
  for (const s of stops) if (v >= s.min) hit = s;
  return hit ? hit.color : null;
}

function colorizeToRGBA(values, nx, ny, stops) {
  const out = new Uint8ClampedArray(nx * ny * 4);
  for (let row = 0; row < ny; row++) {
    const srcRow = ny - 1 - row;
    for (let col = 0; col < nx; col++) {
      const c = rampColor(stops, values[srcRow * nx + col] ?? NaN);
      if (c) out.set(c, (row * nx + col) * 4);
    }
  }
  return out;
}

self.onmessage = function (e) {
  const { values_b64, nx, ny, stops, id } = e.data;
  try {
    const bin = atob(values_b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const values = new Float32Array(bytes.buffer, bytes.byteOffset, nx * ny);
    const rgba = colorizeToRGBA(values, nx, ny, stops);
    self.postMessage({ id, rgba, nx, ny, success: true });
  } catch (err) {
    self.postMessage({ id, error: err.message, success: false });
  }
};
