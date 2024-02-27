import os
import random

import vtk
import numpy as np

from invesalius import inv_paths
import invesalius.data.coordinates as dco
import invesalius.constants as const
import invesalius.project as prj


class ActorFactory(object):
    def __init__(self):
        pass

    # Utilities
    
    # TODO: This is copied from viewer_volume.py, should be de-duplicated and moved to a single place.
    def CreateVTKObjectMatrix(self, position, orientation):
        m_img = dco.coordinates_to_transformation_matrix(
            position=position,
            orientation=orientation,
            axes='sxyz',
        )
        m_img = np.asmatrix(m_img)

        m_img_vtk = vtk.vtkMatrix4x4()

        for row in range(0, 4):
            for col in range(0, 4):
                m_img_vtk.SetElement(row, col, m_img[row, col])

        return m_img_vtk

    # Methods for creating actors

    def CreateLine(self, startpoint, endpoint, colour=(1, 1, 1)):
        # Create a line source.
        line_source = vtk.vtkLineSource()
        line_source.SetPoint1(startpoint)
        line_source.SetPoint2(endpoint)

        # Create a mapper.
        line_mapper = vtk.vtkPolyDataMapper()
        line_mapper.SetInputConnection(line_source.GetOutputPort())

        # Create an actor.
        line_actor = vtk.vtkActor()
        line_actor.GetProperty().SetColor(colour)
        line_actor.SetMapper(line_mapper)

        return line_actor

    def CreateTube(self, startpoint, endpoint, colour=(1, 1, 1), width=1.5):
        # Create a line source.
        line_source = vtk.vtkLineSource()
        line_source.SetPoint1(startpoint)
        line_source.SetPoint2(endpoint)

        # Apply a tube filter to create a thick line (tube).
        tube_filter = vtk.vtkTubeFilter()
        tube_filter.SetInputConnection(line_source.GetOutputPort())
        tube_filter.SetRadius(width)
        tube_filter.SetNumberOfSides(12)

        # Create a mapper.
        line_mapper = vtk.vtkPolyDataMapper()
        line_mapper.SetInputConnection(tube_filter.GetOutputPort())

        # Create an actor.
        line_actor = vtk.vtkActor()
        line_actor.GetProperty().SetColor(colour)
        line_actor.SetMapper(line_mapper)

        return line_actor

    def CreateArrow(self, startPoint, endPoint):
        # Compute a basis
        normalizedX = [0 for i in range(3)]
        normalizedY = [0 for i in range(3)]
        normalizedZ = [0 for i in range(3)]

        # The X axis is a vector from start to end
        math = vtk.vtkMath()
        math.Subtract(endPoint, startPoint, normalizedX)
        length = math.Norm(normalizedX)
        math.Normalize(normalizedX)

        # The Z axis is an arbitrary vector cross X
        arbitrary = [0 for i in range(3)]
        arbitrary[0] = random.uniform(-10, 10)
        arbitrary[1] = random.uniform(-10, 10)
        arbitrary[2] = random.uniform(-10, 10)
        math.Cross(normalizedX, arbitrary, normalizedZ)
        math.Normalize(normalizedZ)

        # The Y axis is Z cross X
        math.Cross(normalizedZ, normalizedX, normalizedY)
        matrix = vtk.vtkMatrix4x4()

        # Create the direction cosine matrix
        matrix.Identity()
        for i in range(3):
            matrix.SetElement(i, 0, normalizedX[i])
            matrix.SetElement(i, 1, normalizedY[i])
            matrix.SetElement(i, 2, normalizedZ[i])

        # Apply the transforms arrow 1
        transform_1 = vtk.vtkTransform()
        transform_1.Translate(startPoint)
        transform_1.Concatenate(matrix)
        transform_1.Scale(length, length, length)
        # source
        arrowSource1 = vtk.vtkArrowSource()
        arrowSource1.SetTipResolution(50)
        # Create a mapper and actor
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(arrowSource1.GetOutputPort())
        # Transform the polydata
        transformPD = vtk.vtkTransformPolyDataFilter()
        transformPD.SetTransform(transform_1)
        transformPD.SetInputConnection(arrowSource1.GetOutputPort())
        # mapper transform
        mapper.SetInputConnection(transformPD.GetOutputPort())
        # actor
        actor_arrow = vtk.vtkActor()
        actor_arrow.SetMapper(mapper)

        return actor_arrow

    def CreatePointer(self):
        """
        Create a sphere on volume visualization to reference center of
        cross in slice planes.
        The sphere's radius will be scale times bigger than the average of
        image spacing values.
        """
        vtk_colors = vtk.vtkNamedColors()
        color = vtk_colors.GetColor3d('DarkRed')

        scale = 2.0
        proj = prj.Project()
        s = proj.spacing
        r = (s[0] + s[1] + s[2]) / 3.0 * scale

        ball_source = vtk.vtkSphereSource()
        ball_source.SetRadius(r)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_source.GetOutputPort())

        pointer_actor = vtk.vtkActor()
        pointer_actor.SetMapper(mapper)
        pointer_actor.GetProperty().SetColor(color)
        pointer_actor.PickableOff()
        
        return pointer_actor

    def CreateArrowUsingDirection(self, position, orientation, colour=[0.0, 0.0, 1.0], size=const.ARROW_MARKER_SIZE):
        arrow = vtk.vtkArrowSource()
        arrow.SetArrowOriginToCenter()
        arrow.SetTipResolution(40)
        arrow.SetShaftResolution(40)
        arrow.SetShaftRadius(0.05)
        arrow.SetTipRadius(0.15)
        arrow.SetTipLength(0.35)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(arrow.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(colour)
        actor.GetProperty().SetLineWidth(5)
        actor.AddPosition(0, 0, 0)
        actor.SetScale(size)

        m_img_vtk = self.CreateVTKObjectMatrix(position, orientation)
        actor.SetUserMatrix(m_img_vtk)

        return actor

    def CreateAim(self, position, orientation, colour=[1.0, 1.0, 0.0], scale=1.0, highlight_zero_angle=True):
        """
        Create the aim (crosshair) actor.

        If highlight_zero_angle is True, the aim will have have a small bump at the direction of the
        zero angle.
        """
        if highlight_zero_angle:
            filename = "aim_with_zero_angle_highlighted.stl"
        else:
            filename = "aim.stl"

        path = os.path.join(inv_paths.OBJ_DIR, filename)

        reader = vtk.vtkSTLReader()
        reader.SetFileName(path)

        # Create the transformation for scaling
        scale_transform = vtk.vtkTransform()
        scale_transform.Scale(scale, scale, scale)

        # Apply the scaling to the polydata
        scaled_polydata = vtk.vtkTransformPolyDataFilter()
        scaled_polydata.SetTransform(scale_transform)
        scaled_polydata.SetInputConnection(reader.GetOutputPort())
        scaled_polydata.Update()

        m_img_vtk = self.CreateVTKObjectMatrix(position, orientation)

        # Transform the polydata with position and orientation
        transform = vtk.vtkTransform()
        transform.SetMatrix(m_img_vtk)
        transformed_polydata = vtk.vtkTransformPolyDataFilter()
        transformed_polydata.SetTransform(transform)
        transformed_polydata.SetInputConnection(scaled_polydata.GetOutputPort())
        transformed_polydata.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(transformed_polydata.GetOutputPort())

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetDiffuseColor(colour)
        actor.GetProperty().SetSpecular(.2)
        actor.GetProperty().SetSpecularPower(100)
        actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)

        return actor

    def CreateBall(self, position, colour=[0.0, 0.0, 1.0], size=2):
        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(size)
        ball_ref.SetCenter(position)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtk.vtkProperty()
        prop.SetColor(colour)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(prop)
        actor.PickableOff()

        return actor

    def CreateTorus(self, position, orientation, colour=[0.0, 0.0, 1.0], scale=1.0):
        torus = vtk.vtkParametricTorus()
        torus.SetRingRadius(2)
        torus.SetCrossSectionRadius(1)

        torusSource = vtk.vtkParametricFunctionSource()
        torusSource.SetParametricFunction(torus)
        torusSource.Update()

        torusMapper = vtk.vtkPolyDataMapper()
        torusMapper.SetInputConnection(torusSource.GetOutputPort())
        torusMapper.SetScalarRange(0, 360)

        torusActor = vtk.vtkActor()
        torusActor.SetMapper(torusMapper)
        torusActor.GetProperty().SetDiffuseColor(colour)
        torusActor.SetPosition(position)
        torusActor.SetOrientation(orientation)
        torusActor.SetScale(scale, scale, scale)

        return torusActor

    # Manipulate actors

    # XXX: Do not use, does not seem to work correctly.
    def UpdatePositionAndOrientation(self, actor, new_position, new_orientation):
        """
        Update the position and orientation of an existing actor.
        """
        # Create the transformation matrix for the new position and orientation.
        m_img_vtk = self.CreateVTKObjectMatrix(new_position, new_orientation)

        # Create a vtkTransform and apply the new matrix.
        transform = vtk.vtkTransform()
        transform.SetMatrix(m_img_vtk)

        # Update the actor's transformation matrix.
        actor.SetUserTransform(transform)
