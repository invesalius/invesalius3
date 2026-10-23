# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

import logging
import uuid
from typing import List, Union

import invesalius.session as ses
from invesalius.data.markers.grid_generator import GridGenerator
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.data.markers.marker_transformator import MarkerTransformator
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class MarkersControl(metaclass=Singleton):
    def __init__(self, navigation) -> None:
        self.list: List[Marker] = []
        self.nav_status = False
        self.navigation = navigation
        self.transformator = MarkerTransformator(
            target_resolver=self._FindRobotTarget, main_target_resolver=self.FindTarget
        )
        self._loading_state = False
        self._debug_target_poses = ()
        Publisher.subscribe(self.OnMainCoilChanged, "Main coil changed")
        Publisher.subscribe(self.OnRequestCoilTarget, "Request coil target")
        Publisher.subscribe(self.OnSelectCoil, "Select coil")
        Publisher.subscribe(self.OnResetCoilSelection, "Reset coil selection")
        Publisher.subscribe(self._UpdateDebugTargetPoses, "Set target")
        Publisher.subscribe(self._UpdateDebugTargetPoses, "Unset target")

    def _UpdateDebugTargetPoses(self, marker):
        # Publish one immutable snapshot for the debug worker. Marker poses
        # already use the coordinate convention returned in the coords queue.
        self._debug_target_poses = tuple(
            (m.coil_name, tuple(m.position + m.orientation))
            for m in self.list
            if m.is_target and m.coil_name is not None
        )

    def GetDebugTargetPoses(self):
        """Return a snapshot safe to read from the coordinate worker thread."""
        return self._debug_target_poses

    def SaveState(self) -> None:
        if self._loading_state:
            return
        state = [marker.to_dict() for marker in self.list]

        session = ses.Session()
        session.SetState("markers", state)

    def LoadState(self) -> None:
        if self.list:
            return

        session = ses.Session()
        state = session.GetState("markers")

        if state is None:
            return

        loaded_uuids = set()
        self._loading_state = True
        try:
            for d in state:
                marker = Marker().from_dict(d)
                if marker.marker_uuid and marker.marker_uuid in loaded_uuids:
                    continue
                loaded_uuids.add(marker.marker_uuid)
                self.AddMarker(marker, render=False)
        finally:
            self._loading_state = False
        self.SaveState()

    def AddMarker(self, marker: Marker, render: bool = True, focus: bool = False) -> None:
        """
        Given a marker object, add it to the list of markers and render the new marker.

        If focus is True, the the new marker will get the focus on the marker list.
        """
        if marker.marker_uuid == "":
            marker.marker_uuid = str(uuid.uuid4())

        if marker.is_target:
            coil_name = self._ResolveTargetCoil(marker.coil_name)
            conflict = (
                self.FindTarget(coil_name) is not None
                if coil_name is not None
                else any(m.is_target and m.coil_name is None for m in self.list)
            )
            if conflict:
                logging.warning("Ignoring duplicate target assignment for coil %s", coil_name)
                marker.is_target = False
                marker._set_target_coil(None)
            else:
                marker._set_target_coil(coil_name)
        else:
            marker._set_target_coil(None)

        marker.marker_id = len(self.list)
        self.list.append(marker)

        Publisher.sendMessage("Add marker", marker=marker, render=render, focus=focus)

        if marker.is_target and marker.coil_name is not None:
            self.SetTarget(marker.marker_id, check_for_previous=False)

        if marker.is_point_of_interest:
            self.SetPointOfInterest(marker.marker_id)
            Publisher.sendMessage(
                "Set as Efield target at cortex",
                position=marker.position,
                orientation=marker.orientation,
            )

        if marker.mep_value:
            Publisher.sendMessage("Update marker mep", marker=marker)

        if render:  # this behavior could be misleading
            self.SaveState()

    def Clear(self) -> None:
        marker_ids = [marker.marker_id for marker in self.list]
        self.DeleteMultiple(marker_ids)

    # Note: Unlike parameter render in AddMarker, for DeleteMarker, render=False should
    #       currently not be used outside this class.
    def DeleteMarker(self, marker_id: int, render: bool = True) -> None:
        marker = self.list[marker_id]
        if marker.is_target:
            self.UnsetTarget(marker_id)
        if marker.is_point_of_interest:
            self.UnsetPointOfInterest(marker_id)

        if render:
            Publisher.sendMessage("Delete marker", marker=marker)

        del self.list[marker_id]

        if render:
            for idx, m in enumerate(self.list):
                m.marker_id = idx

            self.SaveState()

        if marker.mep_value:
            Publisher.sendMessage("Redraw MEP mapping")

    def DeleteMultiple(self, marker_ids: List[int]) -> None:
        markers = []
        for m_id in sorted(marker_ids, reverse=True):
            markers.append(self.list[m_id])
            self.DeleteMarker(m_id, render=False)

        Publisher.sendMessage("Delete markers", markers=markers)

        for idx, m in enumerate(self.list):
            m.marker_id = idx

        self.SaveState()

    def _ResolveTargetCoil(self, coil_name=None):
        if self.navigation.n_coils == 1:
            return "default_coil"
        coil_name = coil_name or self.navigation.main_coil
        return coil_name

    def OnSelectCoil(self, coil_name, coil_registration):
        """Release only the target of a coil removed from navigation."""
        if coil_registration is not None:
            return
        for marker in self.list:
            if marker.is_target and marker.coil_name == coil_name:
                self.UnsetTarget(marker.marker_id, coil_name=coil_name)

    def OnResetCoilSelection(self, n_coils, clear_all=False):
        """Release assigned targets when the navigation coil selection is reset."""
        for marker in self.list:
            if marker.is_target and marker.coil_name is not None:
                self.UnsetTarget(marker.marker_id)

    def OnMainCoilChanged(self, coil_name):
        if coil_name is not None:
            for pending in self.list:
                if pending.is_target and pending.coil_name is None:
                    self.SetTarget(pending.marker_id, check_for_previous=False, coil_name=coil_name)
                    break
        marker = self.FindTarget(coil_name) if coil_name is not None else None
        if marker is None:
            self.navigation.UnsetTarget()
        else:
            self.navigation.SetTarget(marker)
        self.transformator.target = marker

    def OnRequestCoilTarget(self, coil_name):
        if coil_name is None:
            return
        marker = self.FindTarget(coil_name)
        if marker is not None:
            Publisher.sendMessage("Set target", marker=marker)

    def _FindRobotTarget(self, robot_id):
        from invesalius.navigation.robot import Robots

        if robot_id is None:
            # Old robot messages without an ID are unambiguous only in single-coil mode.
            return self.FindTarget() if self.navigation.n_coils == 1 else None
        robot = Robots().GetRobot(robot_id)
        return self.FindTarget(robot.coil_name) if robot and robot.coil_name else None

    def SetTarget(self, marker_id: int, check_for_previous: bool = True, coil_name=None) -> None:
        marker = self.list[marker_id]
        coil_name = self._ResolveTargetCoil(coil_name or marker.coil_name)
        if not isinstance(coil_name, str) or not coil_name.strip():
            raise ValueError("Select a coil before assigning a target")
        if check_for_previous and coil_name not in self.navigation.coil_registrations:
            raise ValueError("The selected coil is not registered")
        if marker.coil_name is not None and marker.coil_name != coil_name:
            raise ValueError(f"Target already belongs to {marker.coil_name}")
        previous_target = self.FindTarget(coil_name)

        if check_for_previous and previous_target is marker:
            return

        # Validate first, then update both markers before notifying consumers.
        if previous_target is not None and previous_target is not marker:
            previous_target.is_target = False
            previous_target._set_target_coil(None)

        # Set new target
        marker._set_target_coil(coil_name)
        marker.is_target = True
        self.navigation.ResetCoilAtTarget(coil_name)
        if coil_name == self.navigation.main_coil:
            self.navigation.SetTarget(marker)

        if previous_target is not None and previous_target is not marker:
            Publisher.sendMessage("Unset target", marker=previous_target)
            Publisher.sendMessage(
                "Set target transparency", marker=previous_target, transparent=False
            )

        Publisher.sendMessage("Set target", marker=marker)
        Publisher.sendMessage("Set target transparency", marker=marker, transparent=True)

        # When setting a new target, automatically switch into target mode. Note that the order is important here:
        # first set the target, then move into target mode.
        Publisher.sendMessage("Press target mode button", pressed=True)

        self.SaveState()

    def SetPointOfInterest(self, marker_id: int) -> None:
        # Find the previous point of interest
        prev_poi = self.FindPointOfInterest()

        # If the new point of interest is same as the previous do nothing
        if prev_poi is not None and prev_poi.marker_id == marker_id:
            return

        # Unset the previous point of interest
        if prev_poi is not None:
            self.UnsetPointOfInterest(prev_poi.marker_id)

        # Set the new point of interest
        marker = self.list[marker_id]
        marker.is_point_of_interest = True

        Publisher.sendMessage("Set point of interest", marker=marker)

        self.SaveState()

    def UnsetTarget(self, marker_id: int, coil_name=None) -> None:
        marker = self.list[marker_id]
        if coil_name is not None and marker.coil_name != coil_name:
            raise ValueError("Target is assigned to another coil")
        if marker.coil_name == self.navigation.main_coil:
            self.navigation.UnsetTarget()
        self.navigation.ResetCoilAtTarget(marker.coil_name)
        marker.is_target = False
        marker._set_target_coil(None)

        Publisher.sendMessage("Set target transparency", marker=marker, transparent=False)
        Publisher.sendMessage("Unset target", marker=marker)

        self.SaveState()

    def UnsetPointOfInterest(self, marker_id: int) -> None:
        marker = self.list[marker_id]
        marker.is_point_of_interest = False

        Publisher.sendMessage("Set target transparency", marker=marker, transparent=False)
        Publisher.sendMessage("Unset point of interest", marker=marker)

        self.SaveState()

    def FindTarget(self, coil_name=None) -> Union[None, Marker]:
        """Find the target of a coil, defaulting to the main single-coil slot."""
        coil_name = self._ResolveTargetCoil(coil_name)
        if coil_name is None:
            return None
        for marker in self.list:
            if marker.is_target and marker.coil_name == coil_name:
                return marker

        return None

    def FindLabel(self, label) -> Union[None, Marker]:
        """
        Return a list of markers with the given label.
        If no markers are found, return None.
        """
        matching_markers = [marker for marker in self.list if marker.label == label]

        return matching_markers if matching_markers else None

    def FindPointOfInterest(self) -> Union[None, Marker]:
        for marker in self.list:
            if marker.is_point_of_interest:
                return marker

        return None

    def ChangeLabel(self, marker: Marker, new_label: str) -> None:
        marker.label = str(new_label)
        Publisher.sendMessage("Update marker label", marker=marker)
        self.SaveState()

    def ChangeMEP(self, marker: Marker, new_mep: float) -> None:
        marker.mep_value = new_mep
        Publisher.sendMessage("Update marker mep", marker=marker)

        self.SaveState()

    def ChangeColor(self, marker: Marker, new_color: List[float]) -> None:
        """
        :param marker: instance of Marker
        :param new_color: digital 8-bit per channel rgb
        """
        assert len(new_color) == 3
        marker.colour8bit = new_color
        Publisher.sendMessage("Set new color", marker=marker, new_color=new_color)

        self.SaveState()

    def GetNextMarkerLabel(self) -> str:
        """
        Return a label for the next marker that is not already in use, in the form 'New marker N',
        where N is a number.
        """
        current_labels = [m.label for m in self.list]
        label = "New marker"
        i = 1
        while label in current_labels:
            i += 1
            label = "New marker " + str(i)

        return label

    def DeleteBrainTargets(self) -> None:
        def find_brain_target() -> Union[None, Marker]:
            for marker in self.list:
                if marker.marker_type == MarkerType.BRAIN_TARGET:
                    return marker
            return None

        condition = True
        while condition:
            brain_target = find_brain_target()
            if brain_target is not None and find_brain_target() is not None:
                self.DeleteMarker(brain_target.marker_id)
            else:
                condition = False

    # Note: these functions only support selection of a single marker at the moment.
    def SelectMarker(self, marker_id: int) -> None:
        marker = self.list[marker_id]

        # Marker transformator needs to know which marker is selected so it can react to keyboard events.
        self.transformator.UpdateSelectedMarker(marker)

        # Highlight marker in viewer volume.
        Publisher.sendMessage("Highlight marker", marker=marker)

    def DeselectMarker(self) -> None:
        # Marker transformator needs to know that no marker is selected so it can stop reacting to
        # keyboard events.
        self.transformator.UpdateSelectedMarker(None)

    def CreateCoilTargetFromLandmark(self, marker: Marker, label: str = None) -> None:
        new_marker = marker.duplicate()

        self.transformator.ProjectToScalp(
            marker=new_marker,
            # We are projecting the marker that is on the brain surface; hence, project to the opposite side
            # of the scalp because the normal vectors are unreliable on the brain side of the scalp.
            opposite_side=True,
        )
        new_marker.marker_type = MarkerType.COIL_TARGET
        if not label:
            new_marker.label = self.GetNextMarkerLabel()
        else:
            new_marker.label = label

        self.AddMarker(new_marker)

    def CreateCoilTargetFromBrainTarget(self, marker: Marker) -> None:
        new_marker = Marker()

        new_marker.position = marker["position"]
        new_marker.orientation = marker["orientation"]
        new_marker.marker_type = MarkerType.COIL_TARGET

        # Marker IDs start from zero, hence len(self.markers) will be the ID of the new marker.
        new_marker.marker_id = len(self.list)
        # Create an uuid for the marker
        new_marker.marker_uuid = str(uuid.uuid4())
        # Set the visualization attribute to an empty dictionary.
        new_marker.visualization = {}
        # Unset the is_target attribute.
        new_marker.is_target = False

        self.transformator.ProjectToScalp(
            marker=new_marker,
            # We are projecting the marker that is on the brain surface; hence, project to the opposite side
            # of the scalp because the normal vectors are unreliable on the brain side of the scalp.
            opposite_side=True,
        )
        new_marker.label = self.GetNextMarkerLabel()

        self.AddMarker(new_marker)

    def CreateCoilTargetFromCoilPose(self, marker: Marker) -> None:
        new_marker = marker.duplicate()

        new_marker.marker_type = MarkerType.COIL_TARGET

        self.AddMarker(new_marker)

    def CreateGridFromTarget(
        self,
        reference_marker: Marker,
        grid_type: str,
        rows: int = 3,
        cols: int = 3,
        rings: int = 2,
        points_per_ring: int = 6,
        spacing: float = 5.0,
    ) -> List[Marker]:
        """Create a grid of coil targets around a reference coil target.

        The grid is generated on the smoothed scalp surface, with each target
        oriented tangentially to the local surface normal and preserving the
        z_rotation and z_offset from the reference target.

        :param reference_marker: The coil target marker to use as the center of the grid.
        :param grid_type: Type of grid layout: 'rectangular' or 'circular'.
        :param rows: Number of rows (rectangular grid only).
        :param cols: Number of columns (rectangular grid only).
        :param rings: Number of concentric rings (circular grid only).
        :param points_per_ring: Number of points per ring (circular grid only).
        :param spacing: Distance between adjacent grid points in mm.
        :return: List of newly created Marker objects.
        """
        grid_generator = GridGenerator(self.transformator.surface_geometry)

        if grid_type == "rectangular":
            new_markers = grid_generator.generate_rectangular_grid(
                reference_marker, rows, cols, spacing
            )
        elif grid_type == "circular":
            new_markers = grid_generator.generate_circular_grid(
                reference_marker, rings, points_per_ring, spacing
            )
        else:
            raise ValueError(f"Unknown grid type: {grid_type}")

        for marker in new_markers:
            self.AddMarker(marker)

        return new_markers
