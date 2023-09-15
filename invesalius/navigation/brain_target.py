import numpy as np

import invesalius.data.coregistration as dcr


class BrainTarget:
    def __init__(self, pose):
        self.pose = pose

    def ComputeOffsetsRelativeToCoil(self, coil_pose):
        coil_pose_flip = coil_pose.copy()
        brain_target_flip = self.pose.copy()

        # TODO: Document why the y-coordinate is flipped.
        coil_pose_flip[1] = -coil_pose_flip[1]
        brain_target_flip[1] = -brain_target_flip[1]

        distances = dcr.ComputeRelativeDistanceToTarget(target_coord=coil_pose_flip, img_coord=brain_target_flip)

        # Compute offsets in millimeters.
        offset_xy = [int(np.round(x)) for x in distances[:2]]
        offset_rz = int(np.round(distances[-1] / 15) * 15)

        # TODO: Document why the coordinates are flipped.
        offsets = [-int(offset_xy[1]), int(offset_xy[0]), int(offset_rz)]

        return offsets
