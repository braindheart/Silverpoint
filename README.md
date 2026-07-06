# Silverpoint Hatch — Uneditioned

Turn a 3D model (STL) into a pen-plotter drawing: tonal crosshatch built by
slicing the mesh with parallel planes, toned by ambient occlusion and light,
thinned by van der Corput dithering. Runs entirely in the browser — models
never leave the visitor's machine.

Copyright (C) 2026 Brian Hart · thebrianhart.com · uneditioned.com
License: AGPL-3.0-only (see LICENSE). Drawings made with the tool belong to
whoever makes them. The name and branding are not covered by the license.

## Deploy

`silverpoint.html` + `LICENSE` are the entire deployment. Upload both to any
static host. Rename the HTML to `index.html` inside a folder for a clean URL.
No server code, no build on the host, no external requests.

## Layout

    silverpoint.html                  <- the deployable, generated — do not edit
    LICENSE                           <- canonical AGPL-3.0 text, deploy alongside
    src/
      silverpoint_shell_template.html <- the app: UI, styles, orbit, turntable,
                                         live mode, exports. EDIT THIS for any
                                         shell change. Contains a %%CORE%% token.
      silverpoint_core.js             <- the drawing engine (validated). EDIT
                                         ONLY for algorithm changes.
      silverpoint_core.py             <- reference implementation (same math),
                                         used for cross-language validation.
      build.py                        <- splice core into template -> ../silverpoint.html,
                                         then run the golden test.
      test_golden.js                  <- byte-identity check of the built file.
      golden/
        Figure_Test.stl               <- test model
        figure_js_golden.svg          <- expected output at reference settings

## Build & validate

    cd src
    python3 build.py        # needs python3; node for the test step

The golden test demands BYTE-IDENTICAL output. If it fails after a shell edit,
something leaked into the engine — stop and diff. If you changed the engine on
purpose, verify the new drawing by eye, then consciously refresh the golden:
build, run the app or test harness, and copy the new output over
`golden/figure_js_golden.svg`.

## Design tokens

All colors/typography live in the `:root` block at the top of the template's
stylesheet (muted CMYK on light). Restyle there; nothing below the tokens is
load-bearing.

## Notes kept for future work

* Chained export = linemerge at 0.01 mm tolerance (`CHAIN_TOL`), lossless
  (ink-conservation asserted in development tests). Ratios are modest by
  design: van der Corput dithering makes intrinsically dashy drawings.
* Next lever for plot time is path SORTING (nearest-neighbour with reversal,
  same greedy as gcode_reorder.py) — not yet implemented in the export.
* Live mode threshold `LIVE_MS = 120` ms; turntable idle 1200 ms; wireframe
  edge budget `MAXE = 8000` — all constants near their features.
