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

import uuid
from typing import Dict, List, Optional, Union

import invesalius.session as ses
from invesalius.data.markers.marker import Marker, MarkerType
from invesalius.data.markers.marker_transformator import MarkerTransformator
from invesalius.navigation.robot import RobotObjective, Robots
from invesalius.pubsub import pub as Publisher
from invesalius.utils import Singleton


class MarkersControl(metaclass=Singleton):
    def __init__(self, robot: Robots) -> None:
        self.list: List[Marker] = []
        self.nav_status = False
        self.transformator = MarkerTransformator()
        self.robot = robot
        self.TargetCoilAssociation: Dict[str, Marker] = {}
        self.accepted_coils = None
        self.multitarget = False

        self.__bind_events()

    def __bind_events(self) -> None:
        Publisher.subscribe(self.ADDSelectCoil, "ADD select coil")
        Publisher.subscribe(self.DeleteSelectCoil, "Delete select coil")
        Publisher.subscribe(self.RenameSelectCoil, "Rename select coil")
        Publisher.subscribe(self.OnSetMultiTargetMode, "Set simultaneous multicoil mode")
        Publisher.subscribe(self.ResetTargets, "Reset targets")
        Publisher.subscribe(
            self.UpdateZOffsetTargetByRobot, "Robot to Neuronavigation: Update z_offset target"
        )

    def UpdateZOffsetTargetByRobot(self, z_offset, robot_ID):
        coil_name = self.robot.robots[robot_ID].coil_name
        marker = self.FindTarget(coil_name)

        if not marker or not self.transformator.robot_track_status:
            return
        displacement = self.transformator.DisplacementOffset(z_offset)
        if displacement is None:
            return
        self.transformator.MoveMarker(marker=marker, displacement=displacement)
        # Notify the volume viewer about the updated marker
        Publisher.sendMessage(
            "Update marker",
            marker=marker,
            new_position=marker.position,
            new_orientation=marker.orientation,
        )
        # If this is the active target, update it globally
        if marker.is_target:
            Publisher.sendMessage("Set target", marker=marker)

    def OnSetMultiTargetMode(self, state=False, coils_list=None):
        self.accepted_coils = coils_list
        self.multitarget = state

    def ADDSelectCoil(self, coil_name, coil_registration):
        self.TargetCoilAssociation[coil_name] = None
        self.SaveState()

    def DeleteSelectCoil(self, coil_name):
        self.TargetCoilAssociation.pop(coil_name, None)
        self.SaveState()

    def RenameSelectCoil(self, coil_name, new_coil_name):
        self.TargetCoilAssociation[new_coil_name] = self.TargetCoilAssociation.pop(coil_name)
        self.SaveState()

    def SaveState(self) -> None:
        state = [marker.to_dict() for marker in self.list]
        session = ses.Session()
        session.SetState("markers", state)

    def LoadState(self) -> None:
        session = ses.Session()
        state = session.GetState("markers")

        if state is None:
            return

        for d in state:
            marker = Marker().from_dict(d)
            self.AddMarker(marker, render=False)

    def AddMarker(self, marker: Marker, render: bool = True, focus: bool = False) -> None:
        """
        Given a marker object, add it to the list of markers and render the new marker.

        If focus is True, the the new marker will get the focus on the marker list.
        """
        if marker.marker_uuid == "":
            marker.marker_uuid = str(uuid.uuid4())

        marker.marker_id = len(self.list)
        self.list.append(marker)

        Publisher.sendMessage("Add marker", marker=marker, render=render, focus=focus)

        if marker.is_target:
            self.SetTarget(marker.marker_id, check_for_previous=False, render=render)

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

    def SetTarget(
        self, marker_id: int, check_for_previous: bool = True, render: bool = True
    ) -> None:
        # Set robot objective to NONE when a new target is selected. This prevents the robot from
        # automatically moving to the new target (which would be the case if robot objective was previously
        # set to TRACK_TARGET). Preventing the automatic moving makes robot movement more explicit and predictable.
        self.robot.GetActive().SetObjective(RobotObjective.NONE)
        marker = self.list[marker_id]
        if check_for_previous:
            # Check multitarget mode
            if self.multitarget:
                if marker.coil not in self.accepted_coils:
                    return
                prev_target = self.FindTarget(marker.coil)
            else:
                prev_target = self.FindTarget()

            # If the new target is same as the previous do nothing.
            if prev_target and prev_target.marker_id == marker_id:
                return

            # Unset the previous target
            if prev_target is not None:
                self.UnsetTarget(prev_target.marker_id)

        # Set new target
        marker.is_target = True
        coil_name = marker.coil
        self.TargetCoilAssociation[coil_name] = marker_id
        Publisher.sendMessage("Update main coil by target", coil_name=coil_name)

        Publisher.sendMessage(
            "Set target", marker=marker, robot_ID=self.robot.GetActive().robot_name
        )

        # When setting a new target, automatically switch into target mode. Note that the order is important here:
        # first set the target, then move into target mode.
        Publisher.sendMessage("Press target mode button", pressed=True)

        if render:
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

    def UnsetTarget(self, marker_id: int) -> None:
        marker = self.list[marker_id]
        marker.is_target = False
        self.TargetCoilAssociation[marker.coil] = None

        Publisher.sendMessage(
            "Unset target", marker=marker, robot_ID=self.robot.GetActive().robot_name
        )

        self.SaveState()

    def UnsetPointOfInterest(self, marker_id: int) -> None:
        marker = self.list[marker_id]
        marker.is_point_of_interest = False

        Publisher.sendMessage("Set target transparency", marker=marker, transparent=False)
        Publisher.sendMessage("Unset point of interest", marker=marker)

        self.SaveState()

    def FindTarget(
        self, coil_name: Optional[str] = None, multiple: bool = False
    ) -> Union[None, List[Marker], Marker]:
        """
        Return the markers currently selected as target.
        """

        markers_id = []
        if coil_name:
            marker_id = self.TargetCoilAssociation.get(coil_name, None)

            if marker_id is not None:
                markers_id.append(marker_id)
        else:
            for id in list(self.TargetCoilAssociation.values()):
                if id is not None:
                    markers_id.append(id)

        if 0 <= len(markers_id) < len(self.list):
            if len(markers_id) == 0:
                return None
            elif multiple:
                return [self.list[id] for id in markers_id]
            else:
                return self.list[markers_id[0]]

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

    def ChangeCoilAssociate(self, marker: Marker, new_coil) -> None:
        self.UnsetTarget(marker_id=Marker.marker_id)
        marker.coil = new_coil
        self.SetTarget(marker_id=Marker.marker_id)
        Publisher.sendMessage("Update marker associate coil", marker=marker)
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

    def CreateCoilTargetFromLandmark(self, marker: Marker, coil="") -> None:
        new_marker = marker.duplicate()

        self.transformator.ProjectToScalp(
            marker=new_marker,
            # We are projecting the marker that is on the brain surface; hence, project to the opposite side
            # of the scalp because the normal vectors are unreliable on the brain side of the scalp.
            opposite_side=True,
        )
        new_marker.marker_type = MarkerType.COIL_TARGET
        new_marker.label = self.GetNextMarkerLabel()
        new_marker.coil = coil

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

    def ResetTargets(self):
        for marker_id in list(self.TargetCoilAssociation.values()):
            if marker_id is not None:
                # Disable target
                self.UnsetTarget(marker_id)

        # Stop navigation
        Publisher.sendMessage("Press navigation button", cond=False)
