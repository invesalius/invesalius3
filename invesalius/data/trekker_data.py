import threading
from time import sleep

import numpy as np
import wx
from wx.lib.pubsub import pub as Publisher
import vtk

import invesalius.data.coordinates as dco
import invesalius.data.transformations as tr

# TODO: Optimize navigation thread. Remove the infinite loop and optimize sleep.


class TrekkerStart(threading.Thread):
    """
    Thread to update the coordinates with the fiducial points
    co-registration method while the Navigation Button is pressed.
    Sleep function in run method is used to avoid blocking GUI and
    for better real-time navigation
    """

    def __init__(self, seed):
        threading.Thread.__init__(self)
        self.seed = seed
        self._pause_ = False
        self.start()

    def stop(self):
        self._pause_ = True

    def run(self):
        # m_change = self.coreg_data[0]
        # obj_ref_mode = self.coreg_data[2]
        #
        # trck_init = self.trck_info[0]
        # trck_id = self.trck_info[1]
        # trck_mode = self.trck_info[2]

        m_change, obj_ref_mode = self.coreg_data
        trck_init, trck_id, trck_mode = self.trck_info

        while self.nav_id:
            coord_raw = dco.GetCoordinates(trck_init, trck_id, trck_mode)

            psi, theta, phi = coord_raw[obj_ref_mode, 3:]
            t_probe_raw = asmatrix(tr.translation_matrix(coord_raw[obj_ref_mode, :3]))

            t_probe_raw[2, -1] = -t_probe_raw[2, -1]

            m_img = m_change * t_probe_raw

            coord = m_img[0, -1], m_img[1, -1], m_img[2, -1], psi, theta, phi

            wx.CallAfter(Publisher.sendMessage, 'Co-registered points', arg=m_img, position=coord)

            # TODO: Optimize the value of sleep for each tracking device.
            sleep(0.175)

            if self._pause_:
                return