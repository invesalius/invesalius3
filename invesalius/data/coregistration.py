import threading
from time import sleep

import numpy
import wx
from wx.lib.pubsub import pub as Publisher

import invesalius.data.coordinates as co


class Coregistration(threading.Thread):
    # Thread created to update the coordinates with the fiducial points
    # co-registration method while the Navigation Button is pressed.
    # Sleep function in run method is used for better real-time navigation

    def __init__(self, bases, nav_id, trck_info):
        threading.Thread.__init__(self)
        self.bases = bases
        self.nav_id = nav_id
        self.trck_info = trck_info
        self._pause_ = False
        self.start()
        
    def stop(self):
        self._pause_ = True
       
    def run(self):
        m_inv = self.bases[0]
        n = self.bases[1]
        q1 = self.bases[2]
        q2 = self.bases[3]
        trck_init = self.trck_info[0]
        trck = self.trck_info[1]
        trck_mode = self.trck_info[2]

        while self.nav_id:
            trck_coord = co.Coordinates(trck_init, trck, trck_mode).Returns()
            trck_xyz = numpy.matrix([[trck_coord[0]], [trck_coord[1]],
                                      [trck_coord[2]]])
            img = q1 + (m_inv*n)*(trck_xyz - q2)

            coord = (float(img[0]), float(img[1]), float(img[2]), trck_coord[3],
                     trck_coord[4], trck_coord[5])

            wx.CallAfter(Publisher.sendMessage, 'Set camera in volume', coord[0:3])
            wx.CallAfter(Publisher.sendMessage, 'Co-registered Points', coord[0:3])
            # TODO: Create flag to check if coil angle must be tracked
            # Code for angle tracking
            # f_angles = trck_coord[3:6]
            # wx.CallAfter(ps.Publisher().sendMessage, 'Change Coil Angle',
            # f_angles)

            sleep(0.175)

            if self._pause_:
                return
