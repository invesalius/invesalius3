#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import math
import random

from wx.lib.pubsub import pub as Publisher
import vtk

import constants as const
import project as prj
import session as ses
import utils

TYPE = {const.LINEAR: _(u"Linear"),
        const.ANGULAR: _(u"Angular"),
        }

LOCATION = {const.SURFACE: _(u"3D"),
            const.AXIAL: _(u"Axial"),
            const.CORONAL: _(u"Coronal"),
            const.SAGITAL: _(u"Sagittal")
        }

map_locations_id = {
    "3D":       const.SURFACE,
    "AXIAL":    const.AXIAL,
    "CORONAL":  const.CORONAL,
    "SAGITAL": const.SAGITAL,
}

map_id_locations = {const.SURFACE: "3D",
                    const.AXIAL: "AXIAL",
                    const.CORONAL: "CORONAL",
                    const.SAGITAL: "SAGITAL",
                    }

class MeasureData:
    """
    Responsible to keep measures data.
    """
    __metaclass__= utils.Singleton
    def __init__(self):
        self.measures = {const.SURFACE: {},
                         const.AXIAL:   {},
                         const.CORONAL: {},
                         const.SAGITAL: {}}
        self._list_measures = []

    def append(self, m):
        try:
            self.measures[m[0].location][m[0].slice_number].append(m)
        except KeyError:
            self.measures[m[0].location][m[0].slice_number] = [m, ]

        self._list_measures.append(m)

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


class MeasurementManager(object):
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
        Publisher.subscribe(self._rm_incomplete_measurements,
                            "Remove incomplete measurements")
        Publisher.subscribe(self._change_measure_point_pos, 'Change measurement point position')

    def _load_measurements(self, pubsub_evt):
        try:
            dict, spacing = pubsub_evt.data
        except ValueError:
            dict = pubsub_evt.data
            spacing = 1.0, 1.0, 1.0
        for i in dict:
            m = dict[i]

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
                    Publisher.sendMessage(("Add actors " + str(m.location)),
                        (actors, m.slice_number))
            self.current = None

            if not m.is_shown:
                mr.SetVisibility(False)
                if m.location == const.SURFACE:
                    Publisher.sendMessage('Render volume viewer')
                else:
                    Publisher.sendMessage('Update slice viewer')

    def _add_point(self, pubsub_evt):
        position = pubsub_evt.data[0]
        type = pubsub_evt.data[1] # Linear or Angular
        location = pubsub_evt.data[2] # 3D, AXIAL, SAGITAL, CORONAL

        if location == const.SURFACE:
            slice_number = 0
            try:
                radius = pubsub_evt.data[3]
            except IndexError:
                radius = const.PROP_MEASURE
        else:
            try:
                slice_number = pubsub_evt.data[3]
            except IndexError:
                slice_number = 0

            try:
                radius = pubsub_evt.data[4]
            except IndexError:
                radius = const.PROP_MEASURE

        to_remove = False
        if self.current is None:
            print "To Create"
            to_create = True
        elif self.current[0].location != location:
            print "To Create"
            print "To Remove"
            to_create = True
            to_remove = True
        elif self.current[0].slice_number != slice_number:
            print "To Create"
            print "To Remove"
            to_create = True
            to_remove = True
        else:
            print "To not Create"
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
                print "---To REMOVE"
                #  actors = self.current[1].GetActors()
                #  slice_number = self.current[0].slice_number
                #  Publisher.sendMessage(('Remove actors ' + str(self.current[0].location)),
                                      #  (actors, slice_number))
                self.measures.pop()[1].Remove()
                if self.current[0].location == const.SURFACE:
                    Publisher.sendMessage('Render volume viewer')
                else:
                    Publisher.sendMessage('Reload actual slice')

            session = ses.Session()
            session.ChangeProject()

            self.current = (m, mr)

        mr = self.current[1]
        m = self.current[0]

        x, y, z = position
        actors = mr.AddPoint(x, y, z)
        m.points.append(position)

        if m.location == const.SURFACE:
            Publisher.sendMessage("Add actors " + str(location),
                    (actors, m.slice_number))

        if self.current not in self.measures:
            self.measures.append(self.current)

        if mr.IsComplete():
            index = prj.Project().AddMeasurement(m)
            #m.index = index # already done in proj
            name = m.name
            colour = m.colour
            m.value = mr.GetValue()
            type_ = TYPE[type]
            location = LOCATION[location]
            if type == const.LINEAR:
                value = u"%.2f mm"% m.value
            else:
                value = u"%.2f°"% m.value

            msg =  'Update measurement info in GUI',
            Publisher.sendMessage(msg,
                                  (index, name, colour,
                                   location,
                                   type_,
                                   value))
            self.current = None

    def _change_measure_point_pos(self, pubsub_evt):
        index, npoint, pos = pubsub_evt.data
        print index, npoint, pos
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
            value = u"%.2f mm"% m.value
        else:
            value = u"%.2f°"% m.value

        Publisher.sendMessage('Update measurement info in GUI',
                              (index, name, colour,
                               location,
                               type_,
                               value))

    def _change_name(self, pubsub_evt):
        index, new_name = pubsub_evt.data
        self.measures[index].name = new_name

    def _remove_measurements(self, pubsub_evt):
        indexes = pubsub_evt.data
        for index in indexes:
            m, mr = self.measures.pop(index)
            try:
                mr.Remove()
            except AttributeError:
                # The is not being displayed
                pass
            prj.Project().RemoveMeasurement(index)
            if m.location == const.SURFACE:
                Publisher.sendMessage(('Remove actors ' + str(m.location)),
                        (mr.GetActors(), m.slice_number))
        Publisher.sendMessage('Update slice viewer')
        Publisher.sendMessage('Render volume viewer')

        session = ses.Session()
        session.ChangeProject()

    def _set_visibility(self, pubsub_evt):
        index, visibility = pubsub_evt.data
        m, mr = self.measures[index]
        m.is_shown = visibility
        mr.SetVisibility(visibility)
        if m.location == const.SURFACE:
            Publisher.sendMessage('Render volume viewer')
        else:
            Publisher.sendMessage('Update slice viewer')

    def _rm_incomplete_measurements(self, pubsub_evt):
        if self.current is None:
            return

        mr = self.current[1]
        print "RM INC M", self.current, mr.IsComplete()
        if not mr.IsComplete():
            print "---To REMOVE"
            self.measures.pop()
            actors = mr.GetActors()
            slice_number = self.current[0].slice_number
            Publisher.sendMessage(('Remove actors ' + str(self.current[0].location)),
                                  (actors, slice_number))
            if self.current[0].location == const.SURFACE:
                Publisher.sendMessage('Render volume viewer')
            else:
                Publisher.sendMessage('Update slice viewer')

            if self.measures:
                self.measures.pop()
            self.current = None


class Measurement():
    general_index = -1
    def __init__(self):
        Measurement.general_index += 1
        self.index = Measurement.general_index
        self.name = const.MEASURE_NAME_PATTERN %(self.index+1)
        self.colour = random.choice(const.MEASURE_COLOUR)
        self.value = 0
        self.location = const.SURFACE # AXIAL, CORONAL, SAGITTAL
        self.type = const.LINEAR # ANGULAR
        self.slice_number = 0
        self.points = []
        self.is_shown = True

    def Load(self, info):
        self.index = info["index"]
        self.name = info["name"]
        self.colour = info["colour"]
        self.value = info["value"]
        self.location = info["location"]
        self.type = info["type"]
        self.slice_number = info["slice_number"]
        self.points = info["points"]
        self.is_shown = info["visible"]

class CirclePointRepresentation(object):
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
        sphere = vtk.vtkSphereSource()
        sphere.SetCenter(x, y, z)
        sphere.SetRadius(self.radius)

#        c = vtk.vtkCoordinate()
#        c.SetCoordinateSystemToWorld()

        m = vtk.vtkPolyDataMapper()
        m.SetInputConnection(sphere.GetOutputPort())
#        m.SetTransformCoordinate(c)

        a = vtk.vtkActor()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)

        return a

class CrossPointRepresentation(object):
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
        pc = self.camera.GetPosition() # camera position
        pf = self.camera.GetFocalPoint() # focal position
        pp = (x, y, z) # point where the user clicked

        # Vector from camera position to user clicked point
        vcp = [j-i for i,j in zip(pc, pp)]
        # Vector from camera position to camera focal point
        vcf = [j-i for i,j in zip(pc, pf)]
        # the vector where the perpendicular vector will be given
        n = [0,0,0]
        # The cross, or vectorial product, give a vector perpendicular to vcp
        # and vcf, in this case this vector will be in horizontal, this vector
        # will be stored in the variable "n"
        vtk.vtkMath.Cross(vcp, vcf, n)
        # then normalize n to only indicate the direction of this vector
        vtk.vtkMath.Normalize(n)
        # then
        p1 = [i*self.size + j for i,j in zip(n, pp)]
        p2 = [i*-self.size + j for i,j in zip(n, pp)]

        sh = vtk.vtkLineSource()
        sh.SetPoint1(p1)
        sh.SetPoint2(p2)

        n = [0,0,0]
        vcn = [j-i for i,j in zip(p1, pc)]
        vtk.vtkMath.Cross(vcp, vcn, n)
        vtk.vtkMath.Normalize(n)
        p3 = [i*self.size + j for i,j in zip(n, pp)]
        p4 = [i*-self.size +j for i,j in zip(n, pp)]

        sv = vtk.vtkLineSource()
        sv.SetPoint1(p3)
        sv.SetPoint2(p4)

        cruz = vtk.vtkAppendPolyData()
        cruz.AddInputData(sv.GetOutput())
        cruz.AddInputData(sh.GetOutput())

        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        m = vtk.vtkPolyDataMapper2D()
        m.SetInputConnection(cruz.GetOutputPort())
        m.SetTransformCoordinate(c)

        a = vtk.vtkActor2D()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)
        return a

class LinearMeasure(object):
    def __init__(self, colour=(1, 0, 0), representation=None):
        self.colour = colour
        self.points = []
        self.point_actor1 = None
        self.point_actor2 = None
        self.line_actor = None
        self.text_actor = None
        self.renderer = None
        if not representation:
            representation = CirclePointRepresentation(colour)
        self.representation = representation
        print colour

    def IsComplete(self):
        """
        Is this measure complete?
        """
        return not self.point_actor2 is None

    def AddPoint(self, x, y, z):
        if not self.point_actor1:
            self.SetPoint1(x, y, z)
            return (self.point_actor1, )
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
        line = vtk.vtkLineSource()
        line.SetPoint1(self.points[0])
        line.SetPoint2(self.points[1])

        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        m = vtk.vtkPolyDataMapper2D()
        m.SetInputConnection(line.GetOutputPort())
        m.SetTransformCoordinate(c)

        a = vtk.vtkActor2D()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)
        self.line_actor = a

    def _draw_text(self):
        p1, p2 = self.points
        text = ' %.2f mm ' % \
                math.sqrt(vtk.vtkMath.Distance2BetweenPoints(p1, p2))
        x,y,z=[(i+j)/2 for i,j in zip(p1, p2)]
        textsource = vtk.vtkTextSource()
        textsource.SetText(text)
        textsource.SetBackgroundColor((250/255.0, 247/255.0, 218/255.0))
        textsource.SetForegroundColor(self.colour)

        m = vtk.vtkPolyDataMapper2D()
        m.SetInputConnection(textsource.GetOutputPort())

        a = vtk.vtkActor2D()
        a.SetMapper(m)
        a.DragableOn()
        a.GetPositionCoordinate().SetCoordinateSystemToWorld()
        a.GetPositionCoordinate().SetValue(x,y,z)
        a.GetProperty().SetColor((0, 1, 0))
        a.GetProperty().SetOpacity(0.75)
        self.text_actor = a

    def GetNumberOfPoints(self):
        return len(self.points)

    def GetValue(self):
        p1, p2 = self.points
        return math.sqrt(vtk.vtkMath.Distance2BetweenPoints(p1, p2))

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
        if self.point_actor1:
            self.renderer.RemoveActor(self.point_actor1)
            del self.point_actor1

        if self.point_actor2:
            self.renderer.RemoveActor(self.point_actor2)
            del self.point_actor2

        if self.line_actor:
            self.renderer.RemoveActor(self.line_actor)
            del self.line_actor

        if self.text_actor:
            self.renderer.RemoveActor(self.text_actor)
            del self.text_actor

    # def __del__(self):
        # self.Remove()


class AngularMeasure(object):
    def __init__(self, colour=(1, 0, 0), representation=None):
        self.colour = colour
        self.points = [0, 0, 0]
        self.number_of_points = 0
        self.point_actor1 = None
        self.point_actor2 = None
        self.point_actor3 = None
        self.line_actor = None
        self.text_actor = None
        if not representation:
            representation = CirclePointRepresentation(colour)
        self.representation = representation
        print colour

    def IsComplete(self):
        return not self.point_actor3 is None

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
            self.points[0] = (x, y, z)
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
            self.points[1] = (x, y, z)
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
            self.points[2] = (x, y, z)
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
        line1 = vtk.vtkLineSource()
        line1.SetPoint1(self.points[0])
        line1.SetPoint2(self.points[1])

        line2 = vtk.vtkLineSource()
        line2.SetPoint1(self.points[1])
        line2.SetPoint2(self.points[2])

        arc = self.DrawArc()

        line = vtk.vtkAppendPolyData()
        line.AddInputConnection(line1.GetOutputPort())
        line.AddInputConnection(line2.GetOutputPort())
        line.AddInputConnection(arc.GetOutputPort())

        print line

        c = vtk.vtkCoordinate()
        c.SetCoordinateSystemToWorld()

        m = vtk.vtkPolyDataMapper2D()
        m.SetInputConnection(line.GetOutputPort())
        m.SetTransformCoordinate(c)

        a = vtk.vtkActor2D()
        a.SetMapper(m)
        a.GetProperty().SetColor(self.colour)
        self.line_actor = a

    def DrawArc(self):

        d1 = math.sqrt(vtk.vtkMath.Distance2BetweenPoints(self.points[0],
                                                          self.points[1]))
        d2 = math.sqrt(vtk.vtkMath.Distance2BetweenPoints(self.points[2],
                                                          self.points[1]))

        if d1 < d2:
            d = d1
            p1 = self.points[0]
            a,b,c = [j-i for i,j in zip(self.points[1], self.points[2])]
        else:
            d = d2
            p1 = self.points[2]
            a,b,c = [j-i for i,j in zip(self.points[1], self.points[0])]

        t = (d / math.sqrt(a**2 + b**2 + c**2))
        x = self.points[1][0] + a*t
        y = self.points[1][1] + b*t
        z = self.points[1][2] + c*t
        p2 = (x, y, z)

        arc = vtk.vtkArcSource()
        arc.SetPoint1(p1)
        arc.SetPoint2(p2)
        arc.SetCenter(self.points[1])
        arc.SetResolution(20)
        return arc

    def _draw_text(self):
        text = u' %.2f ' % \
                self.CalculateAngle()
        x,y,z= self.points[1]
        textsource = vtk.vtkTextSource()
        textsource.SetText(text)
        textsource.SetBackgroundColor((250/255.0, 247/255.0, 218/255.0))
        textsource.SetForegroundColor(self.colour)

        m = vtk.vtkPolyDataMapper2D()
        m.SetInputConnection(textsource.GetOutputPort())

        a = vtk.vtkActor2D()
        a.SetMapper(m)
        a.DragableOn()
        a.GetPositionCoordinate().SetCoordinateSystemToWorld()
        a.GetPositionCoordinate().SetValue(x,y,z)
        self.text_actor = a

    def GetNumberOfPoints(self):
        return self.number_of_points

    def GetValue(self):
        return self.CalculateAngle()

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
        v1 = [j-i for i,j in zip(self.points[0], self.points[1])]
        v2 = [j-i for i,j in zip(self.points[2], self.points[1])]
        #print vtk.vtkMath.Normalize(v1)
        #print vtk.vtkMath.Normalize(v2)
        cos = vtk.vtkMath.Dot(v1, v2)/(vtk.vtkMath.Norm(v1)*vtk.vtkMath.Norm(v2))
        angle = math.degrees(math.acos(cos))
        return angle

    def Remove(self):
        if self.point_actor1:
            self.renderer.RemoveActor(self.point_actor1)
            del self.point_actor1

        if self.point_actor2:
            self.renderer.RemoveActor(self.point_actor2)
            del self.point_actor2

        if self.point_actor3:
            self.renderer.RemoveActor(self.point_actor3)
            del self.point_actor3

        if self.line_actor:
            self.renderer.RemoveActor(self.line_actor)
            del self.line_actor

        if self.text_actor:
            self.renderer.RemoveActor(self.text_actor)
            del self.text_actor

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

    # def __del__(self):
        # self.Remove()
