import numpy as np
from wx.lib.pubsub import pub as Publisher

import gui.dialogs as dlg

class Tracker:
    def __init__(self, trck_id):
        if trck_id != 0:
            trck = {1 : self.ClaronTracker,
                    2 : self.PlhFastrak,
                    3 : self.PlhIsotrakII,
                    4 : self.PlhPatriot,
                    5 : self.ZebrisCMS20}

            self.ReturnTracker(trck, trck_id)

        else:
            print "Select Tracker"

    def ClaronTracker(self):
        try:
            import ClaronTracker as mtc
        except ImportError:
            print 'The ClaronTracker library is not installed'

        print "CLARON func"
        return 0

    def PlhFastrak(self):
        import serial
        print "FASTRAK func"
        return 1

    def PlhIsotrakII(self):
        import serial
        print "ISOTRAKII func"
        return 2

    def PlhPatriot(self):
        import sys

        import serial
        import usb.core
        import usb.util

        print "PATRIOT func"
        return 3

    def ZebrisCMS20(self):
        print "ZEBRIS func"
        return 4

    def ReturnTracker(self, trck, trck_id):
        print "Returning"
        print "This is the tracker selected!", trck_id
        return trck[trck_id]()


class Coordinates:
    def __init__(self, trck_init, trck, ref_mode):
        # Module to get coordinates from spatial trackers

        self.__bind_events()
        self.coord = None
        if trck != 0:

            trck_ID = {1 : self.Claron,
                    2 : self.PolhemusFAST,
                    3 : self.PolhemusISO,
                    4 : self.Polhemus,
                    5 : self.Zebris}

            self.coord = trck_ID[trck](trck_init, ref_mode)

        else:
            print "Select Tracker"
            
    def __bind_events(self):
        Publisher.subscribe(self.__update_points_MTC, 'Update MTC position')
        Publisher.subscribe(self.__update_status_MTC, 'Update MTC status 2')   
        Publisher.subscribe(self.__update_points_coil, 'Update coil position')  
        
        
    def __update_status_MTC(self, pubsub_evt):  
        self.MTC_status = pubsub_evt.data

    def __update_points_MTC(self, pubsub_evt): 
        self.coordTT = pubsub_evt.data

    def __update_points_coil(self, pubsub_evt): 
        self.coordcoil = pubsub_evt.data

    def Claron(self, trk_init, ref_mode):
        mtc = trk_init
        i = 0
        # TODO: set a maximum value for the while, ie. use a count and iterate it 10 times
        if ref_mode == 0:
            while i == 0:
                try:
                    mtc.Run()
                    coord = (mtc.PositionTooltipX1, mtc.PositionTooltipY1, mtc.PositionTooltipZ1,
                             mtc.AngleX1, mtc.AngleY1, mtc.AngleZ1)
                    i = 1
                except AttributeError:
                    print "wait, collecting the coordinates ..."

        if ref_mode == 1:
            while i == 0:
                try:
                    mtc.Run()
                    Tooltip1 = array([mtc.PositionTooltipX1, mtc.PositionTooltipY1, mtc.PositionTooltipZ1])
                    Tooltip2 = array([mtc.PositionTooltipX2, mtc.PositionTooltipY2, mtc.PositionTooltipZ2])
                    angs1 = array([mtc.AngleX1, mtc.AngleY1, mtc.AngleZ1])
                    angs2 = array([mtc.AngleX2, mtc.AngleY2, mtc.AngleZ2])
                    i = 1
                except AttributeError:
                    print "wait, collecting the coordinates ..."

            a = radians(angs2[2])
            b = radians(angs2[1])
            g = radians(angs2[0])
            vet = Tooltip1 - Tooltip2
            vet = vet.reshape(3, 1)

            # Attitude Matrix given by Patriot Manual
            Mrot = matrix([[cos(a) * cos(b), sin(b) * sin(g) * cos(a) - cos(g) * sin(a),
                            cos(a) * sin(b) * cos(g) + sin(a) * sin(g)],
                           [cos(b) * sin(a), sin(b) * sin(g) * sin(a) + cos(g) * cos(a),
                            cos(g) * sin(b) * sin(a) - sin(g) * cos(a)],
                           [-sin(b), sin(g) * cos(b), cos(b) * cos(g)]])

            coord_fin = (Mrot.T) * vet

            coord = (coord_fin[0], coord_fin[1], coord_fin[2], angs1[0], angs1[1], angs1[2])

        x = 10.0
        y = 10.0
        z = -10.0
        print coord
        # Os fatores subtraidos (-0.36, 3.12, 1.88) representam um offset para navegacao com a bobina, caso for navegar so com a probe excluir esses fatores
        try:
            # if self.MTC_status == True and self.coordTT != None and self.coordcoil != None:
            fact_coil1 = self.coordTT[0] - self.coordcoil[0]
            fact_coil2 = self.coordTT[1] - self.coordcoil[1]
            fact_coil3 = self.coordTT[2] - self.coordcoil[2]
            fact_coil = [fact_coil1, fact_coil2, fact_coil3]
            coord = (
            float(coord[0]) * x + fact_coil[0], float(coord[1]) * y + fact_coil[1], float(coord[2]) * z + fact_coil[2],
            float(coord[3]), float(coord[4]), float(coord[5]))
            # coord = (float(coord[0])*x + 0.36, float(coord[1])*y -3.12, float(coord[2])*z -1.88,float(coord[3]),float(coord[4]),float(coord[5]))
        # else:
        except:
            coord = (float(coord[0]) * x, float(coord[1]) * y, float(coord[2]) * z, float(coord[3]), float(coord[4]),
                     float(coord[5]))
        return coord

    def PolhemusFAST(self, trck_init, ref_mode):
        dev = trk_init
        endpoint = dev[0][(0, 0)][0]
        coord = None
        dev.write(0x02, "u")
        dev.write(0x02, "F")
        dev.write(0x02, "P")

        if ref_mode == 0:

            data = dev.read(endpoint.bEndpointAddress,
                            endpoint.wMaxPacketSize)

            data2 = data.tostring()
            count = 0
            for i, j in enumerate(data2):
                if j == '-':
                    data2 = data2[:i + count] + ' ' + data2[i + count:]
                    count = count + 1

            aostr = [s for s in data2.split()]
            coord = [float(s) for s in aostr[1:len(aostr)]]

            x = 10.0
            y = 10.0
            z = -10.0

            if not coord:
                print "error 0,0,0"
                coord = (0, 0, 0, 0, 0, 0)

            coord = (float(coord[0]) * x, float(coord[1]) * y, float(coord[2]) * z, float(coord[3]), float(coord[4]),
                     float(coord[5]))
            return coord

        elif ref_mode == 1:

            data1 = dev.read(endpoint.bEndpointAddress, 2 * endpoint.wMaxPacketSize)

            data1str = data1.tostring()

            count = 0
            for i, j in enumerate(data1str):
                if j == '-':
                    data1str = data1str[:i + count] + ' ' + data1str[i + count:]
                    count = count + 1
            aostr1 = [s for s in data1str.split()]
            plh1 = [float(s) for s in aostr1[1:len(aostr1)]]
            plh2 = [float(s) for s in aostr1[8:14]]

            a = radians(plh2[3])
            b = radians(plh2[4])
            g = radians(plh2[5])

            angs1 = plh2[3:6]
            plh1 = matrix(plh1[0:3])
            plh1.reshape(3, 1)
            plh2 = matrix(plh2[0:3])
            plh2.reshape(3, 1)

            vet = plh1 - plh2
            vet = vet.reshape(3, 1)

            # Attitude Matrix given by Patriot Manual
            Mrot = matrix([[cos(a) * cos(b), sin(b) * sin(g) * cos(a) - cos(g) * sin(a),
                            cos(a) * sin(b) * cos(g) + sin(a) * sin(g)],
                           [cos(b) * sin(a), sin(b) * sin(g) * sin(a) + cos(g) * cos(a),
                            cos(g) * sin(b) * sin(a) - sin(g) * cos(a)],
                           [-sin(b), sin(g) * cos(b), cos(b) * cos(g)]])

            coord_fin = (Mrot.T) * vet
            coord = coord_fin[0], coord_fin[1], coord_fin[2], angs1[0], angs1[1], angs1[2]

            # fastrak ja esta em cm, transforma pra mm
            x = 10.0
            y = 10.0
            z = -10.0

            if not coord:
                print "ahh meu amigo... eh tudo zero viu"
                coord = (0, 0, 0, 0, 0, 0)

            coord = (float(coord[0]) * x, float(coord[1]) * y, float(coord[2]) * z,
                     float(coord[3]), float(coord[4]), float(coord[5]))
            return coord

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
        inch2mm = 25.4

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

            if not coord:
                print "error 0,0,0"
                coord = np.zeros((1, 6))

            coord = (float(coord[0])*inch2mm, float(coord[1])*inch2mm,
                     float(coord[2])*(-inch2mm), float(coord[3]),
                     float(coord[4]), float(coord[5]))

        elif ref_mode == 1:
            data1 = trck_init.read(endpoint.bEndpointAddress, 2 * endpoint.wMaxPacketSize)

            data1str = data1.tostring()

            count = 0
            for i, j in enumerate(data1str):
                if j == '-':
                    data1str = data1str[:i + count] + ' ' + data1str[i + count:]
                    count = count + 1
            aostr1 = [s for s in data1str.split()]
            plh1 = [float(s) for s in aostr1[1:len(aostr1)]]
            plh2 = [float(s) for s in aostr1[8:14]]

            a = radians(plh2[3])
            b = radians(plh2[4])
            g = radians(plh2[5])

            angs1 = plh2[3:6]
            plh1 = matrix(plh1[0:3])
            plh1.reshape(3, 1)
            plh2 = matrix(plh2[0:3])
            plh2.reshape(3, 1)

            vet = plh1 - plh2
            vet = vet.reshape(3, 1)

            # Attitude Matrix given by Patriot Manual
            Mrot = matrix([[cos(a) * cos(b), sin(b) * sin(g) * cos(a) - cos(g) * sin(a),
                            cos(a) * sin(b) * cos(g) + sin(a) * sin(g)],
                           [cos(b) * sin(a), sin(b) * sin(g) * sin(a) + cos(g) * cos(a),
                            cos(g) * sin(b) * sin(a) - sin(g) * cos(a)],
                           [-sin(b), sin(g) * cos(b), cos(b) * cos(g)]])

            coord_fin = (Mrot.T) * vet
            coord = coord_fin[0], coord_fin[1], coord_fin[2], angs1[0], angs1[1], angs1[2]

            if not coord:
                coord = (0, 0, 0, 0, 0, 0)

            coord = (float(coord[0]) * inch2mm, float(coord[1]) * inch2mm,
                     float(coord[2]) * (-inch2mm), float(coord[3]),
                     float(coord[4]), float(coord[5]))

        return coord

    def Zebris(self, trk_init, ref_mode):
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