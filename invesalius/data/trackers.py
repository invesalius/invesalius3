#import ClaronTracker
#import usb.core
import serial
#import usb.util
import sys
import gui.dialogs as dlg


class Tracker:
    def __init__(self, trck_id):
        """
        Initialize spatial trackers for neuronavigation

        :param trck_id: identifier of spatial tracker
        :return: spatial tracker initialization variable
        """

        self.ReturnTracker(trck_id)

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
            else:
                dlg.TrackerNotConnected(0)

        except ImportError:
            dlg.TrackerNotConnected(5)

        return trck_init

    def PlhFastrak(self):
        trck_init = self.polhemus_serial(1)

        return trck_init

    def PlhIsotrakII(self):
        trck_init = self.polhemus_serial(2)

        return trck_init

    def PlhPatriot(self):
        trck_init = None

        try:
            import sys

            import usb.core as uc
            # import usb.util as uu

            trck_init = uc.find(idVendor=0x0F44, idProduct=0xEF12)

            if not trck_init:
                print 'Could not find Polhemus PATRIOT USB. Trying Polhemus ' \
                      'serial connection...'

                trck_init = self.polhemus_serial(3)

            else:
                try:
                    cfg = trck_init.get_active_configuration()
                    for i in cfg:
                        for x in i:
                            # TODO: try better code
                            x = x
                    trck_init.set_configuration()

                except uc.USBError as err:
                    dlg.TrackerNotConnected(3)
                    print 'Could not set configuration %s' % err

        except ImportError:
            print 'Import Error for Polhemus PATRIOT USB.'
            trck_init = self.polhemus_serial(3)

        return trck_init

    def ZebrisCMS20(self):
        trck_init = None

        dlg.TrackerNotConnected(4)
        print 'Zebris device not found.'

        return trck_init

    def DefaultTracker(self):
        trck_init = None

        try:
            # import spatial tracker library
            print 'Trying to connect with spatial tracker.'

        except ImportError:
            dlg.TrackerNotConnected(5)

        return trck_init  # spatial tracker initialization variable

    def polhemus_serial(self, plh_id):
        trck_init = None

        try:
            import serial

            try:
                trck_init = serial.Serial(0, baudrate=115200, timeout=0.2)
                trck_init.write('P')
                data = trck_init.readlines()

                if not data:
                    dlg.TrackerNotConnected(plh_id)

            except serial.SerialException:
                dlg.TrackerNotConnected(6)

        except ImportError:
            dlg.TrackerNotConnected(5)

        return trck_init

    def ReturnTracker(self, trck_id):

        print "Returning"
        print "This is the tracker selected!", trck_id

        trck = {0 : self.ClaronTracker,
                1 : self.PlhFastrak,
                2 : self.PlhIsotrakII,
                3 : self.PlhPatriot,
                4 : self.ZebrisCMS20}

        return trck[trck_id]()


# class Tracker_Init:
#     def PolhemusISO_init(self):
#         try:
#             plh = serial.Serial(0, baudrate = 115200, timeout=0.2)
#             return plh
#
#         except:
#             dlg.TrackerNotConnected(1)
#             raise ValueError('Device not found')
#
#     def Polhemus_init(self):
#         dev = usb.core.find(idVendor=0x0F44, idProduct=0xEF12)
#         if dev is None:
#             dlg.TrackerNotConnected(1)
#             raise ValueError('Device not found')
#         try:
#             cfg = dev.get_active_configuration()
#             for i in cfg:
#                 for x in i:
#                     x = x
#             dev.set_configuration()
#         except usb.core.USBError as e:
#             sys.exit("Could not set configuration: %s" % str(e))
#         return dev
#
#     def Claron_init(self):
#         try:
#             mtc = ClaronTracker.ClaronTracker()
#             mtc.CalibrationDir = "C:\CalibrationFiles"
#             mtc.MarkerDir = "C:\Markers"
#             mtc.NumberFramesProcessed = 10
#             mtc.FramesExtrapolated = 0
#             mtc.Initialize()
#             if mtc.GetIdentifyingCamera():
#                 print "Camera Identified."
#                 mtc.Run()
#             else:
#                 dlg.TrackerNotConnected(2)
#                 print "The Claron MicronTracker is not connected!"
#             return mtc
#
#         except:
#             dlg.TrackerNotConnected(2)
#             raise ValueError('Device not found')
#
#
#     def Zebris_init(self):
#         dlg.TrackerNotConnected(3)
#         return