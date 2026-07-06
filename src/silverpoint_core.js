// silverpoint_core.js — the Silverpoint Hatch algorithm, environment-free.
// ============================================================================
// v1.0.0 — line-by-line translation of silverpoint_core.py v1.1.0.
//
// READ THIS SIDE BY SIDE WITH THE PYTHON. Sections, function names, argument
// orders, and even comment placement mirror the Python file. The translation
// dictionary is tiny:
//
//     Python tuple (x,y,z)        ->  JS array [x,y,z]
//     def f(a, b):                ->  function f(a, b) {
//     list comprehension          ->  explicit loop (or .map)
//     dict                        ->  Map (preserves insertion order, same
//                                      as Python 3.7+ dicts)
//     math.sqrt / cos / sin       ->  Math.sqrt / cos / sin  (same IEEE-754
//                                      doubles -> near-identical output)
//
// The injected dependency is unchanged:
//     raycast(origin, direction, maxDist) -> hit distance (number) or null
// In Node tests we inject a small BVH; in the browser, three-mesh-bvh.
//
// Runs unmodified in Node AND the browser (no imports, no I/O — the host
// supplies mesh + raycast and receives layers + camera + SVG string).
// ============================================================================

const CROSS_DELTAS_ALL = [15.0, 45.0, 75.0, 90.0];

// ============================ tiny vector kit ===============================

function vAdd(a, b)   { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
function vSub(a, b)   { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function vScale(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
function vDot(a, b)   { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function vLen(a)      { return Math.sqrt(vDot(a, a)); }
function vLen2(a)     { return vDot(a, a); }

function vCross(a, b) {
  return [a[1] * b[2] - a[2] * b[1],
          a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0]];
}

function vNorm(a) {
  const L = vLen(a);
  if (L < 1e-12) return [0.0, 0.0, 0.0];
  return [a[0] / L, a[1] / L, a[2] / L];
}

function vLerp(a, b, t) {
  // Linear interpolation: the point fraction t of the way from a to b.
  return [a[0] + (b[0] - a[0]) * t,
          a[1] + (b[1] - a[1]) * t,
          a[2] + (b[2] - a[2]) * t];
}

function vRotateAxis(v, axis, angleRad) {
  // Rodrigues rotation of v about unit axis.
  const k = vNorm(axis);
  const c = Math.cos(angleRad), s = Math.sin(angleRad);
  const kxv = vCross(k, v);
  const kdv = vDot(k, v);
  return [v[0] * c + kxv[0] * s + k[0] * kdv * (1 - c),
          v[1] * c + kxv[1] * s + k[1] * kdv * (1 - c),
          v[2] * c + kxv[2] * s + k[2] * kdv * (1 - c)];
}

// ============================ mesh utilities ================================

function meshBounds(verts) {
  let lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const v of verts)
    for (let i = 0; i < 3; i++) {
      if (v[i] < lo[i]) lo[i] = v[i];
      if (v[i] > hi[i]) hi[i] = v[i];
    }
  const center = vScale(vAdd(lo, hi), 0.5);
  return [center, vLen(vSub(hi, lo))];
}

function vertexNormals(verts, tris) {
  // Area-weighted per-vertex normals (raw cross = 2*area*normal).
  const acc = verts.map(() => [0.0, 0.0, 0.0]);
  for (const [ia, ib, ic] of tris) {
    const fn = vCross(vSub(verts[ib], verts[ia]), vSub(verts[ic], verts[ia]));
    for (const [idx] of [[ia], [ib], [ic]]) {
      acc[idx][0] += fn[0]; acc[idx][1] += fn[1]; acc[idx][2] += fn[2];
    }
  }
  return acc.map(vNorm);
}

// ============================ dither / sampling =============================

function vanDerCorput(n, base = 2) {
  let q = 0.0, bk = 1.0 / base;
  while (n > 0) {
    q += (n % base) * bk;
    n = Math.floor(n / base);
    bk /= base;
  }
  return q;
}

// --- dither orderings: the PRICE of each line in a 32-line window ------------
// vdC is the historical default (bit-reversal). The others are selectable.
const DITHER_GOLDEN = [0.50000, 0.11803, 0.73607, 0.35410, 0.97214, 0.59017, 0.20820, 0.82624, 0.44427, 0.06231, 0.68034, 0.29837, 0.91641, 0.53444, 0.15248, 0.77051, 0.38854, 0.00658, 0.62461, 0.24265, 0.86068, 0.47871, 0.09675, 0.71478, 0.33282, 0.95085, 0.56888, 0.18692, 0.80495, 0.42299, 0.04102, 0.65905];
const DITHER_WHITE = [0.81250, 0.50000, 0.03125, 0.06250, 0.15625, 0.46875, 0.75000, 0.78125, 0.87500, 0.09375, 0.65625, 0.18750, 0.59375, 0.00000, 0.12500, 0.28125, 0.71875, 0.21875, 0.93750, 0.56250, 0.84375, 0.34375, 0.53125, 0.68750, 0.96875, 0.40625, 0.25000, 0.37500, 0.90625, 0.43750, 0.62500, 0.31250];

function priceFn(method) {
  // returns f(i32) -> price in [0,1). 'vdc' MUST match vanDerCorput exactly
  // so the default path stays byte-identical to the validated golden.
  if (method === 'golden') return (i) => DITHER_GOLDEN[i & 31];
  if (method === 'white')  return (i) => DITHER_WHITE[i & 31];
  return (i) => vanDerCorput(i & 31);
}

function cosineHemisphere(normal, k, total) {
  const n = vNorm(normal);
  const a = Math.abs(n[0]) < 0.9 ? [1.0, 0.0, 0.0] : [0.0, 1.0, 0.0];
  const t = vNorm(vSub(a, vScale(n, vDot(a, n))));
  const b = vCross(n, t);
  const u = (k + 0.5) / total;
  const r = Math.sqrt(u);
  const phi = k * 2.39996323;
  const x = r * Math.cos(phi), y = r * Math.sin(phi);
  const z = Math.sqrt(Math.max(0.0, 1.0 - u));
  return vNorm(vAdd(vAdd(vScale(t, x), vScale(b, y)), vScale(n, z)));
}

// ============================ tone ==========================================

function computeAO(verts, vnorm, raycast, samples, distFrac, bboxDiag,
                   progress = null) {
  const aoDist = distFrac * bboxDiag;
  const eps = 1e-4 * bboxDiag;
  const nVerts = verts.length;
  const ao = new Array(nVerts).fill(1.0);
  const tick = Math.max(1, Math.floor(nVerts / 20));
  for (let i = 0; i < nVerts; i++) {
    const p = verts[i], n = vnorm[i];
    const origin = vAdd(p, vScale(n, eps));
    let hits = 0;
    for (let k = 0; k < samples; k++) {
      const d = cosineHemisphere(n, k, samples);
      if (raycast(origin, d, aoDist) !== null) hits += 1;
    }
    ao[i] = 1.0 - hits / samples;
    if (progress && (i + 1) % tick === 0) progress(i + 1, nVerts);
  }
  return ao;
}

function toneFromAO(ao, vnorm, LKey, LFill, fillStrength, wrap,
                    ambient, gamma, darknessMax, useAO) {
  const Lk = vNorm(LKey);
  const Lf = LFill !== null ? vNorm(LFill) : null;
  const invW = 1.0 / (1.0 + wrap);

  function shade(n, L) {
    let d = -vDot(n, L);
    if (wrap > 0.0) d = (d + wrap) * invW;
    return d > 0.0 ? d : 0.0;
  }

  const dark = new Array(vnorm.length).fill(0.0);
  for (let i = 0; i < vnorm.length; i++) {
    const n = vnorm[i];
    let diff = shade(n, Lk);
    if (Lf !== null) {
      diff += fillStrength * shade(n, Lf);
      if (diff > 1.0) diff = 1.0;
    }
    const a = useAO ? ao[i] : 1.0;
    let lum = a * (ambient + (1.0 - ambient) * diff);
    lum = lum < 0.0 ? 0.0 : (lum > 1.0 ? 1.0 : lum);
    let d = 1.0 - lum;
    if (gamma !== 1.0) d = Math.pow(d, gamma);
    dark[i] = d < darknessMax ? d : darknessMax;
  }
  return dark;
}

// ============================ lights ========================================

function lightFromAngles(azDeg, elDeg, right, trueup, fwd) {
  let v = vScale(fwd, -1.0);
  v = vRotateAxis(v, right, elDeg * Math.PI / 180.0);
  v = vRotateAxis(v, trueup, azDeg * Math.PI / 180.0);
  return vScale(vNorm(v), -1.0);
}

function lightFromPosition(lightPos, center) {
  const v = vSub(center, lightPos);
  if (vLen2(v) < 1e-18) return null;
  return vNorm(v);
}

// ============================ camera / projection ===========================

function makeCamera(center, bboxDiag, viewDir, up, orthoZoom, pageMM) {
  const view = vNorm(viewDir);
  const upv = vNorm(up);
  const pos = vAdd(center, vScale(view, bboxDiag * 2.0));
  const fwd = vNorm(vSub(center, pos));
  const right = vNorm(vCross(fwd, upv));
  const trueup = vNorm(vCross(right, fwd));
  const [W, H] = pageMM;
  const scale = bboxDiag * orthoZoom;
  let frameW, frameH;
  if (W >= H) { frameW = scale; frameH = scale * H / W; }
  else        { frameW = scale * W / H; frameH = scale; }
  return { pos, fwd, right, up: trueup, frameW, frameH };
}

function projectMM(cam, pageMM, marginMM, p) {
  const [W, H] = pageMM;
  const m = marginMM;
  const iw = W - 2 * m, ih = H - 2 * m;
  const rel = vSub(p, cam.pos);
  const x = vDot(rel, cam.right);
  const y = vDot(rel, cam.up);
  const u = x / cam.frameW + 0.5;
  const v = y / cam.frameH + 0.5;
  return [m + u * iw, m + (1.0 - v) * ih];
}

function screenNormal(thetaDeg, right, trueup) {
  const a = (thetaDeg - 90.0) * Math.PI / 180.0;
  return vNorm(vAdd(vScale(right, Math.cos(a)), vScale(trueup, Math.sin(a))));
}

// ============================ slicing =======================================

function sliceFamily(verts, tris, dark, normal, nLines, crossPhase,
                     camFwd, raycast, bboxDiag, offsetFrac, tLight,
                     doOcclusion, backfaceCutoff = 0.05,
                     price = vanDerCorput) {
  const nrm = vNorm(normal);
  const proj = verts.map(v => vDot(v, nrm));
  let cmin = Infinity, cmax = -Infinity;
  for (const p of proj) { if (p < cmin) cmin = p; if (p > cmax) cmax = p; }
  const spacing = (cmax - cmin) / Math.max(1, nLines);
  if (spacing <= 0) return [];
  const offset = offsetFrac * bboxDiag;
  const eps = 1e-4 * bboxDiag;
  const planeC = [];
  for (let k = 0; k < nLines; k++) planeC.push(cmin + (k + 0.5) * spacing);
  const negFwd = vScale(camFwd, -1.0);
  const segs = [];
  for (const [ia, ib, ic] of tris) {
    const va = verts[ia], vb = verts[ib], vc = verts[ic];
    const da = proj[ia], db = proj[ib], dc = proj[ic];
    let lo = da < db ? da : db; lo = lo < dc ? lo : dc;
    let hi = da > db ? da : db; hi = hi > dc ? hi : dc;
    let fn = vCross(vSub(vb, va), vSub(vc, va));
    if (vLen2(fn) === 0.0) continue;
    fn = vNorm(fn);
    if (vDot(fn, camFwd) >= backfaceCutoff) continue;      // back-facing
    const td = (dark[ia] + dark[ib] + dark[ic]) / 3.0;
    if (td <= tLight) continue;
    const k0 = Math.max(0, Math.ceil((lo - cmin) / spacing - 0.5));
    const k1 = Math.min(nLines - 1, Math.floor((hi - cmin) / spacing - 0.5));
    for (let k = k0; k <= k1; k++) {
      if (td < price((k + crossPhase) & 31)) continue;
      const c = planeC[k];
      const sa = da - c, sb = db - c, sc = dc - c;
      const pts = [];
      const edges = [[va, sa, vb, sb], [vb, sb, vc, sc], [vc, sc, va, sa]];
      for (const [p0, s0, p1, s1] of edges) {
        if ((s0 > 0) !== (s1 > 0)) {
          const t = s0 / (s0 - s1);
          pts.push(vLerp(p0, p1, t));
        }
      }
      if (pts.length !== 2) continue;
      const a = vAdd(pts[0], vScale(fn, offset));
      const b = vAdd(pts[1], vScale(fn, offset));
      if (doOcclusion) {
        const mid = vScale(vAdd(a, b), 0.5);
        const dist = raycast(vAdd(mid, vScale(fn, eps)), negFwd, bboxDiag * 4.0);
        if (dist !== null && dist > eps * 4) continue;
      }
      segs.push([a, b]);
    }
  }
  return segs;
}

function filterShort(segs, minLen) {
  if (minLen <= 0.0) return segs;
  const ml2 = minLen * minLen;
  return segs.filter(([a, b]) => vLen2(vSub(b, a)) >= ml2);
}

function silhouetteSegments(verts, tris, camFwd) {
  // Occluding contour: edges shared by one front and one back face.
  // Map key = packed edge (i<j): i * nVerts + j  (safe: 22k^2 << 2^53).
  const N = verts.length;
  const edgeFace = new Map();
  for (const tri of tris) {
    const va = verts[tri[0]], vb = verts[tri[1]], vc = verts[tri[2]];
    const f = vDot(vCross(vSub(vb, va), vSub(vc, va)), camFwd) < 0.0;
    const es = [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]]];
    for (const [e0, e1] of es) {
      const key = e0 < e1 ? e0 * N + e1 : e1 * N + e0;
      const arr = edgeFace.get(key);
      if (arr === undefined) edgeFace.set(key, [f]);
      else arr.push(f);
    }
  }
  const out = [];
  for (const [key, fs] of edgeFace) {
    if (fs.length === 2 && fs[0] !== fs[1]) {
      const i = Math.floor(key / N), j = key % N;
      out.push([verts[i], verts[j]]);
    }
  }
  return out;
}

// ============================ family setup ==================================

function hatchFamilies(baseAngle, crossAngle, tLight, tCross, darknessMax,
                       right, trueup, mode = 'SCREEN',
                       normalA = [0.0, 0.0, 1.0], normalB = [1.0, 0.0, 0.0],
                       vesselAxis = null, viewDir = null,
                       normalC = null, tDeep = 0.75) {
  if (vesselAxis !== null) {
    const ax = vNorm(vesselAxis);
    const cross = vNorm(vCross(ax, viewDir));
    return [[["A", ax, tLight, 0]], [["B", cross, tCross, 16]]];
  }
  if (mode === 'WORLD') {
    const fams = [["B", vNorm(normalB), tCross, 16]];
    // Optional third family: enters only where tone exceeds tDeep — the
    // deepest zones. vdC phase 8 sits between A's 0 and B's 16 so the three
    // dither sequences interleave instead of stacking.
    if (normalC !== null && normalC !== undefined)
      fams.push(["C", vNorm(normalC), tDeep, 8]);
    return [[["A", vNorm(normalA), tLight, 0]], fams];
  }
  const A = [["A", screenNormal(baseAngle, right, trueup), tLight, 0]];
  let deltas;
  if (crossAngle === 'NONE') deltas = [];
  else if (crossAngle === 'ALL') deltas = CROSS_DELTAS_ALL;
  else deltas = [parseFloat(crossAngle)];
  const span = Math.max(0.0, darknessMax - tCross);
  const cross = [];
  for (let i = 0; i < deltas.length; i++) {
    const d = deltas[i];
    const thr = deltas.length > 1
      ? tCross + span * 0.6 * (i / deltas.length) : tCross;
    const phase = (8 * (i + 1)) & 31;
    cross.push([`B${Math.round(d)}`,
                screenNormal(baseAngle + d, right, trueup), thr, phase]);
  }
  return [A, cross];
}

// ============================ pipeline (one call) ===========================

const DEFAULTS = {
  // page / view
  pageMM: [381.0, 558.8], marginMM: 25.0,
  viewDir: [0.0, -1.0, 0.0], up: [0.0, 0.0, 1.0], orthoZoom: 1.15,
  // light — priority: lightDir > lightPos > az/el dials
  lightDir: null, lightPos: null,
  lightAz: -25.0, lightEl: 30.0,
  fillStrength: 0.0, fillAz: 150.0, fillEl: 0.0,
  wrap: 0.0, ambient: 0.25,
  // tone
  useAO: true, aoSamples: 24, aoDistFrac: 0.20,
  darknessMax: 0.80, toneGamma: 1.5,
  // hatch
  hatchAngleMode: 'SCREEN',
  normalA: [0.0, 0.0, 1.0], normalB: [1.0, 0.0, 0.0], vesselAxis: null,
  normalC: null, tDeep: 0.75,
  ditherMethod: 'vdc', penMM: 0.30,
  nLinesA: 500, nLinesB: 500,
  baseAngle: 45.0, crossAngle: '90',
  tLight: 0.20, tCross: 0.65, minSegFrac: 0.0,
  // visibility
  offsetFrac: 0.0015, doOcclusion: true, doSilhouette: true,
  backfaceCutoff: 0.05,
};

function generate(verts, tris, raycast, settings, ao = null, vnorm = null,
                  progress = null) {
  const s = Object.assign({}, DEFAULTS, settings);
  const [center, diag] = meshBounds(verts);
  if (vnorm === null) vnorm = vertexNormals(verts, tris);
  if (ao === null) {
    ao = s.useAO
      ? computeAO(verts, vnorm, raycast, s.aoSamples, s.aoDistFrac, diag, progress)
      : new Array(verts.length).fill(1.0);
  }

  const cam = makeCamera(center, diag, s.viewDir, s.up, s.orthoZoom, s.pageMM);
  const fwd = cam.fwd, right = cam.right, trueup = cam.up;

  let LKey;
  if (s.lightDir !== null) LKey = vNorm(s.lightDir);
  else if (s.lightPos !== null) {
    LKey = lightFromPosition(s.lightPos, center)
        || lightFromAngles(s.lightAz, s.lightEl, right, trueup, fwd);
  } else LKey = lightFromAngles(s.lightAz, s.lightEl, right, trueup, fwd);
  const LFill = s.fillStrength > 0.0
    ? lightFromAngles(s.fillAz, s.fillEl, right, trueup, fwd) : null;

  const dark = toneFromAO(ao, vnorm, LKey, LFill, s.fillStrength, s.wrap,
                          s.ambient, s.toneGamma, s.darknessMax, s.useAO);

  const [AFams, crossFams] = hatchFamilies(
    s.baseAngle, s.crossAngle, s.tLight, s.tCross, s.darknessMax,
    right, trueup, s.hatchAngleMode, s.normalA, s.normalB,
    s.vesselAxis, s.viewDir,
    s.normalC === undefined ? null : s.normalC,
    s.tDeep === undefined ? 0.75 : s.tDeep);

  const minLen = s.minSegFrac * diag;
  const layers = [];
  const price = priceFn(s.ditherMethod);
  for (const [lbl, nrm, thr, phase] of AFams) {
    const segs = sliceFamily(verts, tris, dark, nrm, s.nLinesA, phase,
                             fwd, raycast, diag, s.offsetFrac, thr,
                             s.doOcclusion, s.backfaceCutoff, price);
    layers.push([lbl, filterShort(segs, minLen)]);
  }
  for (const [lbl, nrm, thr, phase] of crossFams) {
    const darkC = dark.map(d => (d >= thr ? d : 0.0));
    const segs = sliceFamily(verts, tris, darkC, nrm, s.nLinesB, phase,
                             fwd, raycast, diag, s.offsetFrac, thr,
                             s.doOcclusion, s.backfaceCutoff, price);
    layers.push([lbl, filterShort(segs, minLen)]);
  }
  if (s.doSilhouette)
    layers.push(["silhouette", silhouetteSegments(verts, tris, fwd)]);
  return [layers, cam];
}

// ============================ SVG output ====================================

function svgString(layers, cam, pageMM, marginMM, penMM = 0.30) {
  const [W, H] = pageMM;
  const out = [`<svg xmlns="http://www.w3.org/2000/svg" ` +
    `xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" ` +
    `width="${W}mm" height="${H}mm" viewBox="0 0 ${W} ${H}">`];
  // hatch strokes render at the pen width; silhouette stays 1.5x heavier,
  // preserving the historical 0.30 / 0.45 ratio. Default penMM=0.30 keeps
  // the golden output byte-identical.
  const hatchW = +penMM.toFixed(4);
  const silhW = +(penMM * 1.5).toFixed(4);
  const styleFor = name =>
    name === "silhouette" ? ["#26262b", silhW] : ["#3a3a40", hatchW];
  for (const [name, segs] of layers) {
    if (!segs.length) continue;
    const [col, sw] = styleFor(name);
    out.push(`<g inkscape:groupmode="layer" inkscape:label="${name}" ` +
      `fill="none" stroke="${col}" stroke-width="${sw}" ` +
      `stroke-linecap="round">`);
    for (const [a, b] of segs) {
      const [ax, ay] = projectMM(cam, pageMM, marginMM, a);
      const [bx, by] = projectMM(cam, pageMM, marginMM, b);
      out.push(`<line x1="${ax.toFixed(3)}" y1="${ay.toFixed(3)}" ` +
        `x2="${bx.toFixed(3)}" y2="${by.toFixed(3)}"/>`);
    }
    out.push('</g>');
  }
  out.push('</svg>');
  return out.join('\n');
}

// Node export / browser global (works in both without a bundler)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    vAdd, vSub, vScale, vDot, vCross, vNorm, vLerp, vLen, vLen2, vRotateAxis,
    meshBounds, vertexNormals, vanDerCorput, cosineHemisphere,
    computeAO, toneFromAO, lightFromAngles, lightFromPosition,
    makeCamera, projectMM, screenNormal, sliceFamily, filterShort,
    silhouetteSegments, hatchFamilies, generate, svgString, DEFAULTS,
  };
}
