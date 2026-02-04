import math

from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkPolyData,
)
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkRenderer,
    vtkTextActor,
)

from invesalius.pubsub import pub as Publisher


class RobotForceVisualizer:
    def __init__(self, interactor, num_segments=30, radius=0.5, thickness=0.1):
        self.ren_force = vtkRenderer()
        self.ren_force.SetLayer(1)

        render_window = interactor.GetRenderWindow()
        render_window.AddRenderer(self.ren_force)

        self.ren_force.SetViewport(0.01, 0.23, 0.15, 0.35)
        self.num_segments = num_segments
        self.radius = radius
        self.thickness = thickness
        self.segments = []

        self.threshold_low = 5.0
        self.threshold_high = 20.0
        self.max_force = 40.0

        # visibility flag (default on)
        self.visible = True

        for i in range(num_segments):
            actor = self._create_segment(i)
            self.ren_force.AddActor(actor)
            self.segments.append(actor)
            actor.SetVisibility(False)

        self.text = vtkTextActor()
        self.text.GetTextProperty().SetFontSize(18)
        self.text.GetTextProperty().SetColor(1, 1, 1)
        self.text.GetTextProperty().ShadowOn()
        self.text.SetPosition(0, 10)
        self.ren_force.AddActor2D(self.text)
        self.text.SetVisibility(False)
        self.ren_force.GetActiveCamera().Zoom(0.4)
        self.ren_force.InteractiveOff()

        self.__bind_events()

    def __bind_events(self):
        Publisher.subscribe(
            self.OnUpdateRobotForceData, "Robot to Neuronavigation: Send force sensor data"
        )
        Publisher.subscribe(
            self.set_visibility, "Set visibility robot force visualizer"
        )

    def _create_segment(self, i):
        theta_start = (2 * math.pi / self.num_segments) * i
        theta_end = theta_start + (2 * math.pi / self.num_segments) * 0.9

        r1, r2 = self.radius, self.radius + self.thickness

        points = vtkPoints()
        polys = vtkCellArray()

        coords = [
            [r1 * math.cos(theta_start), r1 * math.sin(theta_start), 0],
            [r2 * math.cos(theta_start), r2 * math.sin(theta_start), 0],
            [r2 * math.cos(theta_end), r2 * math.sin(theta_end), 0],
            [r1 * math.cos(theta_end), r1 * math.sin(theta_end), 0],
        ]

        ids = [points.InsertNextPoint(p) for p in coords]
        polys.InsertNextCell(4)
        for pid in ids:
            polys.InsertCellPoint(pid)

        poly_data = vtkPolyData()
        poly_data.SetPoints(points)
        poly_data.SetPolys(polys)

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(poly_data)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0.9, 0.9, 0.9)
        return actor

    def _update_text_position(self):
        render_window = self.ren_force.GetRenderWindow()
        if not render_window:
            return

        width, height = render_window.GetSize()
        x0, y0, x1, y1 = self.ren_force.GetViewport()

        # Compute viewport size in pixels
        vp_x = int((x1 - x0) * width)
        vp_y = int((y1 - y0) * height)
        vp_left = int(x0 * width)
        vp_bottom = int(y0 * height)

        # Center point in the viewport
        text_x = vp_left + vp_x // 2
        text_y = vp_bottom + vp_y // 2

        # Approximate text width adjustment for centering
        self.text.SetDisplayPosition(text_x - 25, text_y - 10)

    def OnUpdateRobotForceData(self, force_feedback):
        if not self.visible:
            return
        self.update_force(force_feedback)

    def set_visibility(self, visible: bool):
        self.visible = bool(visible)
        vis_int = 1 if self.visible else 0
        for seg in self.segments:
            seg.SetVisibility(vis_int)
        self.text.SetVisibility(vis_int)

    def update_visibility(self, robot_status):
        self.set_visibility(bool(robot_status))

    def update_force(self, force):
        active_segments = int((force / self.max_force) * self.num_segments)
        for i, seg in enumerate(self.segments):
            if i < active_segments:
                if force < self.threshold_low:
                    color = (0.0, 0.8, 0.0)
                elif force < self.threshold_high:
                    color = (1.0, 1.0, 0.0)
                else:
                    color = (1.0, 0.0, 0.0)
                seg.GetProperty().SetColor(*color)
            else:
                seg.GetProperty().SetColor(0.9, 0.9, 0.9)

        self.text.SetInput(f"{force:.1f} N")
        self._update_text_position()
