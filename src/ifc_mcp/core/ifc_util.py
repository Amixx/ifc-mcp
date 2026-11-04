"""General IFC utilities written against ``ifcopenshell.file`` and ``ifcopenshell.entity_instance``.

Functions here take and return IFC entities or plain values, depend only on
ifcopenshell and numpy, and import nothing from ``ifc_mcp``.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.util.placement
import numpy as np
import numpy.typing as npt


def get_grid_axis_coordinates(axis: ifcopenshell.entity_instance) -> npt.NDArray[np.float64] | None:
    """Get the points a straight grid axis runs through, in world coordinates

    A grid axis curve is defined in the object coordinate system of the IfcGrid
    it belongs to. The points returned have that grid's placement applied, so
    axes from different grids in the same file can be compared and intersected
    directly. Coordinates are in project length units, and 2D points get a Z of
    0.0 before the placement is applied.

    Only two curve classes are read: an IfcPolyline, and an IfcIndexedPolyCurve
    with no IfcArcIndex segment. The points come in the order the curve walks
    them, with an index repeated by consecutive segments listed once. Every
    other axis curve returns None, even one that is geometrically straight:
    an IfcIndexedPolyCurve with an arc segment, an IfcCircle, an
    IfcTrimmedCurve, an IfcCompositeCurve, and the IFC4X3 alignment curves
    such as IfcGradientCurve, IfcSegmentedReferenceCurve and IfcPolynomialCurve.

    :param axis: The IfcGridAxis
    :raises ValueError: If the axis has no AxisCurve or belongs to no IfcGrid.
    :return: An (n, 3) numpy array of points, or None if the axis curve is not
        one of the two classes read.

    Example:

    .. code:: python

        axis = file.by_type("IfcGridAxis")[0]
        points = ifcopenshell.util.placement.get_grid_axis_coordinates(axis)
        if points is not None:
            start, end = points[0], points[-1]
    """
    curve = axis.AxisCurve
    if curve is None:
        raise ValueError(f"IfcGridAxis #{axis.id()} {axis.AxisTag!r} has no AxisCurve")
    if curve.is_a("IfcPolyline"):
        points = [point.Coordinates for point in curve.Points]
    elif curve.is_a("IfcIndexedPolyCurve"):
        coordinates = curve.Points.CoordList
        if not curve.Segments:
            points = list(coordinates)
        else:
            indices: list[int] = []
            for segment in curve.Segments:
                if segment.is_a("IfcArcIndex"):
                    return None
                for index in segment.wrappedValue:
                    if not indices or indices[-1] != index:
                        indices.append(index)
            points = [coordinates[index - 1] for index in indices]
    else:
        return None

    local = np.zeros((len(points), 4))
    local[:, 3] = 1.0
    for row, point in enumerate(points):
        local[row, : len(point)] = point

    grids = axis.PartOfU or axis.PartOfV or axis.PartOfW
    if not grids:
        raise ValueError(f"IfcGridAxis #{axis.id()} {axis.AxisTag!r} belongs to no IfcGrid")
    grid = grids[0]
    matrix = ifcopenshell.util.placement.get_local_placement(grid.ObjectPlacement)
    return (matrix @ local.T).T[:, :3]
