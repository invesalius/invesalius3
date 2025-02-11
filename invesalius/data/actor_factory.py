import os
import random

import numpy as np
import vtk

import invesalius.constants as const
import invesalius.data.coordinates as dco
import invesalius.project as prj
from invesalius import inv_paths


class ActorFactory:
    def __init__(self):
        pass

    # Utilities

    # TODO: This is copied from viewer_volume.py, should be de-duplicated and moved to a single place.
    def CreateVTKObjectMatrix(self, position, orientation):
        m_img = dco.coordinates_to_transformation_matrix(
            position=position,
            orientation=orientation,
            axes="sxyz",
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

    def CreateTube(self, startpoint, endpoint, colour=(1, 1, 1), radius=1.5):
        # Create a line source.
        line_source = vtk.vtkLineSource()
        line_source.SetPoint1(startpoint)
        line_source.SetPoint2(endpoint)

        # Apply a tube filter to create a thick line (tube).
        tube_filter = vtk.vtkTubeFilter()
        tube_filter.SetInputConnection(line_source.GetOutputPort())
        tube_filter.SetRadius(radius)
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
        color = vtk_colors.GetColor3d("DarkRed")

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

    def CreateArrowUsingDirection(
        self, position, orientation, colour=[0.0, 0.0, 1.0], length_multiplier=1.0
    ):
        """
        Return an actor representing an arrow with the given position and orientation.

        The zero angle of the arrow is in the positive x-direction (right in RAS+ coordinate system,
        which the volume viewer uses). Note that it corresponds to the anterior of the coil, as the
        coil has a coordinate system where x-axis is the anterior-posterior axis.
        """
        arrow = vtk.vtkArrowSource()
        arrow.SetArrowOriginToDefault()
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

        # Apply scaling to adjust the arrow's size.
        size = const.ARROW_MARKER_SIZE
        actor.SetScale(size * length_multiplier, size, size)

        # Create a vtkTransform object to handle transformations.
        transform = vtk.vtkTransform()

        # Reset the transform to identity matrix.
        transform.Identity()

        # Apply translation to set the position.
        #
        # Note that translation is applied first, then rotation.
        transform.Translate(position)

        # Apply the rotation transformations for Euler angles.
        transform.RotateZ(orientation[2])
        transform.RotateY(orientation[1])
        transform.RotateX(orientation[0])

        # Apply the transform to the actor.
        actor.SetUserTransform(transform)

        return actor

    def CreateAim(
        self, position, orientation, colour=[1.0, 1.0, 0.0], scale=1.0, highlight_zero_angle=True
    ):
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
        reader.Update()

        # Create the main transformation for the aim.
        transform = vtk.vtkTransform()
        transform.Identity()

        # Apply translation first.
        transform.Translate(position)

        # Then, apply rotation.
        transform.RotateZ(orientation[2])
        transform.RotateY(orientation[1])
        transform.RotateX(orientation[0])

        # Apply scaling last to ensure it does not affect position or orientation
        transform.Scale(scale, scale, scale)

        # Create a mapper for the STL data
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(reader.GetOutputPort())

        # Create the actor and apply the transformation
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetDiffuseColor(colour)
        actor.GetProperty().SetSpecular(0.2)
        actor.GetProperty().SetSpecularPower(100)
        actor.GetProperty().SetOpacity(const.AIM_ACTOR_SHOWN_OPACITY)
        actor.SetUserTransform(transform)

        return actor

    def CreateBall(self, position, colour=[0.0, 0.0, 1.0], size=2):
        ball_ref = vtk.vtkSphereSource()
        ball_ref.SetRadius(size)
        ball_ref.SetCenter(0, 0, 0)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(ball_ref.GetOutputPort())

        prop = vtk.vtkProperty()
        prop.SetColor(colour)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(prop)

        transform = vtk.vtkTransform()
        transform.Translate(position)
        actor.SetUserTransform(transform)

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

    def ScaleActor(self, actor, scaling_factor):
        """
        Scale an actor by a given factor.
        """
        old_scale = actor.GetScale()
        new_scale = [old_scale[i] * scaling_factor for i in range(3)]
        actor.SetScale(new_scale)

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

    def ReplaceActor(self, renderer, old_actor, new_actor):
        """
        Given a renderer and two actors, replace the old one with the new one, copying
        the old actor's visibility, position, and orientation to the new actor.
        """
        visibility, position, orientation = None, None, None

        visibility = old_actor.GetVisibility()
        position = old_actor.GetPosition()
        orientation = old_actor.GetOrientation()

        # Remove the old actor from the renderer.
        renderer.RemoveActor(old_actor)

        new_actor.SetVisibility(visibility)
        new_actor.SetPosition(position)
        new_actor.SetOrientation(orientation)

        # Add the new actor to the renderer
        renderer.AddActor(new_actor)
