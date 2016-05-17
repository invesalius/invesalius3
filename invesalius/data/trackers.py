import sys
import gui.dialogs as dlg

#TODO: Disconnect tracker when a new one is connected
class Tracker:
    """
    Initialize spatial trackers for neuronavigation

    return: spatial tracker initialization variable
    """
    def __init__(self):
        self.trck_flag = 0
    def ClaronTracker(self):
        trck_init = None
        try:
            import ClaronTracker

            trck_init = ClaronTracker.ClaronTracker()
            trck_init.CalibrationDir = "../objects/mtc_files/CalibrationFiles"
            trck_init.MarkerDir = "../objects/mtc_files/Markers"
            trck_init.NumberFramesProcessed = 10
            trck_init.FramesExtrapolated = 0
            trck_init.Initialize()

            if trck_init.GetIdentifyingCamera():
                print "MicronTracker camera identified."
                trck_init.Run()
                self.trck_flag = 1
            else:
                trck_init = None
                dlg.TrackerNotConnected(1)

        except ImportError:
            dlg.TrackerNotConnected(1)

        return trck_init

    def PlhFastrak(self):
        trck_init = None
        try:
            import sys

            import usb.core as uc
            # import usb.util as uu

            trck_init = uc.find(idVendor=0x0F44, idProduct=0x0003)
            self.trck_flag = 2

            if not trck_init:
                print 'Could not find Polhemus PATRIOT USB. Trying Polhemus ' \
                      'serial connection...'

                trck_init = self.polhemus_serial(2)

            else:
                try:
                    cfg = trck_init.get_active_configuration()
                    for i in cfg:
                        for x in i:
                            # TODO: try better code
                            x = x
                    trck_init.set_configuration()

                except uc.USBError as err:
                    trck_init = None
                    dlg.TrackerNotConnected(2)
                    print 'Could not set configuration %s' % err

        #except ImportError or ValueError('No backend available'):
        except:
            print 'Import Error for Polhemus PATRIOT USB.'
            trck_init = self.polhemus_serial(2)

        return trck_init

    def PlhIsotrakII(self):
        trck_init = self.polhemus_serial(3)
        self.trck_flag = 3

        return trck_init

    def PlhPatriot(self):
        trck_init = None
        try:
            import Polhemus
            trck_init = Polhemus.Polhemus()
            initplh = trck_init.Initialize()
            trck_init.Run() #This run is necessary to discard the first coord collection
            self.trck_flag = 4
            if initplh == False:
                trck_init = None
                dlg.TrackerNotConnected(4)
                #raise ValueError('Device not found')

        except ImportError:
            trck_init = None
            dlg.TrackerNotConnected(4)

        return trck_init


    def ZebrisCMS20(self):
        trck_init = None
        self.trck_flag = 5
        dlg.TrackerNotConnected(5)
        print 'Zebris device not found.'

        return trck_init

    def DefaultTracker(self):
        trck_init = None
        try:
            # import spatial tracker library
            print 'Trying to connect with spatial tracker.'

        except ImportError:
            dlg.TrackerNotConnected(6)

        return trck_init  # spatial tracker initialization variable

    def polhemus_serial(self, plh_id):
        trck_init = None
        try:
            import serial

            try:
                trck_init = serial.Serial(0, baudrate=115200, timeout=0.2)
                trck_init.write('P')
                data = trck_init.readlines()
                self.trck_flag = 3

                if not data:
                    trck_init = None
                    dlg.TrackerNotConnected(plh_id)
            except serial.SerialException:
                trck_init = None
                dlg.TrackerNotConnected(7)
            except AttributeError:
                trck_init = None
                dlg.TrackerNotConnected(plh_id)

        except ImportError:
            dlg.TrackerNotConnected(6)

        return trck_init

    def Tracker_off(self):
        if self.trck_flag == 1:
            ClaronTracker.ClaronTracker().Close()
        elif self.trck_flag == 2:
            None
        elif self.trck_flag == 3:
            None
        elif self.trck_flag == 4:
            Polhemus.Polhemus().Close()
        elif self.trck_flag == 5:
            None
        else:
            None


