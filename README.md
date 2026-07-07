# Silverpoint Hatch — Uneditioned

Turn a 3D model into a pen-plotter drawing. Silverpoint Hatch slices an STL
with a family of parallel planes, tones each line by how the surface catches
the light and how deeply it sits in its own crevices, then thins the lines
with a dither so lighter areas simply have fewer of them. The result is a
layered SVG ready for a plotter.

Everything runs in your browser. **Your model never leaves your machine** —
there is no upload, no server, no account. The drawings you make are yours.

By Brian Hart · [thebrianhart.com](https://thebrianhart.com) ·
[uneditioned.com](https://uneditioned.com)
License: AGPL-3.0-only (see `LICENSE`).

---

## Quick start

1. Open the tool (the deployed page, or `index.html` from a local copy).
2. **Drop an STL** onto the panel — or click it to browse.
3. It draws immediately at sensible defaults.
4. Adjust controls; the drawing re-renders as you go.
5. **Download SVG** when you like what you see.

The first draw computes ambient occlusion (a second or two on a detailed
model); after that, most changes redraw in a fraction of a second because
that occlusion is cached.

---

## The viewport

The big area on the right is a sheet of paper on a wall — the drawing sits on
it at true page proportions, so what you see is what plots.

**Drag to rotate.** Grab the sheet and drag; the model turns and redraws when
you let go. On light models it re-draws *continuously* as you drag (the whole
crosshatch, live); on heavier ones it shows a fast wireframe while you drag and
draws the finished lines on release. Either way, the page border and margin
guide stay visible so you can see how the model will land on the sheet.

**Angle pills (top-right of the viewport).** These pick what dragging does:

- **rotate** — orbit the camera (the default).
- **plane A / plane B / plane C** — in *Surface* hatching mode, lock the model
  and instead aim a slicing plane. A single contour line sweeps over the
  drawing as you drag so you can aim the hatching against the finished image;
  release to redraw. (plane C appears only when Plane C is enabled.)

**Angle strip + spin (bottom).** After a draw settles, the tool quietly
pre-renders the model from eight angles, 45° apart. Filled dots are instant to
open — click one to jump to that view. The **▶** button spins through them; on
light models it spins the real drawing continuously, on heavier ones it flips
through the eight cached angles.

---

## Controls

Controls that don't apply right now are greyed out rather than hidden, so you
can always see the whole panel.

### Page
- **Size** — paper size. Six presets in inches, or **Custom (in)** to type
  width × height.
- **Margin (mm)** — blank border kept clear of ink.
- **Zoom** — how large the model sits on the page. 1 fits it with a little
  air; 2 is twice as close; below 1 pulls back.

### View
- **Direction** — a named view (Front, Back, Right, Left, Top, Bottom) or a
  **Custom vector**. Dragging the viewport writes a custom vector here.

### Light
- **Key source** —
  - **Cube corner (world)** — the key light hangs at one corner of a cube
    around the model. Because it's fixed in the world, the model rotates *past*
    it — the shadow side migrates as you turn the turntable, like a real object
    under a real lamp. Pick the corner with **Corner** (Front/Back ×
    Top/Bottom × Left/Right).
  - **Camera-relative dials** — the light rides with the camera. **Key left /
    right** and **Key up / down** aim it; every view is lit the same way.
- **Ambient** — base fill so shadows never go fully black.

### Tone
- **Ambient occlusion** — darkens crevices and contact areas the way real
  drawing does. The single biggest contributor to a solid, dimensional look.
- **AO samples** — how many rays measure each point. More = smoother shading,
  but cost grows linearly (16 is ~4× the work of 4).
- **AO distance** — how far each ray looks for cover, as a fraction of model
  size. Small = only tight crevices darken; large = broad, soft shading.
- **Darkness cap** — the darkest any area is allowed to get.
- **Tone gamma** — bends the light-to-dark curve. Above 1 lifts midtones
  brighter; below 1 deepens them.

### Hatching
- **Angle mode** —
  - **Surface** — lines follow planes cutting *through the model*, so they
    cling to the form and travel with it when you rotate. Aim them with the
    **Plane A / B / C** vectors (each is the normal of its slicing planes;
    `(0,0,1)` gives level bands, `(1,0,0)` gives vertical bands). The viewport
    plane pills let you aim these by dragging.
  - **Screen angle** — lines are ruled at a fixed angle *on the page* and stay
    put when the model turns, like halftone screen angles. Set with **Base
    angle** and **Cross angle**.
- **Plane C (deep)** — an optional third hatch family that only enters the
  darkest zones (above the **Deep cutoff** tone). Classic crosshatch buildup:
  light stays bare, midtones get one family, shadows a second, the deepest
  crevices a third.
- **Lines A / Lines B** — how many hatch lines each family may lay down at full
  darkness. Roughly, plot time scales with these — halving them ~halves the
  time.
- **Highlight cutoff** — tone below this stays blank paper.
- **Crosshatch cutoff** — tone above this earns the crossing (second) family.
- **Dither** — the order in which lines drop out as tone lightens. Same tone,
  same line count — only the *pattern* of which lines survive differs:
  - **van der Corput** — smoothest, most even. Best default for stills.
  - **Golden ratio** — just as even but aperiodic; best when you animate
    (turntable/spin) or when van der Corput's regularity reads too mechanical.
  - **White noise** — random; grainier, hand-nervous. A texture tool.
- **Pen width (mm)** — the stroke width written into the SVG. Set it to your
  actual pen so the preview and plot match. Silhouette lines are drawn 1.5× as
  wide.

### Visibility
- **Hidden-line removal** — hide lines the far side of the model would block.
- **Silhouette** — draw the model's outline.
- **Surface offset** — lifts lines a hair off the surface so occlusion tests
  don't clip them. Rarely needs changing.
- **Backface cutoff** — how aggressively lines sneaking around the silhouette
  edge are culled. Lower (or negative) trims more.
- **Min seg length** — drop hatch fragments shorter than this.
- **Max segments** — a safety cap; if a drawing would exceed it you'll be told
  to lower the line counts or raise the cap rather than lock up the browser.

---

## Exporting

Two download buttons:

- **SVG raw** — every hatch line as a separate stroke, exactly as drawn.
- **SVG chained** — touching lines joined into continuous paths (a lossless
  line-merge). Same ink, fewer pen-lifts. Good to feed a plotter directly.
  Note: silverpoint drawings are intentionally "dashy" (that's the dither), so
  the reduction is modest — the bigger plot-time win is usually path *sorting*
  in your plotter software or vpype.

**Plot tag in margin** — an optional checkbox that draws a tiny single-stroke
`uneditioned.com` in the bottom-right margin. It plots as real ink (survives
any downstream processing). Off by default. Every exported SVG also carries an
invisible comment crediting the tool — no ink, just there in the file's source.

Both exports work with either flavor and with the tag on or off.

---

## Getting good results

- **Clean your mesh first.** Floating shrapnel, duplicate faces, non-manifold
  edges, and interpenetrating shells make ambient occlusion and hidden-line
  removal misbehave — you'll see mottled patches. A watertight, single-shell,
  consistently-wound mesh draws cleanly. (Weld vertices, delete loose geometry,
  recalculate normals.)
- **Let AO carry the form.** It's the difference between a flat pattern and a
  drawing that reads as solid.
- **Reach for Golden-ratio dither when animating.** Its aperiodic pattern
  avoids the faint moiré that periodic dithering can show across a turntable.
- **Match Pen width to your actual pen** so the on-screen density equals the
  plotted density.
- **Watch plot time in the line counts**, not the segment count — Z-lift
  travel dominates dense plots, so fewer, longer lines beat many short ones.

---

## Running / deploying (for the repo)

The whole app is the single self-contained file `index.html`
(a.k.a. `silverpoint.html`). To publish it, put that file — plus `LICENSE` —
on any static host. No server, no build step on the host, no dependencies, no
network calls.

The `src/` folder holds the maintainable project:

    src/
      silverpoint_shell_template.html   the app (UI, styles, interactions)
      silverpoint_core.js               the drawing engine (validated)
      silverpoint_core.py               reference implementation (same math)
      build.py                          splice core into template -> ../index.html,
                                        then run the golden test
      test_golden.js                    byte-identity check of the built file
      golden/                           the test model + its expected output

To rebuild after an edit:

    cd src
    python3 build.py

The build refuses to bless output that isn't byte-identical to the golden
reference (unless you changed the engine on purpose and regenerated the
golden). This is what keeps the JavaScript engine provably matched to the
Python reference.

All visual styling lives in the `:root` token block at the top of the
template's stylesheet — restyle there. 
