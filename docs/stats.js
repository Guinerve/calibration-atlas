// Statistics for the explorer, kept identical to the Python analysis
// (tests/test_explorer.py checks them against it).

const CLIP = 0.0005; // smallest price Polymarket publishes; matches recalibration.py

const logit = (p) => {
  const q = Math.min(Math.max(p, CLIP), 1 - CLIP);
  return Math.log(q / (1 - q));
};
export const sigmoid = (x) => 1 / (1 + Math.exp(-x));

export function brier(price, outcome) {
  let total = 0;
  for (let i = 0; i < price.length; i++) total += (price[i] - outcome[i]) ** 2;
  return total / price.length;
}

// Per non-empty bin of price: count, mean price, how often Yes happened.
export function reliabilityBins(price, outcome, bins = 10) {
  const acc = Array.from({ length: bins }, () => ({ count: 0, sumP: 0, sumY: 0 }));
  for (let i = 0; i < price.length; i++) {
    const b = Math.min(Math.floor(price[i] * bins), bins - 1);
    acc[b].count += 1;
    acc[b].sumP += price[i];
    acc[b].sumY += outcome[i];
  }
  return acc.flatMap((a, b) => a.count === 0 ? [] : [{
    low: b / bins, high: (b + 1) / bins, count: a.count,
    meanPrice: a.sumP / a.count, observed: a.sumY / a.count,
  }]);
}

const inv2 = ([[a, b], [c, d]]) => {
  const det = a * d - b * c;
  return [[d / det, -b / det], [-c / det, a / det]];
};
const mul2 = (m, n) => [
  [m[0][0] * n[0][0] + m[0][1] * n[1][0], m[0][0] * n[0][1] + m[0][1] * n[1][1]],
  [m[1][0] * n[0][0] + m[1][1] * n[1][0], m[1][0] * n[0][1] + m[1][1] * n[1][1]],
];

// logit(P(Yes)) = a + b * logit(price), by Newton's method, with standard errors
// clustered by event (the same small sample correction statsmodels applies).
export function fitRecalibration(price, outcome, cluster) {
  const n = price.length;
  const x = price.map(logit);
  let a = 0, b = 1, hess = null, converged = false;
  for (let iter = 0; iter < 50; iter++) {
    let g0 = 0, g1 = 0, h00 = 0, h01 = 0, h11 = 0;
    for (let i = 0; i < n; i++) {
      const mu = sigmoid(a + b * x[i]);
      const w = mu * (1 - mu);
      g0 += outcome[i] - mu; g1 += (outcome[i] - mu) * x[i];
      h00 += w; h01 += w * x[i]; h11 += w * x[i] * x[i];
    }
    hess = [[h00, h01], [h01, h11]];
    const inv = inv2(hess);
    const da = inv[0][0] * g0 + inv[0][1] * g1, db = inv[1][0] * g0 + inv[1][1] * g1;
    a += da; b += db;
    if (!Number.isFinite(a) || !Number.isFinite(b)) break;
    if (Math.abs(da) + Math.abs(db) < 1e-10) { converged = true; break; }
  }
  // Separated outcomes have no finite maximum: the slope runs away instead of settling.
  if (!converged || Math.abs(b) > 10) {
    return { a, b, n, events: new Set(cluster).size, seA: NaN, seB: NaN, converged: false };
  }
  const scores = new Map();
  for (let i = 0; i < n; i++) {
    const r = outcome[i] - sigmoid(a + b * x[i]);
    const s = scores.get(cluster[i]) ?? [0, 0];
    s[0] += r; s[1] += r * x[i];
    scores.set(cluster[i], s);
  }
  let m00 = 0, m01 = 0, m11 = 0;
  for (const [s0, s1] of scores.values()) { m00 += s0 * s0; m01 += s0 * s1; m11 += s1 * s1; }
  const g = scores.size;
  const correction = (g / (g - 1)) * ((n - 1) / (n - 2));
  const bread = inv2(hess);
  const cov = mul2(mul2(bread, [[m00, m01], [m01, m11]]), bread);
  return {
    a, b, n, events: g, converged: true,
    seA: Math.sqrt(correction * cov[0][0]), seB: Math.sqrt(correction * cov[1][1]),
    predict: (p) => sigmoid(a + b * logit(p)),
  };
}
