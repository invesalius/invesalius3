import threading

import serial
import wx
from wx.lib.pubsub import pub as Publisher
from numpy import *
from math import sqrt
from time import sleep

import data.coordinates as co

class Corregister(threading.Thread):
    
    def __init__(self, bases, nav_id, tracker_info):
        threading.Thread.__init__(self)
        self.Minv = bases[0]
        self.N = bases[1]
        self.q1 = bases[2]
        self.q2 = bases[3]
        self.nav_id = nav_id
        self.tracker_init = tracker_info[0]
        self.tracker = tracker_info[1]
        self.tracker_mode = tracker_info[2]
        self._pause_ = 0
        self.start()
        
    def stop(self):
        # Stop neuronavigation
        self._pause_ = 1
       
    def run(self):
        
        while self.nav_id == True:
            #Coordinate System Change calculus
            trck = co.Coordinates(self.tracker_init, self.tracker, self.tracker_mode).Returns()
            tracker = matrix([[trck[0]], [trck[1]], [trck[2]]])            
            img = self.q1 + (self.Minv*self.N)*(tracker - self.q2)
            coord = float(img[0]), float(img[1]), float(img[2]), trck[3], trck[4], trck[5]
            coord_xyz = coord[0:3] 
            #ps.Publisher().sendMessage('Set ball reference position', coord)
            #f_angles = trck[3:6]
            wx.CallAfter(Publisher.sendMessage, 'Set camera in volume', coord)
            #wx.CallAfter(ps.Publisher().sendMessage, 'Change Coil Angle', f_angles)
            wx.CallAfter(Publisher.sendMessage, 'Co-registered Points', coord_xyz)
            sleep(0.175) #Melhor valor obtido experimentalmente

            if self._pause_:
                return
