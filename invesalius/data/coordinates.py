#import ClaronTracker
from numpy import *
import usb.core
import serial
import usb.util
import sys
import gui.dialogs as dlg

class Tracker_Init: 
    def Claron_init(self):
        mtc = ClaronTracker.ClaronTracker()
        mtc.CalibrationDir = "C:\CalibrationFiles"
        mtc.MarkerDir = "C:\Markers"
        mtc.NumberFramesProcessed = 10
        mtc.FramesExtrapolated = 0
        mtc.Initialize()
        if mtc.GetIdentifyingCamera():
            print "eh nois!"
            #mtc.Run()
        else:
            dlg.TrackerNotConnected(2)
            print "The Claron MicronTracker is not connected!"
        return mtc
    def PolhemusISO_init(self):
        plh = serial.Serial(0, baudrate = 115200, timeout=0.2)
        return plh
    
    def Polhemus_init(self):
        dev = usb.core.find(idVendor=0x0F44, idProduct=0xEF12)
        if dev is None:
            dlg.TrackerNotConnected(1)
            raise ValueError('Device not found')  
        try:
            cfg = dev.get_active_configuration()
            for i in cfg:
                for x in i:
                    x = x        
            dev.set_configuration()
        except usb.core.USBError as e:
            sys.exit("Could not set configuration: %s" % str(e))
        return dev
        
    def Zebris_init(self):
        dlg.TrackerNotConnected(3)
        return
        

class Coordinates:
    def __init__(self, trk_init, tracker, ref_mode):
        trk_init = trk_init
        tracker = tracker
        self.ref_mode = ref_mode
        self.coord = None
        
        if tracker == 0:
            self.coord = self.PolhemusISO(trk_init)
        elif tracker == 1:
            self.coord = self.Polhemus(trk_init)
        #elif self.tracker == 1:
        #self.coord = self.Polhemus(self.ref_mode)
        elif tracker == 2:
            self.coord = self.Claron(trk_init)
        elif self.tracker == 3:
            self.coord = self.Zebris(trk_init)
            
    def PolhemusISO(self, trk_init):
        ser = trk_init
        #if polhemus is not connected return this coord
        coord = None
        ser.write("Y")
        ser.write("P")  
        lines = ser.readlines()
   
        if lines[0][0] != '0':
            dlg.TrackerNotConnected(0)
            print "The Polhemus is not connected!"
        else:
            for s in lines:
                if s[1] == '1':
                    line1 = s
                elif s[1] == '2':
                    line2 = s
                        
            #single ref mode
            if self.ref_mode == 0:
                line1 = line1.replace('-', ' -')
                line1 = [s for s in line1.split()]
                j = 0
                while j == 0:
                    try:
                        #mudanca para fastrak - ref 1 tem somente x, y, z
                        #aoflt -> 0:letter 1:x 2:y 3:z
                        plh1 = [float(s) for s in line1[1:len(line1)]]
                        j = 1
                    except ValueError:
                        ser.write("P")
                        line1 = ser.readline()
                        line2 = ser.readline()
                        line1 = line1.replace('-', ' -')
                        line1 = [s for s in line1.split()]
                        print "Trying to fix the error!!"
            
                coord = plh1[0:6]   
        return coord         
    def Polhemus(self, trk_init):
            dev = trk_init
            #if polhemus is not connected return this coord
            endpoint = dev[0][(0,0)][0]
            coord = None
            dev.write(0x2,"P")   
       
            data = None
            data2 = None        
            
            data = dev.read(endpoint.bEndpointAddress,
                                               endpoint.wMaxPacketSize)
            data2 = dev.read(endpoint.bEndpointAddress,
                                               endpoint.wMaxPacketSize)
               
            astr = [chr(s) for s in data] 
            aofloat = str()
            for i in range(0,len(astr)):
                     aofloat += astr[i]        
            aostr = [s for s in aofloat.split()]
        
            astr2 = [chr(s) for s in data2] 
            aofloat2 = str()
            for i in range(0,len(astr2)):
                     aofloat2 += astr2[i]         
            aostr2 = [s for s in aofloat2.split()]
            
            aofloatf= aofloat+aofloat2
            
            aostrf = [s for s in aofloatf.split()]
            
            line1=line2=''
            for i in range (0,len(aostrf)):
                if aostrf[i]=='01':
                    for y in range (0,7):
                        line1=line1+aostrf[y]+' '
                    for y in range (7,14):
                        line2=line2+aostrf[y]+' '
                           
            line1 = [s for s in line1.split()]
            line2 = [s for s in line2.split()]
          
            plh1 = [float(s) for s in line1[1:len(line1)]]
            #plh1 = [float(s) for s in line1[1:7]]
            plh2 = [float(s) for s in line2[1:len(line2)]]
                                                 
            #a (alfa) -> rotation around x, b (beta) -> rotation around y, g (gama) ->rotation around z
            a = radians(plh2[3])
            b = radians(plh2[4])
            g = radians(plh2[5])
                    
            angs1 = plh1[3:6]
            plh1 = matrix(plh1[0:3])
            plh1.reshape(3, 1)
            plh2 = matrix(plh2[0:3])
            plh2.reshape(3, 1)
            
            vet = plh1 - plh2
            vet = vet.reshape(3, 1)
                            
            #Attitude Matrix given by Patriot Manual
            Mrot = matrix([[cos(a)*cos(b), sin(b)*sin(g)*cos(a) - cos(g)*sin(a), cos(a)*sin(b)*cos(g) + sin(a)*sin(g)],
                               [cos(b)*sin(a), sin(b)*sin(g)*sin(a) + cos(g)*cos(a), cos(g)*sin(b)*sin(a) - sin(g)*cos(a)],
                               [-sin(b), sin(g)*cos(b), cos(b)*cos(g)]])
                    
            coord_fin = (Mrot.T)*vet
                    
            coord = coord_fin[0], coord_fin[1], coord_fin[2], angs1[0], angs1[1], angs1[2]
            #fastrak nao precisa colocar ref na ponta
            #ser.write("Y")
            #coloquei o close na selecao dos rastreadores
            #ser.close()
            
            #fastrak ja esta em cm, transforma pra mm
            #x = 10.0
            #y = 10.0
            #z = -10.0
            x = 25.4
            y = 25.4
            z = -25.4
            
            if not coord:
                print "ahh meu amigo... eh tudo zero viu"
                coord = (0, 0, 0, 0, 0, 0)
            
            coord = (float(coord[0])*x, float(coord[1])*y, float(coord[2])*z, float(coord[3]), float(coord[4]), float(coord[5]))
            return coord
    
   
    def Claron(self, trk_init):
        mtc = trk_init
        i = 0
        while i == 0:             
            try:
                mtc.Run()
                coord = (mtc.PositionTooltipX, mtc.PositionTooltipY, mtc.PositionTooltipZ)
                i = 1
            except AttributeError:
                print "deu erro, mas jah jah passa!"

        coord = (mtc.PositionTooltipX, mtc.PositionTooltipY, mtc.PositionTooltipZ)
        
        x = 10.0
        y = 10.0
        z = -10.0
        coord = (float(coord[0])*x, float(coord[1])*y, float(coord[2])*z)
        return coord
    
    def Zebris(self, trk_init, ref_mode_aux):
        dlg.TrackerNotConnected(3)
        return (0, 0, 0)
    
    def Returns(self):
        return self.coord
#TODO: Precisa dessa funcao returns.. num da pra usar a propria de cada um direto na func de escolher o navegador (interrogacao)
