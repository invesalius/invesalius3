import threading

import serial
import wx
import wx.lib.pubsub as ps

from numpy import *
from math import sqrt
from time import sleep

class Corregister(threading.Thread):
    
    def __init__(self, bases, flag):
        threading.Thread.__init__(self)
        self.Minv = bases[0]
        self.N = bases[1]
        self.q1 = bases[2]
        self.q2 = bases[3]
        self.flag = flag
        self._pause_ = 0
        self.start()
        
    def stop(self):
        # Stop neuronavigation
        self._pause_ = 1
        
    def Coordinates(self):        
        #Get Polhemus points for neuronavigation       
        ser = serial.Serial(0)
        ser.write("Y")       
        ser.write("P")
        str = ser.readline()
        ser.write("Y")
        str = str.replace("\r\n","")
        str = str.replace("-"," -")
        aostr = [s for s in str.split()]
        #aoflt -> 0:letter 1:x 2:y 3:z
        aoflt = [float(aostr[1]), float(aostr[2]), float(aostr[3]),
                  float(aostr[4]), float(aostr[5]), float(aostr[6])]      
        ser.close()
        
        #Unit change: inches to millimeters
        x = 25.4
        y = 25.4
        z = -25.4

        coord = (aoflt[0]*x, aoflt[1]*y, aoflt[2]*z)
        return coord
       
    def run(self):
        while self.flag == True:
            #Neuronavigation with Polhemus
            trck = self.Coordinates()
            tracker = matrix([[trck[0]], [trck[1]], [trck[2]]])            
            img = self.q1 + (self.Minv*self.N)*(tracker - self.q2)
            coord = [float(img[0]), float(img[1]), float(img[2])]
            coord_cam = float(img[0]), float(img[1]), float(img[2])
            ps.Publisher().sendMessage('Set ball reference position based on bound', coord_cam)
            ps.Publisher().sendMessage('Set camera in volume', coord_cam)
            wx.CallAfter(ps.Publisher().sendMessage, 'Render volume viewer')
            wx.CallAfter(ps.Publisher().sendMessage, 'Co-registered Points', coord)
            sleep(0.005)

            if self._pause_:
                return
