# silverpoint_core.py — the Silverpoint Hatch algorithm, environment-free
# =============================================================================
# v1.0.0 — extracted from silverpoint_hatch.py v2.5.0
#
# THE CONTRACT
#   This file imports only `math`. No bpy, no mathutils, no numpy. Every
#   function is a pure function: same inputs -> same outputs, no hidden state.
#   That is what makes it runnable in three places without modification:
#
#     * Blender addon  -> adapter wraps BVHTree.ray_cast and mathutils Vectors
#     * plain Python   -> test harness supplies a numpy ray-caster
#     * JavaScript     -> line-by-line translation; three-mesh-bvh supplies rays
#
#   The ONE service the algorithm needs from its host is ray casting, so it is
#   INJECTED as a callable rather than imported:
#
#       raycast(origin, direction, max_dist) -> hit distance (float) or None
#
#   origin/direction are 3-tuples. That signature is the entire boundary
#   between "algorithm" and "environment".
#
# DATA CONVENTIONS (chosen to translate 1:1 into JS typed arrays later)
#   point / vector : 3-tuple of floats            (x, y, z)
#   verts          : list of points               [(x,y,z), ...]
#   tris           : list of index triples        [(ia,ib,ic), ...]
#   segment        : (point_a, point_b)
#   layer          : (label, [segments])
#   darkness       : list of floats in [0..1], parallel to verts
#
# Behaviour is a faithful port of v2.5.0, including:
#   * van der Corput tone-to-density gating with per-family phase
#   * highlight cutoff (t_light) and per-family thresholds
#   * exposed backface_cutoff (default 0.05 = historical behaviour)
#   * hidden-line removal via one midpoint ray toward the camera
#   * key light from angles OR from a world position / aim direction
#   * wrap / fill / ambient / gamma / darkness_max tone shaping
#   * orthographic camera + page-mm projection matching the Blender output
#     (render frame fitted to page aspect, AUTO sensor fit semantics)
# =============================================================================

import math

CROSS_DELTAS_ALL = (15.0, 45.0, 75.0, 90.0)


# ============================ tiny vector kit ================================
# Plain tuples + free functions. In JS these become [x,y,z] arrays + the same
# functions; nothing here relies on Python magic.

def v_add(a, b):    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def v_sub(a, b):    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_scale(a, s):  return (a[0] * s, a[1] * s, a[2] * s)
def v_dot(a, b):    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_len(a):       return math.sqrt(v_dot(a, a))
def v_len2(a):      return v_dot(a, a)

def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])

def v_norm(a):
    L = v_len(a)
    if L < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / L, a[1] / L, a[2] / L)

def v_lerp(a, b, t):
    """Linear interpolation: the point fraction t of the way from a to b."""
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)

def v_rotate_axis(v, axis, angle_rad):
    """Rodrigues rotation of v about unit axis. (Replaces Matrix.Rotation.)"""
    k = v_norm(axis)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    kxv = v_cross(k, v)
    kdv = v_dot(k, v)
    return (v[0] * c + kxv[0] * s + k[0] * kdv * (1 - c),
            v[1] * c + kxv[1] * s + k[1] * kdv * (1 - c),
            v[2] * c + kxv[2] * s + k[2] * kdv * (1 - c))


# ============================ mesh utilities =================================

def mesh_bounds(verts):
    """(center, bbox_diagonal) of a vertex list."""
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
    lo = (min(xs), min(ys), min(zs)); hi = (max(xs), max(ys), max(zs))
    center = v_scale(v_add(lo, hi), 0.5)
    return center, v_len(v_sub(hi, lo))


def vertex_normals(verts, tris):
    """Area-weighted per-vertex normals (the un-normalized cross product of a
    triangle IS twice its area times its normal, so summing raw crosses gives
    area weighting for free)."""
    acc = [(0.0, 0.0, 0.0)] * len(verts)
    for (ia, ib, ic) in tris:
        fn = v_cross(v_sub(verts[ib], verts[ia]), v_sub(verts[ic], verts[ia]))
        acc[ia] = v_add(acc[ia], fn)
        acc[ib] = v_add(acc[ib], fn)
        acc[ic] = v_add(acc[ic], fn)
    return [v_norm(n) for n in acc]


# ============================ dither / sampling ==============================

def van_der_corput(n, base=2):
    """Low-discrepancy value in [0,1): each successive index lands in the
    biggest remaining gap, so tone-gated line dropouts interleave evenly."""
    q, bk = 0.0, 1.0 / base
    while n > 0:
        q += (n % base) * bk
        n //= base
        bk /= base
    return q


# --- dither orderings: the PRICE of each line in a 32-line window ------------
DITHER_GOLDEN = (0.50000, 0.11803, 0.73607, 0.35410, 0.97214, 0.59017, 0.20820, 0.82624, 0.44427, 0.06231, 0.68034, 0.29837, 0.91641, 0.53444, 0.15248, 0.77051, 0.38854, 0.00658, 0.62461, 0.24265, 0.86068, 0.47871, 0.09675, 0.71478, 0.33282, 0.95085, 0.56888, 0.18692, 0.80495, 0.42299, 0.04102, 0.65905)
DITHER_WHITE = (0.81250, 0.50000, 0.03125, 0.06250, 0.15625, 0.46875, 0.75000, 0.78125, 0.87500, 0.09375, 0.65625, 0.18750, 0.59375, 0.00000, 0.12500, 0.28125, 0.71875, 0.21875, 0.93750, 0.56250, 0.84375, 0.34375, 0.53125, 0.68750, 0.96875, 0.40625, 0.25000, 0.37500, 0.90625, 0.43750, 0.62500, 0.31250)


def price_fn(method):
    """f(i32)->price. 'vdc' matches van_der_corput exactly (golden default)."""
    if method == 'golden':
        return lambda i: DITHER_GOLDEN[i & 31]
    if method == 'white':
        return lambda i: DITHER_WHITE[i & 31]
    return lambda i: van_der_corput(i & 31)


def cosine_hemisphere(normal, k, total):
    """k-th of `total` deterministic cosine-weighted directions around normal
    (golden-angle spiral). Used for the AO dome."""
    n = v_norm(normal)
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    t = v_norm(v_sub(a, v_scale(n, v_dot(a, n))))
    b = v_cross(n, t)
    u = (k + 0.5) / total
    r = math.sqrt(u)
    phi = k * 2.39996323
    x, y = r * math.cos(phi), r * math.sin(phi)
    z = math.sqrt(max(0.0, 1.0 - u))
    return v_norm(v_add(v_add(v_scale(t, x), v_scale(b, y)), v_scale(n, z)))


# ============================ tone ===========================================

def compute_ao(verts, vnorm, raycast, samples, dist_frac, bbox_diag,
               progress=None):
    """Per-vertex ambient occlusion in [0,1] (1 = open, 0 = buried).
    `raycast(origin, dir, max_dist) -> hit distance or None` is injected.
    `progress(done, total)` is an optional callback (UI progress bars)."""
    ao_dist = dist_frac * bbox_diag
    eps = 1e-4 * bbox_diag
    n_verts = len(verts)
    ao = [1.0] * n_verts
    for i in range(n_verts):
        p, n = verts[i], vnorm[i]
        origin = v_add(p, v_scale(n, eps))
        hits = 0
        for k in range(samples):
            d = cosine_hemisphere(n, k, samples)
            if raycast(origin, d, ao_dist) is not None:
                hits += 1
        ao[i] = 1.0 - hits / samples
        if progress and (i + 1) % max(1, n_verts // 20) == 0:
            progress(i + 1, n_verts)
    return ao


def tone_from_ao(ao, vnorm, L_key, L_fill, fill_strength, wrap,
                 ambient, gamma, darkness_max, use_ao):
    """AO x diffuse -> per-vertex darkness. Identical math to the addon:
    Diffuse = key Lambert (+ optional fill); wrap softens the terminator."""
    Lk = v_norm(L_key)
    Lf = v_norm(L_fill) if L_fill is not None else None
    inv_w = 1.0 / (1.0 + wrap)

    def shade(n, L):
        d = -v_dot(n, L)                       # n.dot(-L)
        if wrap > 0.0:
            d = (d + wrap) * inv_w
        return d if d > 0.0 else 0.0

    dark = [0.0] * len(vnorm)
    for i, n in enumerate(vnorm):
        diff = shade(n, Lk)
        if Lf is not None:
            diff += fill_strength * shade(n, Lf)
            if diff > 1.0:
                diff = 1.0
        a = ao[i] if use_ao else 1.0
        lum = a * (ambient + (1.0 - ambient) * diff)
        lum = 0.0 if lum < 0.0 else (1.0 if lum > 1.0 else lum)
        d = 1.0 - lum
        if gamma != 1.0:
            d = d ** gamma
        dark[i] = d if d < darkness_max else darkness_max
    return dark


# ============================ lights =========================================

def light_from_angles(az_deg, el_deg, right, trueup, fwd):
    """Camera-relative key/fill dials -> world travel direction L.
    Start at the camera direction, pitch about `right`, yaw about `trueup`."""
    v = v_scale(fwd, -1.0)
    v = v_rotate_axis(v, right, math.radians(el_deg))
    v = v_rotate_axis(v, trueup, math.radians(az_deg))
    return v_scale(v_norm(v), -1.0)


def light_from_position(light_pos, center):
    """World-space lamp position -> travel direction (lamp toward model).
    Returns None if degenerate (lamp at the center)."""
    v = v_sub(center, light_pos)
    if v_len2(v) < 1e-18:
        return None
    return v_norm(v)


# ============================ camera / projection ============================

def make_camera(center, bbox_diag, view_dir, up, ortho_zoom, page_mm):
    """Orthographic camera looking at `center` from direction `view_dir`.
    Returns a plain dict — no scene objects. Frame fitting reproduces the
    addon's behaviour (ortho_scale spans the LARGER page dimension, matching
    Blender's AUTO sensor fit with render resolution set to the page aspect)."""
    view = v_norm(view_dir)
    upv = v_norm(up)
    pos = v_add(center, v_scale(view, bbox_diag * 2.0))
    fwd = v_norm(v_sub(center, pos))
    right = v_norm(v_cross(fwd, upv))
    trueup = v_norm(v_cross(right, fwd))
    W, H = page_mm
    scale = bbox_diag * ortho_zoom            # world units across the big axis
    if W >= H:
        frame_w, frame_h = scale, scale * H / W
    else:
        frame_w, frame_h = scale * W / H, scale
    return {"pos": pos, "fwd": fwd, "right": right, "up": trueup,
            "frame_w": frame_w, "frame_h": frame_h}


def project_mm(cam, page_mm, margin_mm, p):
    """World point -> (x, y) in page millimetres, y down (SVG convention).
    Replaces bpy's world_to_camera_view for the ortho case: express the point
    in the camera's basis, normalise by the frame size, map into the margins."""
    W, H = page_mm
    m = margin_mm
    iw, ih = W - 2 * m, H - 2 * m
    rel = v_sub(p, cam["pos"])
    x = v_dot(rel, cam["right"])
    y = v_dot(rel, cam["up"])
    u = x / cam["frame_w"] + 0.5              # 0..1 across the frame
    v = y / cam["frame_h"] + 0.5
    return (m + u * iw, m + (1.0 - v) * ih)


def screen_normal(theta_deg, right, trueup):
    """Slicing-plane normal whose strokes appear at picture-plane angle theta."""
    a = math.radians(theta_deg - 90.0)
    return v_norm(v_add(v_scale(right, math.cos(a)),
                        v_scale(trueup, math.sin(a))))


# ============================ slicing ========================================

def slice_family(verts, tris, dark, normal, n_lines, cross_phase,
                 cam_fwd, raycast, bbox_diag, offset_frac, t_light,
                 do_occlusion, backface_cutoff=0.05, price=van_der_corput):
    """Triangle-plane intersection for one hatch family -> visible segments.
    Logic identical to the addon v2.5.0 (see Figure 2 walkthrough):
    signed distances -> two edge crossings -> lerp -> offset -> occlusion ray."""
    nrm = v_norm(normal)
    proj = [v_dot(v, nrm) for v in verts]
    cmin, cmax = min(proj), max(proj)
    spacing = (cmax - cmin) / max(1, n_lines)
    if spacing <= 0:
        return []
    offset = offset_frac * bbox_diag
    eps = 1e-4 * bbox_diag
    plane_c = [cmin + (k + 0.5) * spacing for k in range(n_lines)]
    segs = []
    for (ia, ib, ic) in tris:
        va, vb, vc = verts[ia], verts[ib], verts[ic]
        da, db, dc = proj[ia], proj[ib], proj[ic]
        lo = da if da < db else db
        lo = lo if lo < dc else dc
        hi = da if da > db else db
        hi = hi if hi > dc else dc
        fn = v_cross(v_sub(vb, va), v_sub(vc, va))
        if v_len2(fn) == 0.0:
            continue
        fn = v_norm(fn)
        if v_dot(fn, cam_fwd) >= backface_cutoff:      # back-facing -> skip
            continue
        td = (dark[ia] + dark[ib] + dark[ic]) / 3.0
        if td <= t_light:
            continue
        k0 = max(0, int(math.ceil((lo - cmin) / spacing - 0.5)))
        k1 = min(n_lines - 1, int(math.floor((hi - cmin) / spacing - 0.5)))
        for k in range(k0, k1 + 1):
            if td < price((k + cross_phase) & 31):
                continue
            c = plane_c[k]
            sa, sb, sc = da - c, db - c, dc - c
            pts = []
            for (p0, s0, p1, s1) in ((va, sa, vb, sb), (vb, sb, vc, sc), (vc, sc, va, sa)):
                if (s0 > 0) != (s1 > 0):
                    t = s0 / (s0 - s1)
                    pts.append(v_lerp(p0, p1, t))
            if len(pts) != 2:
                continue
            a = v_add(pts[0], v_scale(fn, offset))
            b = v_add(pts[1], v_scale(fn, offset))
            if do_occlusion:
                mid = v_scale(v_add(a, b), 0.5)
                dist = raycast(v_add(mid, v_scale(fn, eps)),
                               v_scale(cam_fwd, -1.0), bbox_diag * 4.0)
                if dist is not None and dist > eps * 4:
                    continue
            segs.append((a, b))
    return segs


def filter_short(segs, min_len):
    """Drop near-degenerate segments (speckle / radiating-fan cleanup)."""
    if min_len <= 0.0:
        return segs
    ml2 = min_len * min_len
    return [(a, b) for (a, b) in segs if v_len2(v_sub(b, a)) >= ml2]


def silhouette_segments(verts, tris, cam_fwd):
    """Occluding-contour edges: each edge shared by one front and one back face."""
    edge_face = {}
    for tri in tris:
        va, vb, vc = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        f = v_dot(v_cross(v_sub(vb, va), v_sub(vc, va)), cam_fwd) < 0.0
        for e in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (e[0], e[1]) if e[0] < e[1] else (e[1], e[0])
            edge_face.setdefault(key, []).append(f)
    return [(verts[i], verts[j]) for (i, j), fs in edge_face.items()
            if len(fs) == 2 and fs[0] != fs[1]]


# ============================ family setup ===================================

def hatch_families(base_angle, cross_angle, t_light, t_cross, darkness_max,
                   right, trueup, mode='SCREEN', normal_a=(0.0, 0.0, 1.0),
                   normal_b=(1.0, 0.0, 0.0), vessel_axis=None, view_dir=None,
                   normal_c=None, t_deep=0.75):
    """SCREEN / WORLD / vessel family list: [(label, normal, threshold, phase)].

    SCREEN: normals built from the camera basis — angles are picture-plane
            angles, cross is relative to A. cross_angle:
            'NONE' | '15' | '45' | '75' | '90' | 'ALL'.
    WORLD:  A and B use the fixed world vectors normal_a / normal_b, exactly
            like the addon's Plane A / Plane B fields. One A, one B ("B"),
            phase 16, regardless of cross_angle.
    vessel: pass vessel_axis (and view_dir) — A slices are rings around the
            axis, B is axis x view (meridians). Overrides both other modes."""
    if vessel_axis is not None:
        ax = v_norm(vessel_axis)
        cross = v_norm(v_cross(ax, view_dir))
        return ([("A", ax, t_light, 0)], [("B", cross, t_cross, 16)])
    if mode == 'WORLD':
        fams = [("B", v_norm(normal_b), t_cross, 16)]
        # Optional third family: enters only where tone exceeds t_deep — the
        # deepest zones. vdC phase 8 sits between A's 0 and B's 16 so the
        # three dither sequences interleave instead of stacking.
        if normal_c is not None:
            fams.append(("C", v_norm(normal_c), t_deep, 8))
        return ([("A", v_norm(normal_a), t_light, 0)], fams)
    A = [("A", screen_normal(base_angle, right, trueup), t_light, 0)]
    if cross_angle == 'NONE':
        deltas = ()
    elif cross_angle == 'ALL':
        deltas = CROSS_DELTAS_ALL
    else:
        deltas = (float(cross_angle),)
    span = max(0.0, darkness_max - t_cross)
    cross = []
    for i, d in enumerate(deltas):
        thr = t_cross + span * 0.6 * (i / len(deltas)) if len(deltas) > 1 else t_cross
        phase = (8 * (i + 1)) & 31
        cross.append((f"B{int(round(d))}",
                      screen_normal(base_angle + d, right, trueup), thr, phase))
    return A, cross


# ============================ pipeline (one call) ============================

def generate(verts, tris, raycast, settings, ao=None, vnorm=None,
             progress=None):
    """The whole fast path in one call: tone -> slice -> silhouette.
    Returns (layers, cam). AO can be passed in pre-computed (the cached slow
    part); if None it is computed here via the injected raycast.

    `settings` is a plain dict — see DEFAULTS for every key and its meaning.
    Plain dicts (not host property groups) keep this callable from anywhere,
    including a JSON blob posted to a web worker."""
    s = dict(DEFAULTS); s.update(settings)
    center, diag = mesh_bounds(verts)
    if vnorm is None:
        vnorm = vertex_normals(verts, tris)
    if ao is None:
        ao = (compute_ao(verts, vnorm, raycast, s["ao_samples"],
                         s["ao_dist_frac"], diag, progress)
              if s["use_ao"] else [1.0] * len(verts))

    cam = make_camera(center, diag, s["view_dir"], s["up"],
                      s["ortho_zoom"], s["page_mm"])
    fwd, right, trueup = cam["fwd"], cam["right"], cam["up"]

    # key light: explicit direction > lamp position > camera-relative dials
    if s["light_dir"] is not None:
        L_key = v_norm(s["light_dir"])
    elif s["light_pos"] is not None:
        L_key = light_from_position(s["light_pos"], center) \
            or light_from_angles(s["light_az"], s["light_el"], right, trueup, fwd)
    else:
        L_key = light_from_angles(s["light_az"], s["light_el"], right, trueup, fwd)
    L_fill = (light_from_angles(s["fill_az"], s["fill_el"], right, trueup, fwd)
              if s["fill_strength"] > 0.0 else None)

    dark = tone_from_ao(ao, vnorm, L_key, L_fill, s["fill_strength"], s["wrap"],
                        s["ambient"], s["tone_gamma"], s["darkness_max"], s["use_ao"])

    A_fams, cross_fams = hatch_families(s["base_angle"], s["cross_angle"],
                                        s["t_light"], s["t_cross"],
                                        s["darkness_max"], right, trueup,
                                        mode=s["hatch_angle_mode"],
                                        normal_a=s["normal_a"],
                                        normal_b=s["normal_b"],
                                        vessel_axis=s["vessel_axis"],
                                        view_dir=s["view_dir"],
                                        normal_c=s.get("normal_c"),
                                        t_deep=s.get("t_deep", 0.75))
    min_len = s["min_seg_frac"] * diag
    layers = []
    price = price_fn(s.get("dither_method", 'vdc'))
    for (lbl, nrm, thr, phase) in A_fams:
        segs = slice_family(verts, tris, dark, nrm, s["n_lines_a"], phase,
                            fwd, raycast, diag, s["offset_frac"], thr,
                            s["do_occlusion"], s["backface_cutoff"], price)
        layers.append((lbl, filter_short(segs, min_len)))
    for (lbl, nrm, thr, phase) in cross_fams:
        darkC = [d if d >= thr else 0.0 for d in dark]
        segs = slice_family(verts, tris, darkC, nrm, s["n_lines_b"], phase,
                            fwd, raycast, diag, s["offset_frac"], thr,
                            s["do_occlusion"], s["backface_cutoff"], price)
        layers.append((lbl, filter_short(segs, min_len)))
    if s["do_silhouette"]:
        layers.append(("silhouette", silhouette_segments(verts, tris, fwd)))
    return layers, cam


DEFAULTS = {
    # page / view
    "page_mm": (381.0, 558.8), "margin_mm": 25.0,
    "view_dir": (0.0, -1.0, 0.0), "up": (0.0, 0.0, 1.0), "ortho_zoom": 1.15,
    # light — priority: light_dir > light_pos > az/el dials
    "light_dir": None,           # explicit world travel direction (sun aim)
    "light_pos": None,           # world lamp position (empty / point light)
    "light_az": -25.0, "light_el": 30.0,
    "fill_strength": 0.0, "fill_az": 150.0, "fill_el": 0.0,
    "wrap": 0.0, "ambient": 0.25,
    # tone
    "use_ao": True, "ao_samples": 24, "ao_dist_frac": 0.20,
    "darkness_max": 0.80, "tone_gamma": 1.5,
    # hatch
    "hatch_angle_mode": 'SCREEN',   # 'SCREEN' | 'WORLD'
    "normal_a": (0.0, 0.0, 1.0),    # WORLD-mode Plane A vector
    "normal_b": (1.0, 0.0, 0.0),    # WORLD-mode Plane B vector
    "vessel_axis": None,            # set to a vector to enable vessel preset
    "normal_c": None,               # WORLD-mode optional Plane C (deep zones)
    "t_deep": 0.75,                 # tone above which Plane C enters
    "dither_method": 'vdc',         # 'vdc' | 'golden' | 'white'
    "pen_mm": 0.30,                 # plotted stroke width (mm)
    "n_lines_a": 500, "n_lines_b": 500,
    "base_angle": 45.0, "cross_angle": '90',
    "t_light": 0.20, "t_cross": 0.65,
    "min_seg_frac": 0.0,
    # visibility
    "offset_frac": 0.0015, "do_occlusion": True, "do_silhouette": True,
    "backface_cutoff": 0.05,
}


# ============================ SVG output =====================================

def svg_string(layers, cam, page_mm, margin_mm, pen_mm=0.30):
    """Layered plotter SVG as a string (host decides where it goes: a file in
    Python, a download blob in the browser)."""
    W, H = page_mm
    # %g matches JavaScript's Number->string (381.0 prints as 381), keeping
    # Python and JS outputs byte-identical.
    Wg, Hg = f"{W:g}", f"{H:g}"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           f'width="{Wg}mm" height="{Hg}mm" viewBox="0 0 {Wg} {Hg}">']
    hatch_w = round(pen_mm, 4)
    silh_w = round(pen_mm * 1.5, 4)
    def style_for(name):
        return ("#26262b", silh_w) if name == "silhouette" else ("#3a3a40", hatch_w)
    for name, segs in layers:
        if not segs:
            continue
        col, sw = style_for(name)
        out.append(f'<g inkscape:groupmode="layer" inkscape:label="{name}" '
                   f'fill="none" stroke="{col}" stroke-width="{sw}" '
                   f'stroke-linecap="round">')
        for a, b in segs:
            ax, ay = project_mm(cam, page_mm, margin_mm, a)
            bx, by = project_mm(cam, page_mm, margin_mm, b)
            out.append(f'<line x1="{ax:.3f}" y1="{ay:.3f}" '
                       f'x2="{bx:.3f}" y2="{by:.3f}"/>')
        out.append('</g>')
    out.append('</svg>')
    return "\n".join(out)


def write_svg(layers, cam, page_mm, margin_mm, path):
    with open(path, "w") as fh:
        fh.write(svg_string(layers, cam, page_mm, margin_mm))
    return path
