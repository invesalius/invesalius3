#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
#--------------------------------------------------------------------------
import sys

from wx import ID_OK

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher
# TODO: Disconnect tracker when a new one is connected
# TODO: Test if there are too many prints when connection fails
# TODO: Redesign error messages. No point in having "Could not connect to default tracker" in all trackers


class TrackerConnection():
    def __init__(self):
        self.connection = None

    def Connect(self):
        assert False, "Not implemented"

    def Disconnect(self):
        try:
            self.connection.Close()
            self.connection = False
            self.lib_mode = 'wrapper'
            print('Tracker disconnected.')
        except:
            self.connection = True
            self.lib_mode = 'error'
            print('The tracker could not be disconnected.')

    def IsConnected(self):
        # TODO: It would be cleaner to compare self.connection to None here; however, currently it can also have
        #   True and False values. Hence, return the connection object as a whole for now.
        return self.connection

    def GetConnection(self):
        # TODO: A nicer API would not expose connection object to outside, but instead use it directly to reply to queries
        #   for coordinates. To be able to do this, code that currently resides in coordinates.py (and that uses the connection
        #   object) would need to be incorporated into TrackerConnection class.
        return self.connection

    def GetLibMode(self):
        return self.lib_mode


class OptitrackTrackerConnection(TrackerConnection):
    """
    Connects to optitrack wrapper from Motive 2.2. Initialize cameras, attach listener, loads Calibration,
    loads User Profile (Rigid bodies information).
    """
    def __init__(self):
        super().__init__()

    def Connect(self):
        connection = None

        dialog = dlg.SetOptitrackconfigs()
        status = dialog.ShowModal()

        if status == ID_OK:
            calibration_optitrack, user_profile_optitrack = dialog.GetValue()
            try:
                import optitrack
                connection = optitrack.optr()

                if connection.Initialize(calibration_optitrack, user_profile_optitrack) == 0:
                    connection.Run()  # Runs 'Run' function once to update cameras.
                    lib_mode = 'wrapper'
                else:
                    connection = None
                    lib_mode = 'error'
            except ImportError:
                lib_mode = 'error'
                print('Error')
        else:
            lib_mode = None
            print('#####')

        dialog.Destroy()

        self.connection = connection
        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class ClaronTrackerConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self):
        connection = None
        try:
            import pyclaron

            lib_mode = 'wrapper'
            connection = pyclaron.pyclaron()
            connection.CalibrationDir = inv_paths.MTC_CAL_DIR.encode(const.FS_ENCODE)
            connection.MarkerDir = inv_paths.MTC_MAR_DIR.encode(const.FS_ENCODE)
            connection.NumberFramesProcessed = 1
            connection.FramesExtrapolated = 0
            connection.PROBE_NAME = const.MTC_PROBE_NAME.encode(const.FS_ENCODE)
            connection.REF_NAME = const.MTC_REF_NAME.encode(const.FS_ENCODE)
            connection.OBJ_NAME = const.MTC_OBJ_NAME.encode(const.FS_ENCODE)
            connection.Initialize()

            if connection.GetIdentifyingCamera():
                connection.Run()
                print("MicronTracker camera identified.")
            else:
                connection = None

        except ImportError:
            lib_mode = 'error'
            print('The ClaronTracker library is not installed.')

        self.connection = connection
        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class PolhemusTrackerConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self, model):
        assert model in ['fastrak', 'isotrak', 'patriot'], "Unsupported model for Polhemus tracker: {}".format(type)

        connection = None
        try:
            connection = self.PolhemusWrapperConnection(model)
            lib_mode = 'wrapper'
            if not connection:
                print('Could not connect with Polhemus wrapper, trying USB connection...')

                connection = self.PolhemusUSBConnection(model)
                lib_mode = 'usb'
                if not connection:
                    print('Could not connect with Polhemus USB, trying serial connection...')
                    connection = self.PolhemusSerialConnection(model)
                    lib_mode = 'serial'
        except:
            lib_mode = 'error'
            print('Could not connect to Polhemus by any method.')

        self.connection = connection
        self.lib_mode = lib_mode
        self.model = model

    def PolhemusWrapperConnection(self, model):
        try:
            from time import sleep
            if model == 'fastrak':
                import polhemusFT
                connection = polhemusFT.polhemusFT()
            else:
                import polhemus
                connection = polhemus.polhemus()

            success = connection.Initialize()

            if success:
                # Sequence of runs necessary to throw away unnecessary data
                for n in range(0, 5):
                    connection.Run()
                    sleep(0.175)
            else:
                connection = None
                print('Could not connect to Polhemus via wrapper without error: Initialize is False.')
        except:
            connection = None
            print('Could not connect to Polhemus via wrapper without error: Import failed.')

        return connection

    def PolhemusSerialConnection(self, model):
        import serial

        connection = None

        dialog = dlg.SetCOMPort(select_baud_rate=False)
        status = dialog.ShowModal()

        if status == ID_OK:
            com_port = dialog.GetCOMPort()
            baud_rate = 115200

            try:
                connection = serial.Serial(com_port, baudrate=baud_rate, timeout=0.03)

                if model == 'fastrak':
                    # Polhemus FASTRAK needs configurations first
                    connection.write(0x02, str.encode("u"))
                    connection.write(0x02, str.encode("F"))

                elif model == 'isotrak':
                    # Polhemus ISOTRAK needs to set tracking point from
                    # center to tip.
                    connection.write(str.encode("u"))
                    connection.write(str.encode("F"))
                    connection.write(str.encode("Y"))

                connection.write(str.encode("P"))
                data = connection.readlines()
                if not data:
                    connection = None
                    print('Could not connect to Polhemus serial without error.')

            except:
                connection = None
                print('Could not connect to Polhemus tracker.')
        else:
            print('Could not connect to Polhemus tracker.')

        dialog.Destroy()

        return connection

    def PolhemusUSBConnection(self, model):
        connection = None
        try:
            import usb.core as uc

            # Check the idProduct using the usbdeview software, the idProduct is unique for each
            # device and connection fails when is incorrect
            # connection = uc.find(idVendor=0x0F44, idProduct=0x0003) [used in a different device]
            connection = uc.find(idVendor=0x0F44, idProduct=0xEF12)

            config = connection.get_active_configuration()

            # XXX: What is done here?
            for i in config:
                for x in i:
                    # TODO: try better code
                    x = x

            connection.set_configuration()
            endpoint = connection[0][(0, 0)][0]

            if model == 'fastrak':
                # Polhemus FASTRAK needs configurations first

                # TODO: Check configurations to standardize initialization for all Polhemus devices
                connection.write(0x02, "u")
                connection.write(0x02, "F")

            # First run to confirm that everything is working
            connection.write(0x02, "P")
            data = connection.read(endpoint.bEndpointAddress,
                                endpoint.wMaxPacketSize)
            if not data:
                connection = None
                print('Could not connect to Polhemus USB without error.')

        except:
            print('Could not connect to Polhemus USB with error.')

        return connection

    def Disconnect(self):
        try:
            if self.model == 'isotrak':
                self.connection.close()
                self.lib_mode = 'serial'
            else:
                self.connection.Close()
                self.lib_mode = 'wrapper'

            self.connection = False
            print('Tracker disconnected.')
        except:
            self.connection = True
            self.lib_mode = 'error'
            print('The tracker could not be disconnected.')


class CameraTrackerConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self):
        connection = None
        try:
            import invesalius.data.camera_tracker as cam

            connection = cam.camera()
            connection.Initialize()
            print('Connect to camera tracking device.')

            lib_mode = 'wrapper'

        except:
            print('Could not connect to camera tracker.')
            lib_mode = 'error'

        self.connection = connection
        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class PolarisTrackerConnection():
    def __init__(self):
        super().__init__()

    def Connect(self):
        connection = None

        dialog = dlg.SetNDIconfigs()
        status = dialog.ShowModal()

        if status == ID_OK:
            com_port, PROBE_DIR, REF_DIR, OBJ_DIR = dialog.GetValue()
            try:
                if sys.platform == 'win32':
                    import pypolaris
                    connection = pypolaris.pypolaris()
                else:
                    from pypolaris import pypolaris
                    connection = pypolaris.pypolaris()

                lib_mode = 'wrapper'

                if connection.Initialize(com_port, PROBE_DIR, REF_DIR, OBJ_DIR) != 0:
                    connection = None
                    lib_mode = None
                    print('Could not connect to polaris tracker.')
                else:
                    print('Connect to polaris tracking device.')

            except:
                lib_mode = 'error'
                connection = None
                print('Could not connect to polaris tracker.')
        else:
            lib_mode = None
            print('Could not connect to polaris tracker.')

        dialog.Destroy()

        self.connection = connection
        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class PolarisP4TrackerConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self):
        connection = None

        dialog = dlg.SetNDIconfigs()
        status = dialog.ShowModal()

        if status == ID_OK:
            com_port, PROBE_DIR, REF_DIR, OBJ_DIR = dialog.GetValue()
            try:
                import pypolarisP4
                lib_mode = 'wrapper'
                connection = pypolarisP4.pypolarisP4()

                if connection.Initialize(com_port, PROBE_DIR, REF_DIR, OBJ_DIR) != 0:
                    connection = None
                    lib_mode = None
                    print('Could not connect to Polaris P4 tracker.')
                else:
                    print('Connect to Polaris P4 tracking device.')

            except:
                lib_mode = 'error'
                connection = None
                print('Could not connect to Polaris P4 tracker.')
        else:
            lib_mode = None
            print('Could not connect to Polaris P4 tracker.')

        dialog.Destroy()

        self.connection = connection
        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class RobotTrackerConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self):
        connection = None
        tracker_id = None

        select_tracker_dialog = dlg.SetTrackerDeviceToRobot()
        status = select_tracker_dialog.ShowModal()

        if status == ID_OK:
            tracker_id = select_tracker_dialog.GetValue()
            if tracker_id:
                connection = CreateTrackerConnection(tracker_id)
                connection.Connect()

                if connection.IsConnected():
                    select_ip_dialog = dlg.SetRobotIP()
                    status = select_ip_dialog.ShowModal()

                    if status == ID_OK:
                        robot_IP = select_ip_dialog.GetValue()
                        Publisher.sendMessage('Connect to robot', robot_IP=robot_IP)

                    select_ip_dialog.Destroy()

        select_tracker_dialog.Destroy()

        self.connection = connection
        self.tracker_id = tracker_id

    def Disconnect(self):
        try:
            Publisher.sendMessage('Reset robot', data=None)

            self.connection.Disconnect()
            self.connection = False

            self.lib_mode = 'wrapper'
            print('Tracker disconnected.')
        except:
            self.connection = True
            self.lib_mode = 'error'
            print('The tracker could not be disconnected.')

    def GetTrackerId(self):
        return self.tracker_id

    def GetConnection(self):
        # XXX: This is a bit convoluted logic, so here's a short explanation: in other cases, self.connection
        #   is the object which can be used to communicate with the tracker directly. However, when using robot,
        #   self.connection is another TrackerConnection object, hence forward the query to that object.
        return self.connection.GetConnection()

    def GetLibMode(self):
        return self.connection.GetLibMode()

    def IsConnected(self):
        return self.connection.IsConnected()


class DebugTrackerRandomConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self):
        self.connection = True
        self.lib_mode = 'debug'
        print('Debug device (random) started.')

    def Disconnect(self):
        self.connection = False
        self.lib_mode = 'debug'
        print('Debug tracker (random) disconnected.')


class DebugTrackerApproachConnection(TrackerConnection):
    def __init__(self):
        super().__init__()

    def Connect(self):
        self.connection = True
        self.lib_mode = 'debug'
        print('Debug device (approach) started.')

    def Disconnect(self):
        self.connection = False
        self.lib_mode = 'debug'
        print('Debug tracker (approach) disconnected.')


TRACKER_CONNECTION_CLASSES = {
    const.MTC: ClaronTrackerConnection,
    const.FASTRAK: PolhemusTrackerConnection,
    const.ISOTRAKII: PolhemusTrackerConnection,
    const.PATRIOT: PolhemusTrackerConnection,
    const.CAMERA: CameraTrackerConnection,
    const.POLARIS: PolarisTrackerConnection,
    const.POLARISP4: PolarisP4TrackerConnection,
    const.OPTITRACK: OptitrackTrackerConnection,
    const.ROBOT: RobotTrackerConnection,
    const.DEBUGTRACKRANDOM: DebugTrackerRandomConnection,
    const.DEBUGTRACKAPPROACH: DebugTrackerApproachConnection,
}


def CreateTrackerConnection(tracker_id):
    """
    Initialize spatial tracker connection for coordinate detection during navigation.

    :param tracker_id: ID of tracking device.
    :return spatial tracker connection instance or None if could not open device.
    """
    tracker_connection_class = TRACKER_CONNECTION_CLASSES[tracker_id]
    tracker_connection = tracker_connection_class()

    return tracker_connection
