// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Brian Hart
//
// test_golden.js — run the worker embedded in the built silverpoint.html
// against golden/Figure_Test.stl at the reference settings; the SVG must be
// byte-identical to golden/figure_js_golden.svg.
//
//   node test_golden.js ../silverpoint.html
//
const fs = require('fs');
const path = require('path');

const htmlPath = process.argv[2] || path.join(__dirname, '..', 'silverpoint.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const m = html.match(/<script id="worker-src" type="text\/plain">([\s\S]*?)<\/script>/);
if (!m) { console.error('worker source not found in ' + htmlPath); process.exit(1); }

const messages = [];
global.postMessage = (msg) => messages.push(msg);
global.TextDecoder = require('util').TextDecoder;
const handler = new Function('postMessage',
  'var onmessage = null;\n' + m[1] + '\nreturn onmessage;')(global.postMessage);

const stl = fs.readFileSync(path.join(__dirname, 'golden', 'Figure_Test.stl'));
handler({ data: { type: 'mesh',
  buffer: stl.buffer.slice(stl.byteOffset, stl.byteOffset + stl.byteLength) } });

// THE reference settings — the ones the golden file was validated against.
// (These are not the app's factory defaults; they are the frozen test vector.)
handler({ data: { type: 'run', settings: {
  pageMM: [381.0, 558.8], marginMM: 25.0,
  viewDir: [0, -1, 0], up: [0, 0, 1], orthoZoom: 1.15,
  lightDir: null, lightPos: null, lightAz: -25, lightEl: 30,
  fillStrength: 0, fillAz: 150, fillEl: 0, wrap: 0, ambient: 0.25,
  useAO: true, aoSamples: 16, aoDistFrac: 0.10,
  darknessMax: 0.80, toneGamma: 1.0,
  hatchAngleMode: 'SCREEN', normalA: [0, 0, 1], normalB: [1, 0, 0], vesselAxis: null,
  nLinesA: 250, nLinesB: 250, baseAngle: 0, crossAngle: '45',
  tLight: 0.20, tCross: 0.65, minSegFrac: 0,
  offsetFrac: 0.0015, doOcclusion: true, doSilhouette: true,
  backfaceCutoff: 0.05, maxSegments: 400000,
} } });

const err = messages.find(x => x.type === 'error');
if (err) { console.error('worker error: ' + err.message); process.exit(1); }
const result = messages.find(x => x.type === 'result');
const golden = fs.readFileSync(
  path.join(__dirname, 'golden', 'figure_js_golden.svg'), 'utf8');
const ok = result.svg === golden;
console.log('segments: ' + result.total.toLocaleString() +
  ' · byte-identical to golden: ' + ok);
process.exit(ok ? 0 : 1);
