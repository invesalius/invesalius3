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
        self.M = bases[0]
        self.Minv = bases[1]
        self.N = bases[2]
        self.Ninv = bases[3]
        self.q1 = bases[4]
        self.q2 = bases[5]
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
        #Image limits to use in simulation
        #bounds = array(project.Project().imagedata.GetBounds())
        #im_simu = bounds
        #im_simu[0] = bounds[0] - 10.0
        #im_simu[2] = bounds[2] - 10.0
        #im_simu[4] = bounds[4] - 10.0
        
        while self.flag == True:
            #Neuronavigation with Polhemus
            trck = self.Coordinates()
            tracker = matrix([[trck[0]], [trck[1]], [trck[2]]])            
            img = self.q1 + (self.Minv*self.N)*(tracker - self.q2)
            coord = [float(img[0]), float(img[1]), float(img[2])]
            ps.Publisher().sendMessage('Co-registered Points', coord)

            if self._pause_:
                return
            
            #Loop for simulate Polhemus movement and Neuronavigation
            #for i in range(0, 5, 2):
            #    while im_simu[i] < (bounds[i+1]+10.0):
            #        im_init = matrix([[im_simu[0]], [im_simu[2]], [im_simu[4]]])          
            #        #mudanca coordenada img2plh
            #        tr_simu = self.q2 + (self.Ninv*self.M)*(im_init - self.q1)
            #        #mudanca coordenada plh2img
            #        img_final = self.q1 + (self.Minv*self.N)*(tr_simu - self.q2)
            #        #publica as alteracoes que devem ser feitas nas fatias
            #        coord = [float(img_final[0]), float(img_final[1]), float(img_final[2])]
            #        ps.Publisher().sendMessage('Co-registered Points', coord)
            #        im_simu[i] = im_simu[i] + 4.0
            #        if self._pause_:
            #            return
