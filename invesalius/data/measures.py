#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import math
import random

import wx.lib.pubsub as ps
import vtk

import constants as const
import project as prj

TYPE = {const.LINEAR: _(u"Linear"),
        const.ANGULAR: _(u"Angular"),
        }

LOCATION = {const.SURFACE: _(u"3D"),
            const.AXIAL: _(u"Axial"),
            const.CORONAL: _(u"Coronal"),
            const.SAGITAL: _(u"Sagittal")
        }

class MeasurementManager(object):
    """
    A class to manage the use (Addition, remotion and visibility) from
    measures.
    """
    def __init__(self):
        self.current = None
        self.measures = []
        self._bind_events()

    def _bind_events(self):
        ps.Publisher().subscribe(self._add_point, "Add measurement point")
        ps.Publisher().subscribe(self._change_name, "Change measurement name")
        ps.Publisher().subscribe(self._remove_measurements, "Remove measurements")
        ps.Publisher().subscribe(self._set_visibility, "Show measurement")
        ps.Publisher().subscribe(self._load_measurements, "Load measurement dict")

    def _load_measurements(self, pubsub_evt):
        dict = pubsub_evt.data
        for i in dict:
            m = dict[i]
            if m.type == const.LINEAR:
                mr = LinearMeasure(m.colour)
            else:
                mr = AngularMeasure(m.colour)
            self.current = (m, mr)
            self.measures.append(self.current)
            for point in m.points:
                x, y, z = point
                actors = mr.AddPoint(x, y, z)
                ps.Publisher().sendMessage(("Add actors", m.location),
                    (actors, m.slice_number))
            self.current = None

            if not m.is_shown:
                mr.SetVisibility(False)
                if m.location == const.SURFACE:
                    ps.Publisher().sendMessage('Render volume viewer')
                else:
                    ps.Publisher().sendMessage('Update slice viewer')

    def _add_point(self, pubsub_evt):
        position = pubsub_evt.data[0]
        type = pubsub_evt.data[1] # Linear or Angular
        location = pubsub_evt.data[2] # 3D, AXIAL, SAGITAL, CORONAL
        try:
            slice_number = pubsub_evt.data[3]
        except IndexError:
            slice_number = 0

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
            if type == const.LINEAR:
                mr = LinearMeasure(m.colour)
            else:
                mr = AngularMeasure(m.colour)
            if to_remove:
                print "---To REMOVE"
                actors = self.current[1].GetActors()
                slice_number = self.current[0].slice_number
                ps.Publisher().sendMessage(('Remove actors',
                    self.current[0].location), (actors, slice_number))
                if self.current[0].location == const.SURFACE:
                    ps.Publisher().sendMessage('Render volume viewer')
                else:
                    ps.Publisher().sendMessage('Update slice viewer')

            self.current = (m, mr)

        mr = self.current[1]
        m = self.current[0]

        x, y, z = position
        actors = mr.AddPoint(x, y, z)
        m.points.append(position)
        ps.Publisher().sendMessage(("Add actors", location),
                (actors, m.slice_number))

        if mr.IsComplete():
            index = prj.Project().AddMeasurement(m)
            #m.index = index # already done in proj
            self.measures.append(self.current)
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
            ps.Publisher().sendMessage(msg,
                    (index, name, colour,
                        type_, location,
                        value))
            self.current = None

    def _change_name(self, pubsub_evt):
        index, new_name = pubsub_evt.data
        self.measures[index][0].name = new_name

    def _remove_measurements(self, pubsub_evt):
        print "---- measures: _remove_measurements"
        indexes = pubsub_evt.data
        print indexes
        for index in indexes:
            m, mr = self.measures.pop(index)
            actors = mr.GetActors()
            prj.Project().RemoveMeasurement(index)
            ps.Publisher().sendMessage(('Remove actors', m.location), 
                    (actors, m.slice_number))
        ps.Publisher().sendMessage('Update slice viewer')
        ps.Publisher().sendMessage('Render volume viewer')

    def _set_visibility(self, pubsub_evt):
        index, visibility = pubsub_evt.data
        m, mr = self.measures[index]
        m.is_shown = visibility
        mr.SetVisibility(visibility)
        if m.location == const.SURFACE:
            ps.Publisher().sendMessage('Render volume viewer')
        else:
            ps.Publisher().sendMessage('Update slice viewer')


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
        self.is_shown = info["is_shown"]

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
        cruz.AddInput(sv.GetOutput())
        cruz.AddInput(sh.GetOutput())

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
        self.points.append((x, y, z))
        self.point_actor1 = self.representation.GetRepresentation(x, y, z)

    def SetPoint2(self, x, y, z):
        self.points.append((x, y, z))
        self.point_actor2 = self.representation.GetRepresentation(x, y, z)
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
        self.text_actor = a

    def GetNumberOfPoints(self):
        return len(self.points)

    def GetValue(self):
        p1, p2 = self.points
        return math.sqrt(vtk.vtkMath.Distance2BetweenPoints(p1, p2))

    def SetRenderer(self, renderer):
        if self.point_actor1:
            self.render.RemoveActor(self.point_actor1)
            renderer.AddActor(self.point_actor1)

        if self.point_actor2:
            self.render.RemoveActor(self.point_actor2)
            renderer.AddActor(self.point_actor2)

        if self.line_actor:
            self.render.RemoveActor(self.line_actor)
            renderer.AddActor(self.line_actor)

        if self.text_actor:
            self.render.RemoveActor(self.text_actor)
            renderer.AddActor(self.text_actor)

        self.render = renderer

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
            self.render.RemoveActor(self.point_actor1)
            del self.point_actor1

        if self.point_actor2:
            self.render.RemoveActor(self.point_actor2)
            del self.point_actor2

        if self.line_actor:
            self.render.RemoveActor(self.line_actor)
            del self.line_actor

        if self.text_actor:
            self.render.RemoveActor(self.text_actor)
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
        self.points[0] = (x, y, z)
        self.number_of_points = 1
        self.point_actor1 = self.representation.GetRepresentation(x, y, z)

    def SetPoint2(self, x, y, z):
        self.number_of_points = 2
        self.points[1] = (x, y, z)
        self.point_actor2 = self.representation.GetRepresentation(x, y, z)

    def SetPoint3(self, x, y, z):
        self.number_of_points = 3
        self.points[2] = (x, y, z)
        self.point_actor3 = self.representation.GetRepresentation(x, y, z)
        self.CreateMeasure()

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
        line.AddInput(line1.GetOutput())
        line.AddInput(line2.GetOutput())
        line.AddInput(arc.GetOutput())

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
            self.render.RemoveActor(self.point_actor1)
            del self.point_actor1

        if self.point_actor2:
            self.render.RemoveActor(self.point_actor2)
            del self.point_actor2

        if self.point_actor3:
            self.render.RemoveActor(self.point_actor3)
            del self.point_actor3

        if self.line_actor:
            self.render.RemoveActor(self.line_actor)
            del self.line_actor

        if self.text_actor:
            self.render.RemoveActor(self.text_actor)
            del self.text_actor

    def SetRenderer(self, renderer):
        if self.point_actor1:
            self.render.RemoveActor(self.point_actor1)
            renderer.AddActor(self.point_actor1)

        if self.point_actor2:
            self.render.RemoveActor(self.point_actor2)
            renderer.AddActor(self.point_actor2)

        if self.point_actor3:
            self.render.RemoveActor(self.point_actor3)
            renderer.AddActor(self.point_actor3)

        if self.line_actor:
            self.render.RemoveActor(self.line_actor)
            renderer.AddActor(self.line_actor)

        if self.text_actor:
            self.render.RemoveActor(self.text_actor)
            renderer.AddActor(self.text_actor)

        self.render = renderer

    # def __del__(self):
        # self.Remove()
