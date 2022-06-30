#!/usr/bin/env python

# noinspection PyUnresolvedReferences
import vtkmodules.vtkInteractionStyle
# noinspection PyUnresolvedReferences
import vtkmodules.vtkRenderingOpenGL2
from vtkmodules.vtkCommonColor import vtkNamedColors
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersSources import vtkConeSource
from vtkmodules.vtkInteractionWidgets import vtkBoxWidget
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkRenderWindow,
    vtkRenderWindowInteractor,
    vtkRenderer,
)
import vtk
import numpy as np
from scipy.spatial.transform import Rotation
import invesalius.data.transformations as tr
# Call back function to resize the cone

class MyInteractorStyle(vtk.vtkInteractorStyleTrackballActor):

    def __init__(self, renwin, interactor, renderer,  parent=None):
        self.renwin = renwin
        self.interactor = interactor
        self.renderer = renderer

        self.spinning = False
        self.RemoveAllObservers()
        self.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)
        self.AddObserver("MouseMoveEvent", self.OnSpinMove)

    def OnPressLeftButton(self, evt, obj):
        self.spinning = True
        return

    def OnReleaseLeftButton(self, evt, obj):
        self.spinning = False
        return

    def OnSpinMove(self, evt, obj):
        if self.spinning:
            clickPos = self.GetInteractor().GetEventPosition()

            picker = vtk.vtkPropPicker()
            picker.Pick(clickPos[0], clickPos[1], 0, self.renderer)
            x, y, z = picker.GetPickPosition()

            print(picker.GetActor())
            evt.Spin()
            #evt.SetControlKey()
            evt.OnRightButtonDown()

class testspin:
    def __init__(self):
        self.spinning = False
        self.main()

    def boxCallback(self, obj, event):
        t = vtkTransform()
        obj.GetTransform(t)
        obj.GetProp3D().SetUserTransform(t)

    def rotation_matrix_from_vectors(self, vec1, vec2):
        """ Find the rotation matrix that aligns vec1 to vec2
        :param vec1: A 3d "source" vector
        :param vec2: A 3d "destination" vector
        :return mat: A transform matrix (3x3) which when applied to vec1, aligns it with vec2.
        """
        a, b = (vec1 / np.linalg.norm(vec1)).reshape(3), (vec2 / np.linalg.norm(vec2)).reshape(3)
        v = np.cross(a, b)
        c = np.dot(a, b)
        s = np.linalg.norm(v)
        kmat = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        rotation_matrix = np.eye(3) + kmat + kmat.dot(kmat) * ((1 - c) / (s ** 2))
        return rotation_matrix

    def main(self):
        colors = vtkNamedColors()

        input1 = vtk.vtkPolyData()
        input2 = vtk.vtkPolyData()
        input3 = vtk.vtkPolyData()

        cylinderSource = vtk.vtkCylinderSource()
        cylinderSource.SetRadius(0.02)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(cylinderSource.GetOutputPort())

        actor_cylinder = vtk.vtkActor()
        actor_cylinder.SetMapper(mapper)
        #actor_cylinder.GetProperty().SetColor(colour)
        actor_cylinder.GetProperty().SetLineWidth(1)
        actor_cylinder.AddPosition(0, 0, 0)
        #actor_cylinder.SetScale(0.005)

        #actor_cylinder.SetUserMatrix(self.m_img_vtk)
        #cylinderSource.RotateZ(90)
        cylinderSource.Update()
        input1.ShallowCopy(cylinderSource.GetOutput())

        arrow = vtk.vtkArrowSource()
        arrow.SetArrowOriginToCenter()
        arrow.SetTipResolution(4)
        arrow.SetShaftResolution(40)
        arrow.SetShaftResolution(40)
        arrow.SetShaftRadius(0.05)
        arrow.SetTipRadius(0.15)
        arrow.SetTipLength(0.35)
        arrow.Update()
        input2.ShallowCopy(arrow.GetOutput())
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(arrow.GetOutputPort())

        arrow_actor = vtk.vtkActor()
        arrow_actor.SetMapper(mapper)
        #arrow_actor.GetProperty().SetColor(colour)
        arrow_actor.GetProperty().SetLineWidth(10)
        arrow_actor.AddPosition(0, 0, 0)
        #arrow_actor.SetScale(100)
        torus = vtk.vtkParametricTorus()
        torus.SetRingRadius(0.15)
        torus.SetCrossSectionRadius(0.01)
        torusSource = vtk.vtkParametricFunctionSource()
        torusSource.SetParametricFunction(torus)
        torusSource.Update()
        input3.ShallowCopy(torusSource.GetOutput())
        #arrow_actor.SetUserMatrix(self.m_img_vtk)

        # Append the two meshes
        appendFilter = vtk.vtkAppendPolyData()
        appendFilter.AddInputData(input1)
        appendFilter.AddInputData(input2)
        appendFilter.AddInputData(input3)

        appendFilter.Update()

        #  Remove any duplicate points.
        cleanFilter = vtk.vtkCleanPolyData()
        cleanFilter.SetInputConnection(appendFilter.GetOutputPort())
        cleanFilter.Update()

        # Create a mapper and actor
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(cleanFilter.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        self.actor = actor

        linesPolyData = vtk.vtkPolyData()

        # Create three points
        origin = [0,0,0]
        p0 = [0,10,10]

        # Create a vtkPoints container and store the points in it
        pts = vtk.vtkPoints()
        pts.InsertNextPoint(origin)
        pts.InsertNextPoint(p0)

        # Add the points to the polydata container
        linesPolyData.SetPoints(pts)

        # Create the first line (between Origin and P0)
        line0 = vtk.vtkLine()
        line0.GetPointIds().SetId(0, 0)  # the second 0 is the index of the Origin in linesPolyData's points
        line0.GetPointIds().SetId(1, 1)  # the second 1 is the index of P0 in linesPolyData's points
        # Create a vtkCellArray container and store the lines in it
        lines = vtk.vtkCellArray()
        lines.InsertNextCell(line0)

        # Add the lines to the polydata container
        linesPolyData.SetLines(lines)
        # Setup the visualization pipeline
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(linesPolyData)

        actor_line = vtk.vtkActor()
        actor_line.SetMapper(mapper)
        actor_line.GetProperty().SetLineWidth(4)
        #print(actor_line)

        mat = self.rotation_matrix_from_vectors(p0, [10,0,0])
        vec1_rot = mat.dot(p0)

        print("hi",vec1_rot)
        #orientation = linesPolyData.Get

        # A renderer and render window
        renderer = vtkRenderer()
        renderer.SetBackground(colors.GetColor3d('Blue'))
        #renderer.AddActor(coneActor)
        #renderer.AddActor(arrow_actor)
        #renderer.AddActor(actor_cylinder)
        renderer.AddActor(actor)
        #renderer.AddActor(actor_line)
        self.renderer = renderer

        renwin = vtkRenderWindow()
        self.renwin = renwin
        renwin.AddRenderer(renderer)
        renwin.SetWindowName('BoxWidget')

        # An interactor
        interactor = vtkRenderWindowInteractor()
        self.interactor = interactor
        interactor.SetRenderWindow(renwin)
        self.actor_style = vtk.vtkInteractorStyleTrackballActor()
        self.camera_style = vtk.vtkInteractorStyleTrackballCamera()

        interactor.SetInteractorStyle(self.actor_style)
        #interstyle.RemoveAllObservers()
        self.actor_style.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.actor_style.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)
        self.actor_style.AddObserver("MouseMoveEvent", self.OnSpinMove)
        self.actor_style.AddObserver('MouseWheelForwardEvent',
                                     self.OnZoomMove)
        self.actor_style.AddObserver('MouseWheelBackwardEvent',
                                     self.OnZoomMove)

        self.camera_style.AddObserver("LeftButtonPressEvent", self.OnPressLeftButton)
        self.camera_style.AddObserver("LeftButtonReleaseEvent", self.OnReleaseLeftButton)
        self.camera_style.AddObserver("MouseMoveEvent", self.OnSpinMove)
        self.camera_style.AddObserver('MouseWheelForwardEvent',
                                     self.OnZoomMove)
        self.camera_style.AddObserver('MouseWheelBackwardEvent',
                                     self.OnZoomMove)

        # A Box widget
        #boxWidget = vtkBoxWidget()
        #boxWidget.SetInteractor(interactor)
        #boxWidget.SetProp3D(coneActor)
        #boxWidget.SetPlaceFactor(1.25)  # Make the box 1.25x larger than the actor
        #boxWidget.PlaceWidget()
        #boxWidget.HandlesOff()
        #boxWidget.TranslationEnabledOff()
        #boxWidget.ScalingEnabledOff()
        #boxWidget.On()

        # Connect the event to a function
        #boxWidget.AddObserver('InteractionEvent', boxCallback)

        # Start
        interactor.Initialize()
        #interactor.RemoveAllObservers()
        #interactor.RemoveObservers("LeftButtonPressEvent")
        #interactor.AddObservers("LeftButtonPressEvent")
        renwin.Render()
        interactor.Start()
        self.renderer.GetActiveCamera().Zoom(2)

    def OnPressLeftButton(self, evt, obj):
        self.renderer.GetActiveCamera().Zoom(0.8)
        self.spinning = True
        return

    def OnReleaseLeftButton(self, evt, obj):
        self.spinning = False
        return

    def perpendicular_vector(self, v):
        if v[1] == 0 and v[2] == 0:
            if v[0] == 0:
                raise ValueError('zero vector')
            else:
                return np.cross(v, [0, 1, 0])
        return np.cross(v, [1, 0, 0])

    def unit_vector(self, vector):
        """ Returns the unit vector of the vector.  """
        return vector / np.linalg.norm(vector)

    def OnZoomMove(self, evt, obj):
        self.interactor.SetInteractorStyle(self.camera_style)
        if obj == 'MouseWheelForwardEvent':
            self.camera_style.OnMouseWheelForward()
        else:
            self.camera_style.OnMouseWheelBackward()
        self.actor.SetOrientation(50, 0, 0)
        return

    def OnSpinMove(self, evt, obj):
        self.interactor.SetInteractorStyle(self.actor_style)
        if self.spinning:
            clickPos = self.interactor.GetEventPosition()

            picker = vtk.vtkPropPicker()
            picker.Pick(clickPos[0], clickPos[1], 0, self.renderer)
            x, y, z = picker.GetPickPosition()
            #per = self.perpendicular_vector([x, y, z])
           # print(per, [x, y, z])
            #print(np.rad2deg(self.angle_between(per, [x, y, z])))

            #print(picker.GetActor())
            evt.Spin()
            #evt.SetControlKey()
            evt.OnRightButtonDown()
            vtkmat = self.actor.GetMatrix()
            print("mat", vtkmat)
            narray = np.eye(4)
            vtkmat.DeepCopy(narray.ravel(), vtkmat)
            print("mat", narray)

            print([narray[0][:3], narray[1][:3], narray[2][:3]])
            rotation = Rotation.from_matrix([narray[0][:3], narray[1][:3], narray[2][:3]])
            print(rotation.as_euler(seq="xyz", degrees=True))
            print(np.rad2deg(tr.euler_from_matrix(narray, axes="sxyz")))
        return


if __name__ == '__main__':
    testspin()
