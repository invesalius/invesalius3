# -*- coding: UTF-8 -*-

import math
import sys

import numpy as np
from vtkmodules.vtkCommonCore import vtkMath
from vtkmodules.vtkFiltersCore import vtkAppendPolyData
from vtkmodules.vtkFiltersSources import (
    vtkArcSource,
    vtkLineSource,
    vtkSphereSource,
    vtkTextSource,
)
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkActor2D,
    vtkCoordinate,
    vtkPolyDataMapper,
    vtkPolyDataMapper2D,
)

import invesalius.constants as const
import invesalius.project as prj
import invesalius.session as ses
import invesalius.utils as utils
from invesalius import math_utils
from invesalius.gui.widgets.canvas_renderer import (
    CanvasHandlerBase,
    Ellipse,
    Polygon,
    TextBox,
)
from invesalius.i18n import tr as _
from invesalius.pubsub import pub as Publisher

TYPE = {
    const.LINEAR: _("Linear"),
    const.ANGULAR: _("Angular"),
    const.DENSITY_ELLIPSE: _("Density Ellipse"),
    const.DENSITY_POLYGON: _("Density Polygon"),
}

LOCATION = {
    const.SURFACE: _("3D"),
    const.AXIAL: _("Axial"),
    const.CORONAL: _("Coronal"),
    const.SAGITAL: _("Sagittal"),
}

map_locations_id = {
    "3D": const.SURFACE,
    "AXIAL": const.AXIAL,
    "CORONAL": const.CORONAL,
    "SAGITAL": const.SAGITAL,
}

map_id_locations = {
    const.SURFACE: "3D",
    const.AXIAL: "AXIAL",
    const.CORONAL: "CORONAL",
    const.SAGITAL: "SAGITAL",
}

if sys.platform == "win32":
    MEASURE_LINE_COLOUR = (255, 0, 0, 255)
    MEASURE_TEXT_COLOUR = (0, 0, 0)
    MEASURE_TEXTBOX_COLOUR = (255, 255, 165, 255)
else:
    MEASURE_LINE_COLOUR = (255, 0, 0, 128)
    MEASURE_TEXT_COLOUR = (0, 0, 0)
    MEASURE_TEXTBOX_COLOUR = (255, 255, 165, 255)


DEBUG_DENSITY = False


class MeasureData(metaclass=utils.Singleton):
    """
    Responsible to keep measures data.
    """

    def __init__(self):
        self.measures = {
            const.SURFACE: {},
            const.AXIAL: {},
            const.CORONAL: {},
            const.SAGITAL: {},
        }
        self._list_measures = []

    def append(self, m):
        try:
            self.measures[m[0].location][m[0].slice_number].append(m)
        except KeyError:
            self.measures[m[0].location][m[0].slice_number] = [
                m,
            ]

        self._list_measures.append(m)

    def clean(self):
        self.measures = {
            const.SURFACE: {},
            const.AXIAL: {},
            const.CORONAL: {},
            const.SAGITAL: {},
        }
        self._list_measures = []

    def get(self, location, slice_number):
        return self.measures[map_locations_id[location]].get(slice_number, [])

    def pop(self, idx=None):
        if idx is None:
            m = self._list_measures.pop()
        else:
            m = self._list_measures.pop(idx)
        self.measures[m[0].location][m[0].slice_number].remove(m)
        return m

    def remove(self, m):
        self._list_measures.remove(m)
        self.measures[m[0].location][m[0].slice_number].remove(m)

    def __contains__(self, m):
        return m in self._list_measures

    def __getitem__(self, idx):
        return self._list_measures[idx]

    def __len__(self):
        return len(self._list_measures)


class MeasurementManager:
    """
    A class to manage the use (Addition, remotion and visibility) from
    measures.
    """

    def __init__(self):
        self.current = None
        self.measures = MeasureData()
        self._bind_events()

    def _bind_events(self):
        Publisher.subscribe(self._add_point, "Add measurement point")
        Publisher.subscribe(self._change_name, "Change measurement name")
        Publisher.subscribe(self._remove_measurements, "Remove measurements")
        Publisher.subscribe(self._set_visibility, "Show measurement")
        Publisher.subscribe(self._load_measurements, "Load measurement dict")
        Publisher.subscribe(self._rm_incomplete_measurements, "Remove incomplete measurements")
        Publisher.subscribe(self._change_measure_point_pos, "Change measurement point position")
        Publisher.subscribe(self._add_density_measure, "Add density measurement")
        Publisher.subscribe(self.OnCloseProject, "Close project data")

    def _load_measurements(self, measurement_dict, spacing=(1.0, 1.0, 1.0)):
        for i in measurement_dict:
            m = measurement_dict[i]

            if isinstance(m, DensityMeasurement):
                if m.type == const.DENSITY_ELLIPSE:
                    mr = CircleDensityMeasure(
                        map_id_locations[m.location], m.slice_number, m.colour
                    )
                    mr.set_center(m.points[0])
                    mr.set_point1(m.points[1])
                    mr.set_point2(m.points[2])
                elif m.type == const.DENSITY_POLYGON:
                    mr = PolygonDensityMeasure(
                        map_id_locations[m.location], m.slice_number, m.colour
                    )
                    for p in m.points:
                        mr.insert_point(p)
                    mr.complete_polygon()

                mr.set_density_values(m.min, m.max, m.mean, m.std, m.area, m.perimeter)
                print(m.min, m.max, m.mean, m.std)
                mr._need_calc = False
                self.measures.append((m, mr))
                mr.set_measurement(m)

            else:
                if m.location == const.AXIAL:
                    radius = min(spacing[1], spacing[2]) * const.PROP_MEASURE

                elif m.location == const.CORONAL:
                    radius = min(spacing[0], spacing[1]) * const.PROP_MEASURE

                elif m.location == const.SAGITAL:
                    radius = min(spacing[1], spacing[2]) * const.PROP_MEASURE

                else:
                    radius = min(spacing) * const.PROP_MEASURE

                representation = CirclePointRepresentation(m.colour, radius)
                if m.type == const.LINEAR:
                    mr = LinearMeasure(m.colour, representation)
                else:
                    mr = AngularMeasure(m.colour, representation)
                self.current = (m, mr)
                self.measures.append(self.current)
                for point in m.points:
                    x, y, z = point
                    actors = mr.AddPoint(x, y, z)

                if m.location == const.SURFACE:
                    Publisher.sendMessage(("Add actors " + str(m.location)), actors=actors)

            self.current = None

            if not m.visible:
                mr.SetVisibility(False)
                if m.location == const.SURFACE:
                    Publisher.sendMessage("Render volume viewer")
                else:
                    Publisher.sendMessage("Redraw canvas")

    def _add_point(self, position, type, location, slice_number=0, radius=const.PROP_MEASURE):
        to_remove = False
        if self.current is None:
            to_create = True
        elif self.current[0].location != location:
            to_create = True
            to_remove = True
        elif self.current[0].slice_number != slice_number:
            to_create = True
            to_remove = True
        else:
            to_create = False

        if to_create:
            m = Measurement()
            m.index = len(self.measures)
            m.location = location
            m.slice_number = slice_number
            m.type = type
            representation = CirclePointRepresentation(m.colour, radius)
            if type == const.LINEAR:
                mr = LinearMeasure(m.colour, representation)
            else:
                mr = AngularMeasure(m.colour, representation)
            if to_remove:
                #  actors = self.current[1].GetActors()
                #  slice_number = self.current[0].slice_number
                #  Publisher.sendMessage(('Remove actors ' + str(self.current[0].location)),
                #  (actors, slice_number))
                self.measures.pop()[1].Remove()
                if self.current[0].location == const.SURFACE:
                    Publisher.sendMessage("Render volume viewer")
                else:
                    Publisher.sendMessage("Redraw canvas")

            session = ses.Session()
            session.ChangeProject()

            self.current = (m, mr)

        mr = self.current[1]
        m = self.current[0]

        x, y, z = position
        actors = mr.AddPoint(x, y, z)
        m.points.append(position)

        if m.location == const.SURFACE:
            Publisher.sendMessage("Add actors " + str(location), actors=actors)

        if self.current not in self.measures:
            self.measures.append(self.current)

        if mr.IsComplete():
            index = prj.Project().AddMeasurement(m)
            # m.index = index # already done in proj
            name = m.name
            colour = m.colour
            m.value = mr.GetValue()
            type_ = TYPE[type]
            location = LOCATION[location]
            if type == const.LINEAR:
                value = f"{m.value:.3f} mm"
            else:
                value = f"{m.value:.3f}°"

            msg = ("Update measurement info in GUI",)
            Publisher.sendMessage(
                msg,
                index=index,
                name=name,
                colour=colour,
                location=location,
                type_=type_,
                value=value,
            )
            self.current = None

    def _change_measure_point_pos(self, index, npoint, pos):
        m, mr = self.measures[index]
        x, y, z = pos
        if npoint == 0:
            mr.SetPoint1(x, y, z)
            m.points[0] = x, y, z
        elif npoint == 1:
            mr.SetPoint2(x, y, z)
            m.points[1] = x, y, z
        elif npoint == 2:
            mr.SetPoint3(x, y, z)
            m.points[2] = x, y, z

        m.value = mr.GetValue()

        name = m.name
        colour = m.colour
        m.value = mr.GetValue()
        type_ = TYPE[m.type]
        location = LOCATION[m.location]

        if m.type == const.LINEAR:
            value = f"{m.value:.3f} mm"
        else:
            value = f"{m.value:.3f}°"

        Publisher.sendMessage(
            "Update measurement info in GUI",
            index=index,
            name=name,
            colour=colour,
            location=location,
            type_=type_,
            value=value,
        )

    def _change_name(self, index, name):
        self.measures[index][0].name = name

    def _remove_measurements(self, indexes):
        for index in indexes:
            m, mr = self.measures.pop(index)
            try:
                mr.Remove()
            except AttributeError:
                # The is not being displayed
                pass
            prj.Project().RemoveMeasurement(index)
            if m.location == const.SURFACE:
                Publisher.sendMessage("Remove actors " + str(m.location), actors=mr.GetActors())
        Publisher.sendMessage("Redraw canvas")
        Publisher.sendMessage("Render volume viewer")

        session = ses.Session()
        session.ChangeProject()

    def _set_visibility(self, index, visibility):
        m, mr = self.measures[index]
        m.visible = visibility
        mr.SetVisibility(visibility)
        if m.location == const.SURFACE:
            Publisher.sendMessage("Render volume viewer")
        else:
            Publisher.sendMessage("Redraw canvas")

    def _rm_incomplete_measurements(self):
        if self.current is None:
            return

        m, mr = self.current
        if not mr.IsComplete():
            idx = self.measures._list_measures.index((m, mr))
            self.measures.remove((m, mr))
            Publisher.sendMessage("Remove GUI measurement", measure_index=idx)
            actors = mr.GetActors()
            # slice_number = self.current[0].slice_number
            if m.location == const.SURFACE:
                Publisher.sendMessage(
                    ("Remove actors " + str(self.current[0].location)), actors=actors
                )
            if self.current[0].location == const.SURFACE:
                Publisher.sendMessage("Render volume viewer")
            else:
                Publisher.sendMessage("Redraw canvas")

            #  if self.measures:
            #  self.measures.pop()
            self.current = None

    def _add_density_measure(self, density_measure):
        m = DensityMeasurement()
        m.index = len(self.measures)
        m.location = density_measure.location
        m.slice_number = density_measure.slice_number
        m.colour = density_measure.colour
        m.value = density_measure._mean
        m.area = density_measure._area
        m.mean = density_measure._mean
        m.min = density_measure._min
        m.max = density_measure._max
        m.std = density_measure._std
        if density_measure.format == "ellipse":
            m.points = [
                density_measure.center,
                density_measure.point1,
                density_measure.point2,
            ]
            m.type = const.DENSITY_ELLIPSE
        elif density_measure.format == "polygon":
            m.points = density_measure.points
            m.type = const.DENSITY_POLYGON
        density_measure.index = m.index

        density_measure.set_measurement(m)

        self.measures.append((m, density_measure))

        # index = prj.Project().AddMeasurement(m)

        msg = ("Update measurement info in GUI",)
        Publisher.sendMessage(
            msg,
            index=m.index,
            name=m.name,
            colour=m.colour,
            location=density_measure.orientation,
            type_="Density",
            value=f"{m.value:.3f}",
        )

    def OnCloseProject(self):
        self.measures.clean()


class Measurement:
    general_index = -1

    def __init__(self):
        Measurement.general_index += 1
        self.index = Measurement.general_index
        self.name = const.MEASURE_NAME_PATTERN % (self.index + 1)
        self.colour = next(const.MEASURE_COLOUR)
        self.value = 0
        self.location = const.SURFACE  # AXIAL, CORONAL, SAGITTAL
        self.type = const.LINEAR  # ANGULAR
        self.slice_number = 0
        self.points = []
        self.visible = True

    def Load(self, info):
        self.index = info["index"]
        self.name = info["name"]
        self.colour = info["colour"]
        self.value = info["value"]
        self.location = info["location"]
        self.type = info["type"]
        self.slice_number = info["slice_number"]
        self.points = info["points"]
        self.visible = info["visible"]

    def get_as_dict(self):
        d = {
            "index": self.index,
            "name": self.name,
            "colour": self.colour,
            "value": self.value,
            "location": self.location,
            "type": self.type,
            "slice_number": self.slice_number,
            "points": self.points,
            "visible": self.visible,
        }
        return d


class DensityMeasurement:
    general_index = -1

    def __init__(self):
        DensityMeasurement.general_index += 1
        self.index = DensityMeasurement.general_index
        self.name = const.MEASURE_NAME_PATTERN % (self.index + 1)
        self.colour = next(const.MEASURE_COLOUR)
        self.area = 0
        self.perimeter = 0.0
        self.min = 0
        self.max = 0
        self.mean = 0
        self.std = 0
        self.location = const.AXIAL
        self.type = const.DENSITY_ELLIPSE
        self.slice_number = 0
        self.points = []
        self.visible = True

    def Load(self, info):
        self.index = info["index"]
        self.name = info["name"]
        self.colour = info["colour"]
        self.value = info["value"]
        self.location = info["location"]
        self.type = info["type"]
        self.slice_number = info["slice_number"]
        self.points = info["points"]
        self.visible = info["visible"]
        self.area = info["area"]
        self.min = info["min"]
        self.max = info["max"]
        self.mean = info["mean"]
        self.std = info["std"]
        try:
            self.perimeter = info["perimeter"]
        except KeyError:
            self.perimeter = 0.0

    def get_as_dict(self):
        d = {
            "index": self.index,
            "name": self.name,
            "colour": self.colour,
            "value": self.value,
            "location": self.location,
            "type": self.type,
            "slice_number": self.slice_number,
            "points": self.points,
            "visible": self.visible,
            "area": self.area,
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "std": self.std,
        }
        return d


class CirclePointRepresentation:
    """
    This class represents a circle that indicate a point in the surface
    """

    def __init__(self, colour=(1, 0, 0), radius=1.0):
        """
        colour: the colour of the representation
        radius: the radius of circle representation
        """
        self.colour = colour
        self.radius = radius

    def GetRepresentation(self, x, y, z):
        """
        Return a actor that represents the point in the given x, y, z point
        """
        sphere = vtkSphereSource()
        sphere.SetCenter(x, y, z)
        sphere.SetRadius(self.radius)

        #        c = vtkCoordinate()
        #        c.SetCoordinateSystemToWorld()

        m = vtkPolyDataMapper()
        m.SetInputConnection(sphere.GetOutputPort())
        #        m.SetTransformCoordinate(c)

        a = vtkActor()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)

        return a


class CrossPointRepresentation:
    """
    This class represents a cross that indicate a point in the surface
    """

    def __init__(self, camera, colour=(1, 0, 0), size=1.0):
        """
        colour: the colour of the representation
        size: the size of the representation
        camera: the active camera, to get the orientation to draw the cross
        """
        self.camera = camera
        self.colour = colour
        self.size = size

    def GetRepresentation(self, x, y, z):
        pc = self.camera.GetPosition()  # camera position
        pf = self.camera.GetFocalPoint()  # focal position
        pp = (x, y, z)  # point where the user clicked

        # Vector from camera position to user clicked point
        vcp = [j - i for i, j in zip(pc, pp)]
        # Vector from camera position to camera focal point
        vcf = [j - i for i, j in zip(pc, pf)]
        # the vector where the perpendicular vector will be given
        n = [0, 0, 0]
        # The cross, or vectorial product, give a vector perpendicular to vcp
        # and vcf, in this case this vector will be in horizontal, this vector
        # will be stored in the variable "n"
        vtkMath.Cross(vcp, vcf, n)
        # then normalize n to only indicate the direction of this vector
        vtkMath.Normalize(n)
        # then
        p1 = [i * self.size + j for i, j in zip(n, pp)]
        p2 = [i * -self.size + j for i, j in zip(n, pp)]

        sh = vtkLineSource()
        sh.SetPoint1(p1)
        sh.SetPoint2(p2)

        n = [0, 0, 0]
        vcn = [j - i for i, j in zip(p1, pc)]
        vtkMath.Cross(vcp, vcn, n)
        vtkMath.Normalize(n)
        p3 = [i * self.size + j for i, j in zip(n, pp)]
        p4 = [i * -self.size + j for i, j in zip(n, pp)]

        sv = vtkLineSource()
        sv.SetPoint1(p3)
        sv.SetPoint2(p4)

        cruz = vtkAppendPolyData()
        cruz.AddInputData(sv.GetOutput())
        cruz.AddInputData(sh.GetOutput())

        c = vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        m = vtkPolyDataMapper2D()
        m.SetInputConnection(cruz.GetOutputPort())
        m.SetTransformCoordinate(c)

        a = vtkActor2D()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)
        return a


class LinearMeasure:
    def __init__(self, colour=(1, 0, 0), representation=None):
        self.colour = colour
        self.points = []
        self.point_actor1 = None
        self.point_actor2 = None
        self.line_actor = None
        self.text_actor = None
        self.renderer = None
        self.layer = 0
        if not representation:
            representation = CirclePointRepresentation(colour)
        self.representation = representation

    def IsComplete(self):
        """
        Is this measure complete?
        """
        return self.point_actor2 is not None

    def AddPoint(self, x, y, z):
        if not self.point_actor1:
            self.SetPoint1(x, y, z)
            return (self.point_actor1,)
        elif not self.point_actor2:
            self.SetPoint2(x, y, z)
            return (self.point_actor2, self.line_actor, self.text_actor)

    def SetPoint1(self, x, y, z):
        if len(self.points) == 0:
            self.points.append((x, y, z))
            self.point_actor1 = self.representation.GetRepresentation(x, y, z)
        else:
            self.points[0] = (x, y, z)
            if len(self.points) == 2:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])
                self.CreateMeasure()
            else:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])

    def SetPoint2(self, x, y, z):
        if len(self.points) == 1:
            self.points.append((x, y, z))
            self.point_actor2 = self.representation.GetRepresentation(*self.points[1])
            self.CreateMeasure()
        else:
            self.points[1] = (x, y, z)
            self.Remove()
            self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
            self.point_actor2 = self.representation.GetRepresentation(*self.points[1])
            self.CreateMeasure()

    def CreateMeasure(self):
        self._draw_line()
        self._draw_text()

    def _draw_line(self):
        line = vtkLineSource()
        line.SetPoint1(self.points[0])
        line.SetPoint2(self.points[1])

        c = vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        m = vtkPolyDataMapper2D()
        m.SetInputConnection(line.GetOutputPort())
        m.SetTransformCoordinate(c)

        a = vtkActor2D()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)
        self.line_actor = a

    def _draw_text(self):
        p1, p2 = self.points
        text = f" {math.sqrt(vtkMath.Distance2BetweenPoints(p1, p2)):.3f} mm "
        x, y, z = ((i + j) / 2 for i, j in zip(p1, p2))
        textsource = vtkTextSource()
        textsource.SetText(text)
        textsource.SetBackgroundColor((250 / 255.0, 247 / 255.0, 218 / 255.0))
        textsource.SetForegroundColor(self.colour)

        m = vtkPolyDataMapper2D()
        m.SetInputConnection(textsource.GetOutputPort())

        a = vtkActor2D()
        a.SetMapper(m)
        a.DragableOn()
        a.GetPositionCoordinate().SetCoordinateSystemToWorld()
        a.GetPositionCoordinate().SetValue(x, y, z)
        a.GetProperty().SetColor((0, 1, 0))
        a.GetProperty().SetOpacity(0.75)
        self.text_actor = a

    def draw_to_canvas(self, gc, canvas):
        """
        Draws to an wx.GraphicsContext.

        Parameters:
            gc: is a wx.GraphicsContext
            canvas: the canvas it's being drawn.
        """
        coord = vtkCoordinate()
        points = []
        for p in self.points:
            coord.SetValue(p)
            cx, cy = coord.GetComputedDisplayValue(canvas.evt_renderer)
            #  canvas.draw_circle((cx, cy), 2.5)
            points.append((cx, cy))

        if len(points) > 1:
            for p0, p1 in zip(points[:-1:], points[1::]):
                r, g, b = self.colour
                canvas.draw_line(p0, p1, colour=(r * 255, g * 255, b * 255, 255))

            txt = f"{self.GetValue():.3f} mm"
            canvas.draw_text_box(
                txt,
                (
                    (points[0][0] + points[1][0]) / 2.0,
                    (points[0][1] + points[1][1]) / 2.0,
                ),
                txt_colour=MEASURE_TEXT_COLOUR,
                bg_colour=MEASURE_TEXTBOX_COLOUR,
            )

    def GetNumberOfPoints(self):
        return len(self.points)

    def GetValue(self):
        if self.IsComplete():
            p1, p2 = self.points
            return math.sqrt(vtkMath.Distance2BetweenPoints(p1, p2))
        else:
            return 0.0

    def SetRenderer(self, renderer):
        if self.point_actor1:
            self.renderer.RemoveActor(self.point_actor1)
            renderer.AddActor(self.point_actor1)

        if self.point_actor2:
            self.renderer.RemoveActor(self.point_actor2)
            renderer.AddActor(self.point_actor2)

        if self.line_actor:
            self.renderer.RemoveActor(self.line_actor)
            renderer.AddActor(self.line_actor)

        if self.text_actor:
            self.renderer.RemoveActor(self.text_actor)
            renderer.AddActor(self.text_actor)

        self.renderer = renderer

    def SetVisibility(self, v):
        self.point_actor1.SetVisibility(v)
        self.point_actor2.SetVisibility(v)
        self.line_actor.SetVisibility(v)
        self.text_actor.SetVisibility(v)

    def GetActors(self):
        """
        Get the actors already created in this measure.
        """
        actors = []
        if self.point_actor1:
            actors.append(self.point_actor1)
        if self.point_actor2:
            actors.append(self.point_actor2)
        if self.line_actor:
            actors.append(self.line_actor)
        if self.text_actor:
            actors.append(self.text_actor)
        return actors

    def Remove(self):
        actors = self.GetActors()
        Publisher.sendMessage("Remove actors " + str(const.SURFACE), actors=actors)

    def __del__(self):
        self.Remove()


class AngularMeasure:
    def __init__(self, colour=(1, 0, 0), representation=None):
        self.colour = colour
        self.points = []
        self.number_of_points = 0
        self.point_actor1 = None
        self.point_actor2 = None
        self.point_actor3 = None
        self.line_actor = None
        self.text_actor = None
        self.layer = 0
        if not representation:
            representation = CirclePointRepresentation(colour)
        self.representation = representation

    def IsComplete(self):
        return self.point_actor3 is not None

    def AddPoint(self, x, y, z):
        if not self.point_actor1:
            self.SetPoint1(x, y, z)
            return (self.point_actor1,)
        elif not self.point_actor2:
            self.SetPoint2(x, y, z)
            return (self.point_actor2,)
        elif not self.point_actor3:
            self.SetPoint3(x, y, z)
            return (self.point_actor3, self.line_actor, self.text_actor)

    def SetPoint1(self, x, y, z):
        if self.number_of_points == 0:
            self.points.append((x, y, z))
            self.number_of_points = 1
            self.point_actor1 = self.representation.GetRepresentation(x, y, z)
        else:
            self.points[0] = (x, y, z)
            if len(self.points) == 3:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])
                self.point_actor3 = self.representation.GetRepresentation(*self.points[2])
                self.CreateMeasure()
            else:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])

    def SetPoint2(self, x, y, z):
        if self.number_of_points == 1:
            self.number_of_points = 2
            self.points.append((x, y, z))
            self.point_actor2 = self.representation.GetRepresentation(x, y, z)
        else:
            self.points[1] = (x, y, z)
            if len(self.points) == 3:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])
                self.point_actor3 = self.representation.GetRepresentation(*self.points[2])
                self.CreateMeasure()
            else:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])

    def SetPoint3(self, x, y, z):
        if self.number_of_points == 2:
            self.number_of_points = 3
            self.points.append((x, y, z))
            self.point_actor3 = self.representation.GetRepresentation(x, y, z)
            self.CreateMeasure()
        else:
            self.points[2] = (x, y, z)
            if len(self.points) == 3:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])
                self.point_actor3 = self.representation.GetRepresentation(*self.points[2])
                self.CreateMeasure()
            else:
                self.Remove()
                self.point_actor1 = self.representation.GetRepresentation(*self.points[0])
                self.point_actor2 = self.representation.GetRepresentation(*self.points[1])

    def CreateMeasure(self):
        self._draw_line()
        self._draw_text()

    def _draw_line(self):
        line1 = vtkLineSource()
        line1.SetPoint1(self.points[0])
        line1.SetPoint2(self.points[1])

        line2 = vtkLineSource()
        line2.SetPoint1(self.points[1])
        line2.SetPoint2(self.points[2])

        arc = self.DrawArc()

        line = vtkAppendPolyData()
        line.AddInputConnection(line1.GetOutputPort())
        line.AddInputConnection(line2.GetOutputPort())
        line.AddInputConnection(arc.GetOutputPort())

        c = vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        m = vtkPolyDataMapper2D()
        m.SetInputConnection(line.GetOutputPort())
        m.SetTransformCoordinate(c)

        a = vtkActor2D()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)
        self.line_actor = a

    def DrawArc(self):
        d1 = math.sqrt(vtkMath.Distance2BetweenPoints(self.points[0], self.points[1]))
        d2 = math.sqrt(vtkMath.Distance2BetweenPoints(self.points[2], self.points[1]))

        if d1 < d2:
            d = d1
            p1 = self.points[0]
            a, b, c = (j - i for i, j in zip(self.points[1], self.points[2]))
        else:
            d = d2
            p1 = self.points[2]
            a, b, c = (j - i for i, j in zip(self.points[1], self.points[0]))

        t = d / math.sqrt(a**2 + b**2 + c**2)
        x = self.points[1][0] + a * t
        y = self.points[1][1] + b * t
        z = self.points[1][2] + c * t
        p2 = (x, y, z)

        arc = vtkArcSource()
        arc.SetPoint1(p1)
        arc.SetPoint2(p2)
        arc.SetCenter(self.points[1])
        arc.SetResolution(20)
        return arc

    def _draw_text(self):
        text = f" {self.CalculateAngle():.3f} "
        x, y, z = self.points[1]
        textsource = vtkTextSource()
        textsource.SetText(text)
        textsource.SetBackgroundColor((250 / 255.0, 247 / 255.0, 218 / 255.0))
        textsource.SetForegroundColor(self.colour)

        m = vtkPolyDataMapper2D()
        m.SetInputConnection(textsource.GetOutputPort())

        a = vtkActor2D()
        a.SetMapper(m)
        a.DragableOn()
        a.GetPositionCoordinate().SetCoordinateSystemToWorld()
        a.GetPositionCoordinate().SetValue(x, y, z)
        self.text_actor = a

    def draw_to_canvas(self, gc, canvas):
        """
        Draws to an wx.GraphicsContext.

        Parameters:
            gc: is a wx.GraphicsContext
            canvas: the canvas it's being drawn.
        """

        coord = vtkCoordinate()
        points = []
        for p in self.points:
            coord.SetValue(p)
            cx, cy = coord.GetComputedDoubleDisplayValue(canvas.evt_renderer)
            #  canvas.draw_circle((cx, cy), 2.5)
            points.append((cx, cy))

        if len(points) > 1:
            for p0, p1 in zip(points[:-1:], points[1::]):
                r, g, b = self.colour
                canvas.draw_line(p0, p1, colour=(r * 255, g * 255, b * 255, 255))

            if len(points) == 3:
                txt = f"{self.GetValue():.3f}° / {360.0 - self.GetValue():.3f}°"
                r, g, b = self.colour
                canvas.draw_arc(
                    points[1],
                    points[0],
                    points[2],
                    line_colour=(int(r * 255), int(g * 255), int(b * 255), 255),
                )
                canvas.draw_text_box(
                    txt,
                    (points[1][0], points[1][1]),
                    txt_colour=MEASURE_TEXT_COLOUR,
                    bg_colour=MEASURE_TEXTBOX_COLOUR,
                )

    def GetNumberOfPoints(self):
        return self.number_of_points

    def GetValue(self):
        if self.IsComplete():
            return self.CalculateAngle()
        else:
            return 0.0

    def SetVisibility(self, v):
        self.point_actor1.SetVisibility(v)
        self.point_actor2.SetVisibility(v)
        self.point_actor3.SetVisibility(v)
        self.line_actor.SetVisibility(v)
        self.text_actor.SetVisibility(v)

    def GetActors(self):
        """
        Get the actors already created in this measure.
        """
        actors = []
        if self.point_actor1:
            actors.append(self.point_actor1)
        if self.point_actor2:
            actors.append(self.point_actor2)
        if self.point_actor3:
            actors.append(self.point_actor3)
        if self.line_actor:
            actors.append(self.line_actor)
        if self.text_actor:
            actors.append(self.text_actor)
        return actors

    def CalculateAngle(self):
        """
        Calculate the angle between 2 vectors in 3D space. It is based on law of
        cosines for vector.
        The Alpha Cosine is equal the dot product from two vector divided for
        product between the magnitude from that vectors. Then the angle is inverse
        cosine.
        """
        v1 = [j - i for i, j in zip(self.points[0], self.points[1])]
        v2 = [j - i for i, j in zip(self.points[2], self.points[1])]
        try:
            cos = vtkMath.Dot(v1, v2) / (vtkMath.Norm(v1) * vtkMath.Norm(v2))
        except ZeroDivisionError:
            return 0.0

        angle = math.degrees(math.acos(cos))
        return angle

    def Remove(self):
        actors = self.GetActors()
        Publisher.sendMessage("Remove actors " + str(const.SURFACE), actors=actors)

    def SetRenderer(self, renderer):
        if self.point_actor1:
            self.renderer.RemoveActor(self.point_actor1)
            renderer.AddActor(self.point_actor1)

        if self.point_actor2:
            self.renderer.RemoveActor(self.point_actor2)
            renderer.AddActor(self.point_actor2)

        if self.point_actor3:
            self.renderer.RemoveActor(self.point_actor3)
            renderer.AddActor(self.point_actor3)

        if self.line_actor:
            self.renderer.RemoveActor(self.line_actor)
            renderer.AddActor(self.line_actor)

        if self.text_actor:
            self.renderer.RemoveActor(self.text_actor)
            renderer.AddActor(self.text_actor)

        self.renderer = renderer

    def __del__(self):
        self.Remove()


class CircleDensityMeasure(CanvasHandlerBase):
    def __init__(self, orientation, slice_number, colour=(255, 0, 0, 255), interactive=True):
        super().__init__(None)
        self.parent = None
        self.children = []
        self.layer = 0

        self.colour = colour
        self.center = (0.0, 0.0, 0.0)
        self.point1 = (0.0, 0.0, 0.0)
        self.point2 = (0.0, 0.0, 0.0)

        self.orientation = orientation
        self.slice_number = slice_number

        self.format = "ellipse"

        self.location = map_locations_id[self.orientation]
        self.index = 0

        self._area = 0
        self._min = 0
        self._max = 0
        self._mean = 0
        self._std = 0

        self._measurement = None

        self.ellipse = Ellipse(
            self,
            self.center,
            self.point1,
            self.point2,
            fill=False,
            line_colour=self.colour,
        )
        self.ellipse.layer = 1
        self.add_child(self.ellipse)
        self.text_box = None

        self._need_calc = True
        self.interactive = interactive

    def set_center(self, pos):
        self.center = pos
        self._need_calc = True
        self.ellipse.center = self.center

        if self._measurement:
            self._measurement.points = [self.center, self.point1, self.point2]

    def set_point1(self, pos):
        self.point1 = pos
        self._need_calc = True
        self.ellipse.set_point1(self.point1)

        if self._measurement:
            self._measurement.points = [self.center, self.point1, self.point2]

    def set_point2(self, pos):
        self.point2 = pos
        self._need_calc = True
        self.ellipse.set_point2(self.point2)

        if self._measurement:
            self._measurement.points = [self.center, self.point1, self.point2]

    def set_density_values(
        self,
        _min: float,
        _max: float,
        _mean: float,
        _std: float,
        _area: float,
        _perimeter: float,
    ):
        self._min = _min
        self._max = _max
        self._mean = _mean
        self._std = _std
        self._area = _area
        self._perimeter = _perimeter

        text = _(
            f"Area: {self._area:.3f}\n"
            f"Min: {self._min:.3f}\n"
            f"Max: {self._max:3f}\n"
            f"Mean: {self._mean:3f}\n"
            f"Std: {self._std:.3f}\n"
            f"Perimeter: {self._perimeter:.3f}"
        )

        if self.text_box is None:
            self.text_box = TextBox(
                self, text, self.point1, MEASURE_TEXT_COLOUR, MEASURE_TEXTBOX_COLOUR
            )
            self.text_box.layer = 2
            self.add_child(self.text_box)
        else:
            self.text_box.set_text(text)

        if self._measurement:
            self._measurement.value = self._mean
            self._update_gui_info()

    def _update_gui_info(self):
        msg = ("Update measurement info in GUI",)
        print(msg)
        if self._measurement:
            m = self._measurement
            Publisher.sendMessage(
                msg,
                index=m.index,
                name=m.name,
                colour=m.colour,
                location=self.orientation,
                type_=_("Density Ellipse"),
                value=f"{m.value:.3f}",
            )

    def set_measurement(self, dm):
        self._measurement = dm
        if self._measurement.perimeter == 0.0:
            _perimeter = self.calc_perimeter()
            self._measurement.perimeter = float(_perimeter)

    def SetVisibility(self, value):
        self.visible = value
        self.ellipse.visible = value

    def _3d_to_2d(self, renderer, pos):
        coord = vtkCoordinate()
        coord.SetValue(pos)
        cx, cy = coord.GetComputedDoubleDisplayValue(renderer)
        return cx, cy

    def is_over(self, x, y):
        return None
        #  if self.interactive:
        #  if self.ellipse.is_over(x, y):
        #  return self.ellipse.is_over(x, y)
        #  elif self.text_box.is_over(x, y):
        #  return self.text_box.is_over(x, y)
        #  return None

    def set_interactive(self, value):
        self.interactive = bool(value)
        self.ellipse.interactive = self.interactive

    def draw_to_canvas(self, gc, canvas):
        """
        Draws to an wx.GraphicsContext.

        Parameters:
            gc: is a wx.GraphicsContext
            canvas: the canvas it's being drawn.
        """
        #  cx, cy = self._3d_to_2d(canvas.evt_renderer, self.center)
        #  px, py = self._3d_to_2d(canvas.evt_renderer, self.point1)
        #  radius = ((px - cx)**2 + (py - cy)**2)**0.5
        if self._need_calc:
            self._need_calc = False
            self.calc_density()

        #  canvas.draw_circle((cx, cy), radius, line_colour=self.colour)
        #  self.ellipse.draw_to_canvas(gc, canvas)

        #  #  canvas.draw_text_box(text, (px, py), )
        #  self.text_box.draw_to_canvas(gc, canvas)
        #  #  self.handle_tl.draw_to_canvas(gc, canvas)

    def calc_area(self):
        if self.orientation == "AXIAL":
            a = abs(self.point1[0] - self.center[0])
            b = abs(self.point2[1] - self.center[1])

        elif self.orientation == "CORONAL":
            a = abs(self.point1[0] - self.center[0])
            b = abs(self.point2[2] - self.center[2])

        elif self.orientation == "SAGITAL":
            a = abs(self.point1[1] - self.center[1])
            b = abs(self.point2[2] - self.center[2])

        return math_utils.calc_ellipse_area(a, b)

    def calc_perimeter(self) -> float:
        if self.orientation == "AXIAL":
            a = abs(self.point1[0] - self.center[0])
            b = abs(self.point2[1] - self.center[1])

        elif self.orientation == "CORONAL":
            a = abs(self.point1[0] - self.center[0])
            b = abs(self.point2[2] - self.center[2])

        elif self.orientation == "SAGITAL":
            a = abs(self.point1[1] - self.center[1])
            b = abs(self.point2[2] - self.center[2])

        return math_utils.calc_ellipse_circumference(a, b)

    def calc_density(self):
        from invesalius.data.slice_ import Slice

        slc = Slice()
        n = self.slice_number
        orientation = self.orientation
        img_slice = slc.get_image_slice(orientation, n)
        dy, dx = img_slice.shape
        spacing = slc.spacing

        if orientation == "AXIAL":
            sx, sy = spacing[0], spacing[1]
            cx, cy = self.center[0], self.center[1]

            a = abs(self.point1[0] - self.center[0])
            b = abs(self.point2[1] - self.center[1])

            n = slc.buffer_slices["AXIAL"].index + 1
            m = slc.current_mask.matrix[n, 1:, 1:]

        elif orientation == "CORONAL":
            sx, sy = spacing[0], spacing[2]
            cx, cy = self.center[0], self.center[2]

            a = abs(self.point1[0] - self.center[0])
            b = abs(self.point2[2] - self.center[2])

            n = slc.buffer_slices["CORONAL"].index + 1
            m = slc.current_mask.matrix[1:, n, 1:]

        elif orientation == "SAGITAL":
            sx, sy = spacing[1], spacing[2]
            cx, cy = self.center[1], self.center[2]

            a = abs(self.point1[1] - self.center[1])
            b = abs(self.point2[2] - self.center[2])

            n = slc.buffer_slices["SAGITAL"].index + 1
            m = slc.current_mask.matrix[1:, 1:, n]

        #  a = np.linalg.norm(np.array(self.point1) - np.array(self.center))
        #  b = np.linalg.norm(np.array(self.point2) - np.array(self.center))

        mask_y, mask_x = np.ogrid[0 : dy * sy : sy, 0 : dx * sx : sx]
        #  mask = ((mask_x - cx)**2 + (mask_y - cy)**2) <= (radius ** 2)
        mask = (((mask_x - cx) ** 2 / a**2) + ((mask_y - cy) ** 2 / b**2)) <= 1.0

        #  try:
        #  test_img = np.zeros_like(img_slice)
        #  test_img[mask] = img_slice[mask]
        #  imsave('/tmp/manolo.png', test_img[::-1,:])
        if DEBUG_DENSITY:
            try:
                m[:] = 0
                m[mask] = 254
                slc.buffer_slices[self.orientation].discard_vtk_mask()
                slc.buffer_slices[self.orientation].discard_mask()
                Publisher.sendMessage("Reload actual slice")
            except IndexError:
                pass

        values = img_slice[mask]

        try:
            _min = values.min()
            _max = values.max()
            _mean = values.mean()
            _std = values.std()
        except ValueError:
            _min = 0
            _max = 0
            _mean = 0
            _std = 0

        _area = self.calc_area()
        _perimeter = self.calc_perimeter()

        if self._measurement:
            self._measurement.points = [self.center, self.point1, self.point2]
            self._measurement.value = float(_mean)
            self._measurement.mean = float(_mean)
            self._measurement.min = float(_min)
            self._measurement.max = float(_max)
            self._measurement.std = float(_std)
            self._measurement.area = float(_area)
            self._measurement.perimeter = float(_perimeter)

        self.set_density_values(_min, _max, _mean, _std, _area, _perimeter)

    def IsComplete(self):
        return True

    def on_mouse_move(self, evt):
        old_center = self.center
        self.center = self.ellipse.center
        self.set_point1(self.ellipse.point1)
        self.set_point2(self.ellipse.point2)

        diff = tuple((i - j for i, j in zip(self.center, old_center)))
        self.text_box.position = tuple((i + j for i, j in zip(self.text_box.position, diff)))

        if self._measurement:
            self._measurement.points = [self.center, self.point1, self.point2]
            self._measurement.value = self._mean
            self._measurement.mean = self._mean
            self._measurement.min = self._min
            self._measurement.max = self._max
            self._measurement.std = self._std

        session = ses.Session()
        session.ChangeProject()

    def on_select(self, evt):
        self.layer = 50

    def on_deselect(self, evt):
        self.layer = 0


class PolygonDensityMeasure(CanvasHandlerBase):
    def __init__(self, orientation, slice_number, colour=(255, 0, 0, 255), interactive=True):
        super().__init__(None)
        self.parent = None
        self.children = []
        self.layer = 0

        self.colour = colour
        self.points = []

        self.orientation = orientation
        self.slice_number = slice_number

        self.complete = False

        self.format = "polygon"

        self.location = map_locations_id[self.orientation]
        self.index = 0

        self._area = 0
        self._min = 0
        self._max = 0
        self._mean = 0
        self._std = 0
        self._perimeter = 0

        self._dist_tbox = (0, 0, 0)

        self._measurement = None

        self.polygon = Polygon(self, fill=False, closed=False, line_colour=self.colour)
        self.polygon.layer = 1
        self.add_child(self.polygon)

        self.text_box = None

        self._need_calc = False
        self.interactive = interactive

    def on_mouse_move(self, evt):
        self.points = self.polygon.points
        self._need_calc = self.complete

        if self._measurement:
            self._measurement.points = self.points

        if self.text_box:
            bounds = self.get_bounds()
            p = [bounds[3], bounds[4], bounds[5]]
            if evt.root_event_obj is self.text_box:
                self._dist_tbox = [i - j for i, j in zip(self.text_box.position, p)]
            else:
                self.text_box.position = [i + j for i, j in zip(self._dist_tbox, p)]
                print("text box position", self.text_box.position)

        session = ses.Session()
        session.ChangeProject()

    def draw_to_canvas(self, gc, canvas):
        if self._need_calc:
            self.calc_density(canvas)
        #  if self.visible:
        #  self.polygon.draw_to_canvas(gc, canvas)
        #  if self._need_calc:
        #  self.calc_density(canvas)
        #  if self.text_box:
        #  bounds = self.get_bounds()
        #  p = [bounds[3], bounds[4], bounds[5]]
        #  self.text_box.draw_to_canvas(gc, canvas)
        #  self._dist_tbox = [j-i for i,j in zip(p, self.text_box.position)]

    def insert_point(self, point):
        print("insert points", len(self.points))
        self.polygon.append_point(point)
        self.points.append(point)

    def complete_polygon(self):
        #  if len(self.points) >= 3:
        self.polygon.closed = True
        self._need_calc = True
        self.complete = True

        bounds = self.get_bounds()
        p = [bounds[3], bounds[4], bounds[5]]
        if self.text_box is None:
            p[0] += 5
            self.text_box = TextBox(self, "", p, MEASURE_TEXT_COLOUR, MEASURE_TEXTBOX_COLOUR)
            self.text_box.layer = 2
            self.add_child(self.text_box)

    def calc_density(self, canvas):
        from invesalius.data.slice_ import Slice

        slc = Slice()
        n = self.slice_number
        orientation = self.orientation
        img_slice = slc.get_image_slice(orientation, n)
        dy, dx = img_slice.shape
        spacing = slc.spacing

        if orientation == "AXIAL":
            sx, sy = spacing[0], spacing[1]
            n = slc.buffer_slices["AXIAL"].index + 1
            m = slc.current_mask.matrix[n, 1:, 1:]
            plg_points = [(x / sx, y / sy) for (x, y, z) in self.points]

        elif orientation == "CORONAL":
            sx, sy = spacing[0], spacing[2]
            n = slc.buffer_slices["CORONAL"].index + 1
            m = slc.current_mask.matrix[1:, n, 1:]
            plg_points = [(x / sx, z / sy) for (x, y, z) in self.points]

        elif orientation == "SAGITAL":
            sx, sy = spacing[1], spacing[2]
            n = slc.buffer_slices["SAGITAL"].index + 1
            m = slc.current_mask.matrix[1:, 1:, n]

            plg_points = [(y / sx, z / sy) for (x, y, z) in self.points]

        plg_tmp = Polygon(
            None,
            plg_points,
            fill=True,
            line_colour=(0, 0, 0, 0),
            fill_colour=(255, 255, 255, 255),
            width=1,
            interactive=False,
            is_3d=False,
        )
        h, w = img_slice.shape
        arr = canvas.draw_element_to_array(
            [
                plg_tmp,
            ],
            size=(w, h),
            flip=False,
        )
        mask = arr[:, :, 0] >= 128

        print("mask sum", mask.sum())

        if DEBUG_DENSITY:
            try:
                m[:] = 0
                m[mask] = 254
                slc.buffer_slices[self.orientation].discard_vtk_mask()
                slc.buffer_slices[self.orientation].discard_mask()
                Publisher.sendMessage("Reload actual slice")
            except IndexError:
                pass

        values = img_slice[mask]

        try:
            _min = values.min()
            _max = values.max()
            _mean = values.mean()
            _std = values.std()
        except ValueError:
            _min = 0
            _max = 0
            _mean = 0
            _std = 0

        _area = self.calc_area()
        _perimeter = self.calc_perimeter()

        if self._measurement:
            self._measurement.points = self.points
            self._measurement.value = float(_mean)
            self._measurement.mean = float(_mean)
            self._measurement.min = float(_min)
            self._measurement.max = float(_max)
            self._measurement.std = float(_std)
            self._measurement.area = float(_area)
            self._perimeter = float(_perimeter)

        self.set_density_values(_min, _max, _mean, _std, _area, _perimeter)
        self.calc_area()

        self._need_calc = False

    def calc_area(self):
        if self.orientation == "AXIAL":
            points = [(x, y) for (x, y, z) in self.points]
        elif self.orientation == "CORONAL":
            points = [(x, z) for (x, y, z) in self.points]
        elif self.orientation == "SAGITAL":
            points = [(y, z) for (x, y, z) in self.points]
        area = math_utils.calc_polygon_area(points)
        print("Points", points)
        print("xv = %s;" % [i[0] for i in points])
        print("yv = %s;" % [i[1] for i in points])
        print("Area", area)
        return area

    def calc_perimeter(self) -> float:
        if self.orientation == "AXIAL":
            points = [(x, y) for (x, y, z) in self.points]
        elif self.orientation == "CORONAL":
            points = [(x, z) for (x, y, z) in self.points]
        elif self.orientation == "SAGITAL":
            points = [(y, z) for (x, y, z) in self.points]
        area = math_utils.calc_polygon_perimeter(points)
        print("Points", points)
        print("xv = %s;" % [i[0] for i in points])
        print("yv = %s;" % [i[1] for i in points])
        print("Perimeter", area)
        return area

    def get_bounds(self):
        min_x = min(self.points, key=lambda x: x[0])[0]
        max_x = max(self.points, key=lambda x: x[0])[0]

        min_y = min(self.points, key=lambda x: x[1])[1]
        max_y = max(self.points, key=lambda x: x[1])[1]

        min_z = min(self.points, key=lambda x: x[2])[2]
        max_z = max(self.points, key=lambda x: x[2])[2]

        print(self.points)

        return (min_x, min_y, min_z, max_x, max_y, max_z)

    def IsComplete(self):
        return self.complete

    def set_measurement(self, dm):
        self._measurement = dm
        if self._measurement.perimeter == 0.0:
            _perimeter = self.calc_perimeter()
            self._measurement.perimeter = float(_perimeter)

    def SetVisibility(self, value):
        self.visible = value
        self.polygon.visible = value

    def set_interactive(self, value):
        self.interactive = bool(value)
        self.polygon.interactive = self.interactive

    def is_over(self, x, y):
        None
        #  if self.interactive:
        #  if self.polygon.is_over(x, y):
        #  return self.polygon.is_over(x, y)
        #  if self.text_box is not None:
        #  if self.text_box.is_over(x, y):
        #  return self.text_box.is_over(x, y)
        #  return None

    def set_density_values(
        self,
        _min: float,
        _max: float,
        _mean: float,
        _std: float,
        _area: float,
        _perimeter: float,
    ):
        self._min = _min
        self._max = _max
        self._mean = _mean
        self._std = _std
        self._area = _area
        self._perimeter = _perimeter

        text = _(
            f"Area: {self._area:.3f}\n"
            f"Min: {self._min:.3f}\n"
            f"Max: {self._max:3f}\n"
            f"Mean: {self._mean:3f}\n"
            f"Std: {self._std:.3f}\n"
            f"Perimeter: {self._perimeter:.3f}"
        )

        bounds = self.get_bounds()
        p = [bounds[3], bounds[4], bounds[5]]

        dx = self.text_box.position[0] - p[0]
        dy = self.text_box.position[1] - p[1]
        p[0] += dx
        p[1] += dy
        self.text_box.set_text(text)
        self.text_box.position = p

        if self._measurement:
            self._measurement.value = self._mean
            self._update_gui_info()

    def _update_gui_info(self):
        msg = ("Update measurement info in GUI",)
        print(msg)
        if self._measurement:
            m = self._measurement
            Publisher.sendMessage(
                msg,
                index=m.index,
                name=m.name,
                colour=m.colour,
                location=self.orientation,
                type_=_("Density Polygon"),
                value=f"{m.value:.3f}",
            )
