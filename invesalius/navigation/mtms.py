import random
import time

import numpy as np
import pandas as pd
import win32com.client

import invesalius.data.coregistration as dcr


class mTMS:
    def __init__(self):
        # TODO: create dialog to input mtms_path and vi
        mtms_path = "C:\\mTMS\\Labview\\Builds\\mTMS 3.1 hack"
        vipath = (
            mtms_path + "\\mTMS ActiveX Server\\mTMS ActiveX Server.exe\\mTMS ActiveX Server.vi"
        )
        # Connect to the ActiveX server
        mtms_app = win32com.client.Dispatch("MTMSActiveXServer.Application")
        self.vi = mtms_app.getvireference(vipath)
        # Log name
        self.log_name = "mtms_subject_00_run_0"
        # self.vi.SetControlValue(self.log_name, 'Experiment 1a')
        self.intensity = self.vi.GetControlValue("Get Intensity")
        # self.intensity = 20

        self.df = pd.DataFrame(
            [], columns=["mTMS_target", "brain_target(nav)", "coil_pose(nav)", "intensity"]
        )

    def CheckTargets(self, coil_pose, brain_target_list):
        for brain_target in brain_target_list:
            distance = dcr.ComputeRelativeDistanceToTarget(
                target_coord=brain_target, img_coord=coil_pose
            )
            offset = self.GetOffset(distance)
            mTMS_target, mTMS_index_target = self.FindmTMSParameters(offset)
            if not len(mTMS_index_target[0]):
                print("Not possible to stimulate the target: ", offset)
                return False
        return True

    def UpdateTargetSequence(self, coil_pose, brain_target_list):
        if brain_target_list:
            # Do I really need to check this? Or I can apply only the possible stimuli?
            if self.CheckTargets(coil_pose, brain_target_list):
                number_of_stim = 3
                randomized_brain_target_list = brain_target_list.copy()
                random.shuffle(randomized_brain_target_list)
                for brain_target in randomized_brain_target_list:
                    for x in range(number_of_stim):
                        self.UpdateTarget(coil_pose, brain_target)
                        time.sleep(random.randrange(300, 500, 1) / 100)
                self.SaveSequence()

    def UpdateTarget(self, coil_pose, brain_target):
        coil_pose_flip = coil_pose.copy()
        brain_target_flip = brain_target.copy()
        coil_pose_flip[1] = -coil_pose_flip[1]
        brain_target_flip[1] = -brain_target_flip[1]
        distance = dcr.ComputeRelativeDistanceToTarget(
            target_coord=coil_pose_flip, img_coord=brain_target_flip
        )
        offset = self.GetOffset(distance)
        mTMS_target, mTMS_index_target = self.FindmTMSParameters(offset)
        if len(mTMS_index_target[0]):
            self.SendToMTMS(mTMS_index_target[0] + 1)
            new_row = {
                "mTMS_target": mTMS_target,
                "brain_target(nav)": brain_target_flip,
                "coil_pose(nav)": coil_pose_flip,
                "intensity": self.intensity,
            }
            self.df = self.df.append(pd.DataFrame([new_row], columns=self.df.columns))
        else:
            print("Target is not valid. The offset is: ", offset)

    def GetOffset(self, distance):
        offset_xy = [int(np.round(x)) for x in distance[:2]]
        offset_rz = int(np.round(distance[-1] / 15) * 15)
        offset = [-int(offset_xy[1]), int(offset_xy[0]), int(offset_rz)]
        return offset

    def FindmTMSParameters(self, offset):
        # fname = "C:\\mTMS\\mTMS parameters\\PP\\PP31 mikael 1mm 15deg 5-coil grid.txt"
        fname = self.vi.GetControlValue("Get Pulse-parameters file")
        with open(fname) as the_file:
            all_data = [line.strip() for line in the_file.readlines()]
            data = all_data[18:]
        data = np.array([line.split("\t") for line in data])

        separator = "_"
        target = separator.join([f"{x}" for x in offset])
        target_index = np.where(data[:, 0] == target)

        return target, target_index

    def SendToMTMS(self, target):
        # Manipulate intensity
        self.intensity = self.vi.GetControlValue("Get Intensity")
        print("Intensity: ", str(self.intensity))
        # self.vi.SetControlValue('New Intensity', 40)
        # self.vi.SetControlValue('Set Intensity', True)

        # Update the Pulse - parameters row and wait until the change has been processed
        self.vi.SetControlValue("New Pulse-parameters row", int(target))
        self.vi.SetControlValue("Set Pulse-parameters row", True)
        print("Updating brain target: ", int(target))
        while self.vi.GetControlValue("Set Pulse-parameters row"):
            pass
        time.sleep(0.3)
        print("Charging capacitors...")
        while not self.vi.GetControlValue("Get Ready to stimulate"):
            pass
        # TODO: remove stimulation from here. The user should use the mtms interface to perform the stimuli
        # Stimulate
        print("Stimulating")
        self.vi.SetControlValue("Stimulate", True)

    def SaveSequence(self):
        timestamp = time.localtime(time.time())
        stamp_date = f"{timestamp.tm_year:0>4d}{timestamp.tm_mon:0>2d}{timestamp.tm_mday:0>2d}"
        stamp_time = f"{timestamp.tm_hour:0>2d}{timestamp.tm_min:0>2d}{timestamp.tm_sec:0>2d}"
        sep = "_"
        parts = [stamp_date, stamp_time, self.log_name, "sequence"]
        default_filename = sep.join(parts) + ".csv"
        self.df.to_csv(default_filename, sep="\t", encoding="utf-8", index=False)
