import sys

import serial
import usb.core
import usb.util
import wx
import numpy as np
from wx.lib.pubsub import pub as Publisher

import gui.dialogs as dlg

try:
    import ClaronTracker as mct
except ImportError:
    print 'The ClaronTracker library is not installed'


class Tracker:
    def __init__(self, trck_id):

        self.trck_init = None
        print "This is the tracker selected!"

        if trck_id == 0:
            trck_init = self.ClaronTracker()
        elif trck_id == 1:
            trck_init = self.PlhFastrak()
        elif trck_id == 2:
            trck_init = self.PlhIsotrakII()
        elif trck_id == 3:
            trck_init = self.PlhPatriot()
        elif trck_id == 4:
            trck_init = self.ZebrisCMS20()

        self.trck_init = trck_init

    def ClaronTracker(self):
        print "CLARON"
        return 0

    def PlhFastrak(self):
        print "FASTRAK"
        return 1

    def PlhIsotrakII(self):
        print "ISOTRAKII"
        return 2

    def PlhPatriot(self):
        print "PATRIOT"
        return 3

    def ZebrisCMS20(self):
        print "ZEBRIS"
        return 4


class Coordinates:
    def __init__(self, trck_init, trck, ref_mode):
        # Module to get coordinates from spatial trackers

        self.__bind_events()
        self.coord = None

        # self.coordTT = [0,0,0]
        # self.coordcoil = [0,0,0]
        # self.MTC_status = None
        # Publisher.sendMessage('Update MTC status')
       
        if trck == 0:
            self.coord = self.PolhemusISO(trck_init, ref_mode)
        elif trck == 1:
            self.coord = self.Polhemus(trck_init, ref_mode)
        elif trck == 2:
            self.coord = self.Claron(trck_init)
        elif trck == 3:
            self.coord = self.Zebris(trck_init)
            
    def __bind_events(self):
        Publisher.subscribe(self.__update_points_MTC, 'Update MTC position')
        Publisher.subscribe(self.__update_status_MTC, 'Update MTC status 2')   
        Publisher.subscribe(self.__update_points_coil, 'Update coil position')  
        
        
    def __update_status_MTC(self, pubsub_evt):  
        self.MTC_status =  pubsub_evt.data

    def __update_points_MTC(self, pubsub_evt): 
        self.coordTT = pubsub_evt.data

    def __update_points_coil(self, pubsub_evt): 
        self.coordcoil = pubsub_evt.data     
             
    def PolhemusISO(self, trck_init, ref_mode):
        # mudanca para fastrak - ref 1 tem somente x, y, z
        # aoflt -> 0:letter 1:x 2:y 3:z

        trck_init.write("Y")
        trck_init.write("P")
        lines = trck_init.readlines()

        coord = None

        if lines[0][0] != '0':
            dlg.TrackerNotConnected(0)
            print "The Polhemus is not connected!"
        else:
            for s in lines:
                if s[1] == '1':
                    line1 = s
                elif s[1] == '2':
                    line2 = s
                        
            # single ref mode
            if ref_mode == 0:
                line1 = line1.replace('-', ' -')
                line1 = [s for s in line1.split()]
                j = 0
                while j == 0:
                    try:
                        plh1 = [float(s) for s in line1[1:len(line1)]]
                        j = 1
                    except ValueError:
                        trck_init.write("P")
                        line1 = trck_init.readline()
                        line1 = line1.replace('-', ' -')
                        line1 = [s for s in line1.split()]
                        print "Trying to fix the error!!"
            
                coord = plh1[0:6]   
        return coord

    def Polhemus(self, trck_init, ref_mode):

        # If Polhemus is not connected return this coord

        endpoint = trck_init[0][(0, 0)][0]
        trck_init.write(0x2, "P")

        coord = None
        data1 = None
        data2 = None

        if ref_mode == 0:
            # TODO: Verify which is the best way to convert the string in line1
            data1 = trck_init.read(endpoint.bEndpointAddress,
                                   endpoint.wMaxPacketSize)

            astr = [chr(s) for s in data1]
            aofloat = str()
            for i in range(0, len(astr)):
                aofloat += astr[i]
            aostr = [s for s in aofloat.split()]

            line1 = ''

            for j in range(0, 7):
                line1 = line1+aostr[j] + ' '

            line1 = [s for s in line1.split()]
            coord = [float(s) for s in line1[1:len(line1)]]

            inch2mm = 25.4

            if not coord:
                print "error 0,0,0"
                coord = np.zeros((1, 6))

            coord = (float(coord[0])*inch2mm, float(coord[1])*inch2mm,
                     float(coord[2])*(-inch2mm), float(coord[3]),
                     float(coord[4]), float(coord[5]))

        else:
            data = trck_init.read(endpoint.bEndpointAddress,
                                  endpoint.wMaxPacketSize)
            data2 = trck_init.read(endpoint.bEndpointAddress,
                                   endpoint.wMaxPacketSize)

            astr = [chr(s) for s in data]
            aofloat = str()
            for i in range(0, len(astr)):
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
            a = np.radians(plh2[3])
            b = np.radians(plh2[4])
            g = np.radians(plh2[5])

            angs1 = plh1[3:6]
            plh1 = np.matrix(plh1[0:3])
            plh1.reshape(3, 1)
            plh2 = np.matrix(plh2[0:3])
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
                coord = (mtc.PositionTooltipX, mtc.PositionTooltipY, mtc.PositionTooltipZ,mtc.AngleX,mtc.AngleY,mtc.AngleZ)
                i = 1
            except AttributeError:
                print "deu erro, mas jah jah passa!"

        coord = (mtc.PositionTooltipX, mtc.PositionTooltipY, mtc.PositionTooltipZ,mtc.AngleX,mtc.AngleY,mtc.AngleZ)
        x = 10.0
        y = 10.0
        z = -10.0
        print coord                     
        # Os fatores subtraidos (-0.36, 3.12, 1.88) representam um offset para navegacao com a bobina, caso for navegar so com a probe excluir esses fatores
        try:
        #if self.MTC_status == True and self.coordTT != None and self.coordcoil != None:
                fact_coil1= self.coordTT[0] - self.coordcoil[0]
                fact_coil2= self.coordTT[1] - self.coordcoil[1]
                fact_coil3= self.coordTT[2] - self.coordcoil[2]
                fact_coil=[fact_coil1,fact_coil2,fact_coil3]
                coord = (float(coord[0])*x + fact_coil[0], float(coord[1])*y + fact_coil[1], float(coord[2])*z + fact_coil[2],float(coord[3]),float(coord[4]),float(coord[5]))
                #coord = (float(coord[0])*x + 0.36, float(coord[1])*y -3.12, float(coord[2])*z -1.88,float(coord[3]),float(coord[4]),float(coord[5]))
        #else:
        except:
            coord = (float(coord[0])*x , float(coord[1])*y , float(coord[2])*z,float(coord[3]),float(coord[4]),float(coord[5]))
        return coord
    
    def Zebris(self, trk_init, ref_mode_aux):
        dlg.TrackerNotConnected(3)
        return (0, 0, 0)
    
    def Returns(self):
        return self.coord
#TODO: Precisa dessa funcao returns.. num da pra usar a propria de cada um direto na func de escolher o navegador (interrogacao)

# it was inside Polhemus
# plh1 = [float(s) for s in line1[1:7]]
# plh2 = [float(s) for s in line2[1:len(line2)]]

# a (alfa) -> rotation around x, b (beta) -> rotation around y, g (gama) ->rotation around z
# a = radians(plh2[3])
# b = radians(plh2[4])
# g = radians(plh2[5])
# angs1 = plh1[3:6]
# plh1 = matrix(plh1[0:3])
# plh1.reshape(3, 1)
# plh2 = matrix(plh2[0:3])
# plh2.reshape(3, 1)
# vet = plh1 - plh2
# vet=plh1
# vet = vet.reshape(3, 1)
# Attitude Matrix given by Patriot Manual
# Mrot = matrix([[cos(a)*cos(b), sin(b)*sin(g)*cos(a) - cos(g)*sin(a), cos(a)*sin(b)*cos(g) + sin(a)*sin(g)],
#                [cos(b)*sin(a), sin(b)*sin(g)*sin(a) + cos(g)*cos(a), cos(g)*sin(b)*sin(a) - sin(g)*cos(a)],
#                [-sin(b), sin(g)*cos(b), cos(b)*cos(g)]])

# coord_fin = (Mrot.T)*vet
# coord = (coord_fin[0], coord_fin[1], coord_fin[2], angs1[0],
#          angs1[1], angs1[2])