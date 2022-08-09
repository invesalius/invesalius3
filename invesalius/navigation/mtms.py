import win32com.client

import numpy as np
import time

import invesalius.data.coordinates as dco
import invesalius.data.coregistration as dcr

class mTMS():
    def __init__(self):
        mtms_path = 'C:\\mTMS\\Labview\\Builds\\mTMS 3.1'
        vipath = mtms_path + '\\mTMS ActiveX Server\\mTMS ActiveX Server.exe\\mTMS ActiveX Server.vi'
        # Connect to the ActiveX server
        mtms_app = win32com.client.Dispatch('MTMSActiveXServer.Application')
        self.vi = mtms_app.getvireference(vipath)
        # Log name
        self.vi.SetControlValue('New Log name', 'Experiment 1a')
        name = self.vi.GetControlValue('New Log name')
        print(name)

    def UpdateTarget(self, coil_pose, brain_target):
        self.coil_pose = coil_pose
        self.brain_target = brain_target
        self.icp_fre = None
        distance = dcr.ComputeRelativeDistanceToTarget(target_coord=coil_pose, img_coord=brain_target)
        offset = self.GetOffset(distance)
        print(offset)
        mTMS_index_target = self.FindmTMSParameters([int(x) for x in offset])
        print(mTMS_index_target)
        if len(mTMS_index_target[0]):
            self.SendToMTMS(mTMS_index_target[0])
        else:
            print("Target is not valid")

    def GetOffset(self, distance):
        print(distance)
        offset_xy = [int(np.round(x / 3) * 3) for x in distance[:2]]
        offset_rz = int(np.round(distance[5] / 15) * 15)

        return [offset_xy[0], offset_xy[1], offset_rz]

    def FindmTMSParameters(self, offset):
        fname = 'C:\\mTMS\\mTMS parameters\\PP\\PP31 5-coil grid.txt'

        with open(fname, 'r') as the_file:
            all_data = [line.strip() for line in the_file.readlines()]
            data = all_data[18:]
        data = np.array([line.split('\t') for line in data])

        offset = offset
        separator = '_'
        target = separator.join(['{}'.format(x) for x in offset])
        return np.where(data[:, 0] == target)

    def SendToMTMS(self, target):
        # Manipulate intensity
        intensity = self.vi.GetControlValue('Get Intensity')
        print("Intensity: ", str(intensity))
        #self.vi.SetControlValue('New Intensity', 40)
        #self.vi.SetControlValue('Set Intensity', True)

        # Update the Pulse - parameters row and wait until the change has been processed
        self.vi.SetControlValue('New Pulse-parameters row', int(target));
        self.vi.SetControlValue('Set Pulse-parameters row', True);
        print("Updating brain target...")
        while self.vi.GetControlValue('Set Pulse-parameters row'):
            pass
        time.sleep(0.1)
        print("Charging capacitors...")
        while not self.vi.GetControlValue('Get Ready to stimulate'):
            pass
        # Stimulate
        print("Stimulating")
        self.vi.SetControlValue('Stimulate', True)
