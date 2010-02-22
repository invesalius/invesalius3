import threading
import serial
import wx.lib.pubsub as ps
from numpy import *
from math import sqrt
from time import sleep
import project

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
               
        ser = serial.Serial(0)
        ser.write("u")       
        ser.write("P")
        str = ser.readline()
        str = str.replace("\r\n","")
        str = str.replace("-"," -")
        aostr = [s for s in str.split()]
        #aoflt -> 0:letter 1:x 2:y 3:z
        aoflt = [float(aostr[1]), float(aostr[2]), float(aostr[3]),
                  float(aostr[4]), float(aostr[5]), float(aostr[6])]      
        ser.close()
        
        spacingx, spacingy, spacingz = project.Project().imagedata.GetSpacing()
        x = 10.0/spacingx
        y = 10.0/spacingy
        z = 10.0/spacingz

        coord = (aoflt[0]*x, aoflt[1]*y, aoflt[2]*z)
        return coord
       
    def run(self):
             
        while self.flag == True:
            #trck = self.Coordinates()
            for i in range(1, 20):
                x = float(i)
                y = sqrt(500.0 - x**2)
                z = float(i) - 4.0
                
                tracker = matrix([[x], [y], [z]])
                #tracker = matrix([[trck[0]], [trck[1]], [trck[2]]])            
                img = self.q1 + (self.Minv*self.N)*(tracker - self.q2)
                
                coord = [float(img[0]), float(img[1]), float(img[2])]
                coord_cam = (float(img[0]), float(img[1]), float(img[2]))

                #coord = img.tolist()
                ps.Publisher().sendMessage('Co-registered Points', coord)
                ps.Publisher().sendMessage('Set camera in volume', coord_cam)
                ps.Publisher().sendMessage('Render volume viewer')
                ps.Publisher().sendMessage('Update slice viewer')
                sleep(1.0)
                if self._pause_:
                    return