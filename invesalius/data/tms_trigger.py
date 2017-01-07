import threading
from time import sleep

import wx
from wx.lib.pubsub import pub as Publisher
import serial

class Trigger(threading.Thread):
    # Thread created to update the coordinates with the fiducial points
    # coregistration method while the Navigation Button is pressed.
    # Sleep function in run method is used for better real-time navigation

    def __init__(self, nav_id):
        threading.Thread.__init__(self)
        self.TTL = serial.Serial('COM1', baudrate=115200, timeout=0)
        self.nav_id = nav_id
        self._pause_ = False
        self.start()

    def stop(self):
        self.TTL.close()
        self._pause_ = True
        
    def run(self):
        while self.nav_id:
            lines = self.TTL.readlines()
            if lines != []:
                wx.CallAfter(Publisher.sendMessage, 'Create markers')
                lines = []
            sleep(0.175)
            if self._pause_:
                return

