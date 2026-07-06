#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Brian Hart
#
# build.py — assemble and validate silverpoint.html
#
#   cd src && python3 build.py
#
# What it does:
#   1. Splices silverpoint_core.js VERBATIM into silverpoint_shell_template.html
#      at the %%CORE%% token. The core is never hand-edited inside the shell;
#      it is always injected from the canonical file, which is what guarantees
#      the shipped engine stays byte-identical to the validated one.
#   2. Writes ../silverpoint.html (the deployable file).
#   3. If node is available, runs the golden test: the embedded worker must
#      reproduce src/golden/figure_js_golden.svg BYTE-IDENTICALLY from
#      src/golden/Figure_Test.stl at the reference settings. If this fails,
#      DO NOT DEPLOY — the engine changed.
#
# Editing guide:
#   * UI / layout / styling / features  -> edit silverpoint_shell_template.html
#   * The drawing algorithm             -> edit silverpoint_core.js
#     (and regenerate the golden file deliberately if the change is intended
#      to alter output: run build, eyeball the drawing, then
#      cp of the new output over golden — a conscious act, never automatic)

import pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent / "silverpoint.html"

core = (HERE / "silverpoint_core.js").read_text()
cut = core.find("// Node export / browser global")
if cut > 0:                       # strip the Node-only export block if present
    core = core[:cut].rstrip() + "\n"

tmpl = (HERE / "silverpoint_shell_template.html").read_text()
assert "%%CORE%%" in tmpl, "template is missing the %%CORE%% token"
OUT.write_text(tmpl.replace("%%CORE%%", core))
print(f"built  {OUT}  ({OUT.stat().st_size:,} bytes)")

node = shutil.which("node")
if not node:
    print("node not found — skipping golden test. Install node and rerun to validate.")
    sys.exit(0)

r = subprocess.run([node, str(HERE / "test_golden.js"), str(OUT)],
                   capture_output=True, text=True)
print(r.stdout.strip())
if r.returncode != 0:
    print(r.stderr.strip())
    print("\nGOLDEN TEST FAILED — the engine's output changed. Do not deploy\n"
          "unless this was intentional (then regenerate the golden file).")
    sys.exit(1)
print("golden test passed — safe to deploy.")
