import sys
import gui.dialogs as dlg


class Tracker:
    """
    Initialize spatial trackers for neuronavigation

    return: spatial tracker initialization variable
    """
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
                    dlg.TrackerNotConnected(2)
                    print 'Could not set configuration %s' % err

        except ImportError and uc.NoBackendError:
            print 'Import Error for Polhemus PATRIOT USB.'
            trck_init = self.polhemus_serial(2)

        return trck_init

    def PlhIsotrakII(self):
        trck_init = self.polhemus_serial(3)

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

                trck_init = self.polhemus_serial(4)

            else:
                try:
                    cfg = trck_init.get_active_configuration()
                    for i in cfg:
                        for x in i:
                            # TODO: try better code
                            x = x
                    trck_init.set_configuration()

                except uc.USBError as err:
                    dlg.TrackerNotConnected(4)
                    print 'Could not set configuration %s' % err

        except ImportError and uc.NoBackendError:
            print 'Import Error for Polhemus PATRIOT USB.'
            trck_init = self.polhemus_serial(4)

        return trck_init

    def ZebrisCMS20(self):
        trck_init = None
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

                if not data:
                    dlg.TrackerNotConnected(plh_id)
            except serial.SerialException:
                dlg.TrackerNotConnected(7)
            except AttributeError:
                dlg.TrackerNotConnected(plh_id)

        except ImportError:
            dlg.TrackerNotConnected(6)

        return trck_init


