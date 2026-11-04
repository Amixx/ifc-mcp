import ifcopenshell
import ifcopenshell.api.project
import ifcopenshell.guid
import numpy as np
import pytest

from ifc_mcp.core.ifc_util import get_grid_axis_coordinates


class IFC4:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.file = ifcopenshell.api.project.create_file(version="IFC4")


class IFC4X3:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.file = ifcopenshell.api.project.create_file(version="IFC4X3")


class IFC2X3:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.file = ifcopenshell.api.project.create_file(version="IFC2X3")


def placement(file, location, x_axis=None, relative_to=None):
    return file.createIfcLocalPlacement(
        relative_to,
        file.createIfcAxis2Placement3D(
            file.createIfcCartesianPoint(location),
            None,
            file.createIfcDirection(x_axis) if x_axis else None,
        ),
    )


def polyline(file, points):
    return file.createIfcPolyline([file.createIfcCartesianPoint(p) for p in points])


def add_grid(file, axes="UAxes", curve=None, object_placement=None):
    axis = file.createIfcGridAxis("A", curve, True)
    grid = file.createIfcGrid(ifcopenshell.guid.new(), ObjectPlacement=object_placement)
    setattr(grid, axes, [axis])
    return axis


class TestGetGridAxisCoordinatesIFC4(IFC4):
    def test_getting_the_points_of_a_polyline_axis(self):
        axis = add_grid(self.file, curve=polyline(self.file, ((0.0, 0.0), (10.0, 0.0))))
        assert np.allclose(get_grid_axis_coordinates(axis), [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])

    def test_applying_the_grid_placement(self):
        axis = add_grid(
            self.file,
            curve=polyline(self.file, ((0.0, 0.0), (10.0, 0.0))),
            object_placement=placement(self.file, (5.0, 5.0, 1.0), x_axis=(0.0, 1.0, 0.0)),
        )
        assert np.allclose(get_grid_axis_coordinates(axis), [[5.0, 5.0, 1.0], [5.0, 15.0, 1.0]])

    def test_applying_a_placement_relative_to_another(self):
        site = placement(self.file, (100.0, 0.0, 0.0))
        axis = add_grid(
            self.file,
            curve=polyline(self.file, ((0.0, 0.0), (0.0, 10.0))),
            object_placement=placement(self.file, (0.0, 50.0, 0.0), relative_to=site),
        )
        assert np.allclose(
            get_grid_axis_coordinates(axis), [[100.0, 50.0, 0.0], [100.0, 60.0, 0.0]]
        )

    def test_keeping_the_z_of_3d_points(self):
        axis = add_grid(self.file, curve=polyline(self.file, ((0.0, 0.0, 2.0), (10.0, 0.0, 2.0))))
        assert np.allclose(get_grid_axis_coordinates(axis), [[0.0, 0.0, 2.0], [10.0, 0.0, 2.0]])

    @pytest.mark.parametrize("axes", ("UAxes", "VAxes", "WAxes"))
    def test_finding_the_grid_from_any_axis_list(self, axes):
        axis = add_grid(
            self.file,
            axes=axes,
            curve=polyline(self.file, ((0.0, 0.0), (1.0, 0.0))),
            object_placement=placement(self.file, (0.0, 0.0, 3.0)),
        )
        assert np.allclose(get_grid_axis_coordinates(axis), [[0.0, 0.0, 3.0], [1.0, 0.0, 3.0]])

    def test_getting_the_points_of_an_indexed_poly_curve_without_segments(self):
        points = self.file.createIfcCartesianPointList2D(((0.0, 0.0), (5.0, 0.0), (10.0, 0.0)))
        axis = add_grid(self.file, curve=self.file.createIfcIndexedPolyCurve(points))
        assert np.allclose(
            get_grid_axis_coordinates(axis), [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [10.0, 0.0, 0.0]]
        )

    def test_walking_the_line_segments_of_an_indexed_poly_curve(self):
        points = self.file.createIfcCartesianPointList2D(((0.0, 0.0), (5.0, 0.0), (10.0, 0.0)))
        segments = [self.file.createIfcLineIndex((3, 2)), self.file.createIfcLineIndex((2, 1))]
        axis = add_grid(self.file, curve=self.file.createIfcIndexedPolyCurve(points, segments))
        assert np.allclose(
            get_grid_axis_coordinates(axis), [[10.0, 0.0, 0.0], [5.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        )

    def test_returning_none_for_an_indexed_poly_curve_with_an_arc(self):
        points = self.file.createIfcCartesianPointList2D(((0.0, 0.0), (5.0, 2.0), (10.0, 0.0)))
        segments = [self.file.createIfcArcIndex((1, 2, 3))]
        axis = add_grid(self.file, curve=self.file.createIfcIndexedPolyCurve(points, segments))
        assert get_grid_axis_coordinates(axis) is None

    def test_returning_none_for_a_curved_axis(self):
        circle = self.file.createIfcCircle(
            self.file.createIfcAxis2Placement2D(self.file.createIfcCartesianPoint((0.0, 0.0))), 5.0
        )
        axis = add_grid(self.file, curve=circle)
        assert get_grid_axis_coordinates(axis) is None

    def test_raising_for_an_axis_without_a_curve(self):
        file = ifcopenshell.file.from_string(
            "ISO-10303-21;HEADER;FILE_DESCRIPTION((''),'2;1');"
            "FILE_NAME('','',(''),(''),'','','');FILE_SCHEMA(('IFC4'));ENDSEC;DATA;"
            "#1=IFCGRIDAXIS('A',$,.T.);"
            "#2=IFCGRID('0YvctVUKr0kugbFTf53O9L',$,$,$,$,$,$,(#1),(),$,$);"
            "ENDSEC;END-ISO-10303-21;"
        )
        with pytest.raises(ValueError, match="#1 'A' has no AxisCurve"):
            get_grid_axis_coordinates(file.by_id(1))

    def test_raising_for_an_axis_outside_a_grid(self):
        axis = self.file.createIfcGridAxis("B", polyline(self.file, ((0.0, 0.0), (1.0, 0.0))), True)
        with pytest.raises(ValueError, match=rf"#{axis.id()} 'B' belongs to no IfcGrid"):
            get_grid_axis_coordinates(axis)


class TestGetGridAxisCoordinatesIFC4X3(IFC4X3):
    def test_applying_the_grid_placement(self):
        axis = add_grid(
            self.file,
            curve=polyline(self.file, ((0.0, 0.0), (10.0, 0.0))),
            object_placement=placement(self.file, (2.0, 3.0, 4.0), x_axis=(0.0, 1.0, 0.0)),
        )
        assert np.allclose(get_grid_axis_coordinates(axis), [[2.0, 3.0, 4.0], [2.0, 13.0, 4.0]])


class TestGetGridAxisCoordinatesIFC2X3(IFC2X3):
    def test_applying_the_grid_placement(self):
        axis = add_grid(
            self.file,
            axes="VAxes",
            curve=polyline(self.file, ((0.0, 0.0), (10.0, 0.0))),
            object_placement=placement(self.file, (1.0, 2.0, 0.0)),
        )
        assert np.allclose(get_grid_axis_coordinates(axis), [[1.0, 2.0, 0.0], [11.0, 2.0, 0.0]])
