"""Decimate over-tessellated IFC geometry -- catalog/manufacturer parts and Revit-style
exports that carry hundreds of explicit faces per element (IfcFacetedBrep /
IfcFaceBasedSurfaceModel) baked directly into the source file.

This is a genuine speed lever for downstream tessellation, not just an output-size trim:
measured on a real 216-element MEP discipline file with valves/fittings averaging
300-800 faces each, tessellating the *simplified* source took 11-12x less time than the
original (real element/dedup counts unchanged, 0 diagnostics either way) -- because the cost
lives in OpenCascade building BRep topology from that many explicit faces, before any mesher
setting or triangle count is even relevant. Decimating the *output* mesh after tessellation
does not touch that cost; only shrinking the source does.

Pattern ported from a proven implementation (quadric edge-collapse via Open3D, then strip
orphaned entities) -- not a from-scratch design. Two removal strategies were benchmarked
against a real 164 MB / 981k-triangle file: writing the whole model then regex-stripping
orphaned STEP lines (~123s total, dominated by ifcopenshell's own serializer re-writing
millions of about-to-be-discarded entities) versus removing orphans from the live
ifcopenshell object graph via ``file.remove()`` before writing once. The second, seemingly
more elegant approach was 5x *worse* (~10 minutes) -- ``remove()`` has real per-call
overhead that compounds catastrophically at millions of calls. Write-then-strip is the
faster of the two measured approaches, kept here despite looking like the "naive" one.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import ifcopenshell
import numpy as np

DEFAULT_RATIO = 0.05
DEFAULT_THRESHOLD = 200
DEFAULT_MIN_HEAVY_FACES = 500_000

_ENTITY_ID_RE = re.compile(r"#(\d+)")


@dataclass(frozen=True)
class SimplifyResult:
    simplified: bool
    elapsed_s: float = 0.0
    original_mb: float = 0.0
    simplified_mb: float = 0.0
    face_sets_touched: int = 0
    original_triangles: int = 0
    simplified_triangles: int = 0
    entities_removed: int = 0
    stages: dict[str, float] = field(default_factory=dict)


def needs_simplification(
    path: str | os.PathLike[str],
    *,
    threshold: int = DEFAULT_THRESHOLD,
    min_heavy_faces: int = DEFAULT_MIN_HEAVY_FACES,
) -> bool:
    """True when enough over-tessellated geometry exists to justify the simplify pass.

    Only triggers once the total face count across large face-sets exceeds
    ``min_heavy_faces`` -- cheap files should never pay this pass at all.
    """
    ifc = ifcopenshell.open(str(path))
    heavy = 0
    for brep in ifc.by_type("IfcFacetedBrep"):
        count = len(brep.Outer.CfsFaces)
        if count >= threshold:
            heavy += count
    for fbsm in ifc.by_type("IfcFaceBasedSurfaceModel"):
        for face_set in fbsm.FbsmFaces:
            count = len(face_set.CfsFaces)
            if count >= threshold:
                heavy += count
    return heavy >= min_heavy_faces


def simplify_ifc(
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    ratio: float = DEFAULT_RATIO,
    threshold: int = DEFAULT_THRESHOLD,
    on_progress: Callable[[str], None] | None = None,
) -> SimplifyResult:
    """Decimate every IfcFacetedBrep/IfcFaceBasedSurfaceModel face-set with at least
    ``threshold`` faces down to ``ratio`` of its original triangle count (floor 50 triangles
    per face-set), rewriting valid IFC. Requires the ``simplify`` extra (Open3D)::

        pip install ifc-mcp[simplify]
    """
    try:
        import open3d as o3d
    except ImportError as error:
        raise ImportError("simplify_ifc requires Open3D: pip install ifc-mcp[simplify]") from error

    import time

    t0 = time.monotonic()
    stages: dict[str, float] = {}

    def log(message: str) -> None:
        if on_progress:
            on_progress(message)

    def mark(name: str, since: float) -> float:
        now = time.monotonic()
        stages[name] = round(now - since, 1)
        return now

    t_stage = time.monotonic()
    ifc = ifcopenshell.open(str(input_path))
    t_stage = mark("open", t_stage)

    work_items: list[tuple[Any, str, Any]] = []
    for brep in ifc.by_type("IfcFacetedBrep"):
        shell = brep.Outer
        if len(shell.CfsFaces) >= threshold:
            work_items.append((shell, "brep", brep))
    for fbsm in ifc.by_type("IfcFaceBasedSurfaceModel"):
        for face_set in fbsm.FbsmFaces:
            if len(face_set.CfsFaces) >= threshold:
                work_items.append((face_set, "fbsm", fbsm))
    t_stage = mark("scan_facesets", t_stage)

    log(f"Face sets to simplify: {len(work_items)}")
    if not work_items:
        import shutil

        shutil.copy2(str(input_path), str(output_path))
        return SimplifyResult(simplified=False)

    old_ids: set[int] = set()
    for face_set, _, _ in work_items:
        old_ids |= _collect_faceset_ids(face_set)
    t_stage = mark("collect_old_ids", t_stage)

    total_orig = 0
    total_new = 0
    for face_set, parent_type, parent in work_items:
        verts, faces = _faceset_to_mesh(face_set)
        total_orig += len(faces)
        target = max(50, int(len(faces) * ratio))

        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(verts)
        mesh.triangles = o3d.utility.Vector3iVector(faces)
        simplified = mesh.simplify_quadric_decimation(target_number_of_triangles=target)
        new_verts = np.asarray(simplified.vertices)
        new_tris = np.asarray(simplified.triangles)
        total_new += len(new_tris)

        new_faces = _make_ifc_faces(ifc, new_verts, new_tris)
        if parent_type == "brep":
            parent.Outer = ifc.createIfcClosedShell(new_faces)
        else:
            new_face_set = ifc.createIfcConnectedFaceSet(new_faces)
            parent.FbsmFaces = tuple(
                new_face_set if existing.id() == face_set.id() else existing
                for existing in parent.FbsmFaces
            )
    t_stage = mark("decimate_and_rebuild", t_stage)

    tmp_path = f"{output_path}.tmp"
    log("Writing intermediate file...")
    ifc.write(tmp_path)
    t_stage = mark("write_intermediate", t_stage)

    log(f"Stripping {len(old_ids):,} orphaned entities...")
    with open(tmp_path, encoding="utf-8") as handle:
        lines = handle.readlines()
    t_stage = mark("read_lines", t_stage)
    dropped_ids = _collect_safely_droppable_old_ids(lines, old_ids)
    t_stage = mark("compute_droppable", t_stage)
    with open(output_path, "w", encoding="utf-8") as handle:
        for line in lines:
            if line.startswith("#"):
                entity_id = int(line[1 : line.index("=")])
                if entity_id in dropped_ids:
                    continue
            handle.write(line)
    os.unlink(tmp_path)
    mark("write_final", t_stage)

    original_mb = os.path.getsize(input_path) / (1024 * 1024)
    simplified_mb = os.path.getsize(output_path) / (1024 * 1024)
    return SimplifyResult(
        simplified=True,
        elapsed_s=round(time.monotonic() - t0, 1),
        original_mb=round(original_mb, 1),
        simplified_mb=round(simplified_mb, 1),
        face_sets_touched=len(work_items),
        original_triangles=total_orig,
        simplified_triangles=total_new,
        entities_removed=len(dropped_ids),
        stages=stages,
    )


def _faceset_to_mesh(face_set: Any) -> tuple[np.ndarray, np.ndarray]:
    verts: list[tuple[float, ...]] = []
    faces: list[list[int]] = []
    vert_index: dict[tuple[float, ...], int] = {}
    for face in face_set.CfsFaces:
        for bound in face.Bounds:
            loop = bound.Bound
            indices: list[int] = []
            for point in loop.Polygon:
                coords = tuple(point.Coordinates)
                if coords not in vert_index:
                    vert_index[coords] = len(verts)
                    verts.append(coords)
                indices.append(vert_index[coords])
            if len(indices) >= 3:
                for j in range(1, len(indices) - 1):
                    faces.append([indices[0], indices[j], indices[j + 1]])
    return np.array(verts, dtype=np.float64), np.array(faces, dtype=np.int32)


def _collect_faceset_ids(face_set: Any) -> set[int]:
    ids = {face_set.id()}
    for face in face_set.CfsFaces:
        ids.add(face.id())
        for bound in face.Bounds:
            ids.add(bound.id())
            ids.add(bound.Bound.id())
            for point in bound.Bound.Polygon:
                ids.add(point.id())
    return ids


def _make_ifc_faces(ifc: Any, verts: np.ndarray, faces: np.ndarray) -> list[Any]:
    points = [ifc.createIfcCartesianPoint(tuple(float(x) for x in v)) for v in verts]
    result = []
    for triangle in faces:
        loop = ifc.createIfcPolyLoop(
            [points[triangle[0]], points[triangle[1]], points[triangle[2]]]
        )
        bound = ifc.createIfcFaceOuterBound(loop, True)
        result.append(ifc.createIfcFace([bound]))
    return result


def _collect_safely_droppable_old_ids(lines: list[str], old_ids: set[int]) -> set[int]:
    """Entities under ``old_ids`` reachable from nothing outside ``old_ids`` -- safe to drop.

    Text-based on purpose: a live-graph equivalent (removing orphans from the ifcopenshell
    object model via ``file.remove()`` before writing once) was benchmarked and found ~5x
    slower at this scale -- see the module docstring.
    """
    deps: dict[int, set[int]] = {}
    all_ids: set[int] = set()
    for line in lines:
        if not line.startswith("#"):
            continue
        equals = line.find("=")
        if equals <= 1:
            continue
        entity_id = int(line[1:equals])
        all_ids.add(entity_id)
        deps[entity_id] = {int(m.group(1)) for m in _ENTITY_ID_RE.finditer(line[equals + 1 :])}

    reachable = {entity_id for entity_id in all_ids if entity_id not in old_ids}
    stack = list(reachable)
    while stack:
        current = stack.pop()
        for ref in deps.get(current, ()):
            if ref not in reachable:
                reachable.add(ref)
                stack.append(ref)

    return {
        entity_id for entity_id in old_ids if entity_id in all_ids and entity_id not in reachable
    }
