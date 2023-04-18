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
from typing import Any, Dict, List, Optional, Tuple, Union
import invesalius.constants as const
import invesalius.gui.dialogs as dlg
from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher
# TODO: Disconnect tracker when a new one is connected
# TODO: Test if there are too many prints when connection fails
# TODO: Redesign error messages. No point in having "Could not connect to default tracker" in all trackers


class TrackerConnection():
    def __init__(self, model: object = None) -> None:
        self.connection: object = None
        self.configuration: object = None
        self.model: object = model

    def Configure(self) -> bool:
        assert False, "Not implemented"

    def Connect(self) -> None:
        assert False, "Not implemented"

    def Disconnect(self) -> None:
        try:
            self.connection.Close()
            self.connection: bool = False
            self.lib_mode: str = 'wrapper'
            print('Tracker disconnected.')
        except:
            self.connection: bool = True
            self.lib_mode: str = 'error'
            print('The tracker could not be disconnected.')

    def IsConnected(self) -> object:
        # TODO: It would be cleaner to compare self.connection to None here; however, currently it can also have
        #   True and False values. Hence, return the connection object as a whole for now.
        return self.connection

    def GetConnection(self) -> object:
        # TODO: A nicer API would not expose connection object to outside, but instead use it directly to reply to queries
        #   for coordinates. To be able to do this, code that currently resides in coordinates.py (and that uses the connection
        #   object) would need to be incorporated into TrackerConnection class.
        return self.connection

    def GetLibMode(self) -> str:
        return self.lib_mode

    def GetConfiguration(self) -> object:
        return self.configuration

    def SetConfiguration(self, configuration: object) -> bool:
        self.configuration: object = configuration
        return True


class OptitrackTrackerConnection(TrackerConnection):
    """
    Connects to optitrack wrapper from Motive 2.2. Initialize cameras, attach listener, loads Calibration,
    loads User Profile (Rigid bodies information).
    """
    def __init__(self, model: object = None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        dialog: dlg.SetOptitrackconfigs = dlg.SetOptitrackconfigs()

        status: int = dialog.ShowModal()
        success: bool = status == ID_OK

        if success:
            calibration: object = dialog.GetValue()[0]
            user_profile: object = dialog.GetValue()[1]
            self.configuration: dict = {
                'calibration': calibration,
                'user_profile': user_profile,
            }
        else:
            self.lib_mode: str = None

        dialog.Destroy()
        return success

    def Connect(self) -> None:
        assert self.configuration is not None, "No configuration defined"

        try:
            import optitrack
            connection: optitrack.optr = optitrack.optr()

            calibration: object = self.configuration['calibration']
            user_profile: object = self.configuration['user_profile']

            if connection.Initialize(calibration, user_profile) == 0:
                connection.Run()  # Runs 'Run' function once to update cameras.
                lib_mode: str = 'wrapper'

                self.connection: optitrack.optr = connection
            else:
                lib_mode: str = 'error'

        except ImportError:
            lib_mode: str = 'error'
            print('Error')

        self.lib_mode: str = lib_mode

    def Disconnect(self) -> None:
        super().Disconnect()


class ClaronTrackerConnection(TrackerConnection):
    def __init__(self, model: object = None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        return True

    def Connect(self) -> None:
        try:
            import pyclaron

            lib_mode: str = 'wrapper'
            connection: pyclaron.pyclaron = pyclaron.pyclaron()

            connection.CalibrationDir: bytes = inv_paths.MTC_CAL_DIR.encode(const.FS_ENCODE)
            connection.MarkerDir: bytes = inv_paths.MTC_MAR_DIR.encode(const.FS_ENCODE)
            connection.NumberFramesProcessed: int = 1
            connection.FramesExtrapolated: int = 0
            connection.PROBE_NAME: bytes = const.MTC_PROBE_NAME.encode(const.FS_ENCODE)
            connection.REF_NAME: bytes = const.MTC_REF_NAME.encode(const.FS_ENCODE)
            connection.OBJ_NAME: bytes = const.MTC_OBJ_NAME.encode(const.FS_ENCODE)

            connection.Initialize()

            if connection.GetIdentifyingCamera():
                connection.Run()
                print("MicronTracker camera identified.")

                self.connection: pyclaron.pyclaron = connection

        except ImportError:
            lib_mode: str = 'error'
            print('The ClaronTracker library is not installed.')

        self.lib_mode: str = lib_mode

    def Disconnect(self) -> None:
        super().Disconnect()


class PolhemusTrackerConnection(TrackerConnection):
    def __init__(self, model: str = None) -> None:
        assert model in ['fastrak', 'isotrak', 'patriot'], "Unsupported model for Polhemus tracker: {}".format(model)

        super().__init__(model)

    def Configure(self) -> bool:
        return True

    def ConfigureCOMPort(self) -> bool:
        dialog = dlg.SetCOMPort(select_baud_rate=False)
        status = dialog.ShowModal()

        success: bool = status == ID_OK

        if success:
            com_port: str = dialog.GetCOMPort()
            baud_rate: int = 115200

            self.configuration = {
                'com_port': com_port,
                'baud_rate': baud_rate,
            }
        else:
            print('Could not connect to Polhemus tracker.')

        dialog.Destroy()

        return success

    # XXX: The workflow in connecting to Polhemus is that, first, a wrapper connection
    #   and a USB connection are attempted. If both fail, the user is asked to configure
    #   the COM port, and a serial connection is attempted. Unfortunately, that requires
    #   some additional logic in Connect function to support connecting with preset configuration
    #   (namely, by setting 'reconfigure' to False.)
    def Connect(self, reconfigure: bool) -> None:
        connection: object = None
        try:
            connection = self.PolhemusWrapperConnection()
            lib_mode: str = 'wrapper'
            if not connection:
                print('Could not connect with Polhemus wrapper, trying USB connection...')

                connection = self.PolhemusUSBConnection()
                lib_mode = 'usb'
                if not connection:
                    print('Could not connect with Polhemus USB, trying serial connection...')

                    if reconfigure:
                        self.ConfigureCOMPort()
                    connection = self.PolhemusSerialConnection()
                    lib_mode = 'serial'
        except:
            lib_mode = 'error'
            print('Could not connect to Polhemus by any method.')

        self.connection = connection
        self.lib_mode = lib_mode

    def PolhemusWrapperConnection(self) -> object:
        try:
            from time import sleep
            if self.model == 'fastrak':
                import polhemusFT
                connection: object = polhemusFT.polhemusFT()
            else:
                import polhemus
                connection: object = polhemus.polhemus()

            success: bool = connection.Initialize()

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

    def PolhemusSerialConnection(self) -> object:
        assert self.configuration is not None, "No configuration defined"

        import serial

        connection: object = None

        try:
            com_port: str = self.configuration['com_port']
            baud_rate: int = self.configuration['baud_rate']

            connection = serial.Serial(
                com_port,
                baudrate=baud_rate,
                timeout=0.03
            )

            if self.model == 'fastrak':
                # Polhemus FASTRAK needs configurations first
                connection.write(0x02, str.encode("u"))
                connection.write(0x02, str.encode("F"))

            elif self.model == 'isotrak':
                # Polhemus ISOTRAK needs to set tracking point from
                # center to tip.
                connection.write(str.encode("u"))
                connection.write(str.encode("F"))
                connection.write(str.encode("Y"))

            connection.write(str.encode("P"))
            data: list[bytes] = connection.readlines()
            if not data:
                connection = None
                print('Could not connect to Polhemus serial without error.')

        except:
            connection = None
            print('Could not connect to Polhemus tracker.')

        return connection

    def PolhemusUSBConnection(self) -> object:
        connection: object = None
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
                    pass

            connection.set_configuration()
            endpoint: object = connection[0][(0, 0)][0]

            if self.model == 'fastrak':
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

    def Disconnect(self) -> None:
        try:
            if self.model == 'isotrak':
                self.connection.close()
                self.lib_mode: str = 'serial'
            else:
                self.connection.Close()
                self.lib_mode: str = 'wrapper'

            self.connection: bool = False
            print('Tracker disconnected.')
        except:
            self.connection: bool = True
            self.lib_mode: str = 'error'
            print('The tracker could not be disconnected.')


class CameraTrackerConnection(TrackerConnection):
    def __init__(self, model: str=None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        return True

    def Connect(self) -> None:
        try:
            import invesalius.data.camera_tracker as cam

            connection: object = cam.camera()
            connection.Initialize()
            print('Connected to camera tracking device.')

            lib_mode: str = 'wrapper'

            self.connection: object = connection
        except:
            print('Could not connect to camera tracker.')
            lib_mode: str = 'error'

        self.lib_mode: str = lib_mode

    def Disconnect(self) -> None:
        super().Disconnect()


class PolarisTrackerConnection(TrackerConnection):
    def __init__(self, model: str=None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        dialog: object = dlg.SetNDIconfigs()
        status: int = dialog.ShowModal()

        success: bool = status == ID_OK
        if success:
            com_port, probe_dir, ref_dir, obj_dir: str = dialog.GetValue()

            self.configuration: dict = {
                'com_port': com_port,
                'probe_dir': probe_dir,
                'ref_dir': ref_dir,
                'obj_dir': obj_dir,
            }
        else:
            self.lib_mode: str = None
            print('Could not connect to polaris tracker.')

        dialog.Destroy()

        return success

    def Connect(self) -> None:
        assert self.configuration is not None, "No configuration defined"

        try:
            if sys.platform == 'win32':
                import pypolaris
                connection: object = pypolaris.pypolaris()
            else:
                from pypolaris import pypolaris
                connection: object = pypolaris.pypolaris()

            lib_mode: str = 'wrapper'

            com_port: bytes = self.configuration['com_port'].encode(const.FS_ENCODE)
            probe_dir: bytes = self.configuration['probe_dir'].encode(const.FS_ENCODE)
            ref_dir: bytes = self.configuration['ref_dir'].encode(const.FS_ENCODE)
            obj_dir: bytes = self.configuration['obj_dir'].encode(const.FS_ENCODE)

            if connection.Initialize(com_port, probe_dir, ref_dir, obj_dir) != 0:
                lib_mode: str = None
                print('Could not connect to polaris tracker.')
            else:
                print('Connected to polaris tracking device.')
                self.connection: object = connection

        except:
            lib_mode: str = 'error'
            connection: object = None
            print('Could not connect to polaris tracker.')

        self.lib_mode: str = lib_mode

    def Disconnect(self) -> None:
        super().Disconnect()


class PolarisP4TrackerConnection(TrackerConnection):
    def __init__(self, model: str=None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        dialog: object = dlg.SetNDIconfigs()
        status: int = dialog.ShowModal()

        success: bool = status == ID_OK
        if success:
            com_port, probe_dir, ref_dir, obj_dir: str = dialog.GetValue()

            self.configuration: dict = {
                'com_port': com_port,
                'probe_dir': probe_dir,
                'ref_dir': ref_dir,
                'obj_dir': obj_dir,
            }
        else:
            self.lib_mode: str = None
            print('Could not connect to Polaris P4 tracker.')

        dialog.Destroy()

        return success

    def Connect(self) -> None:
        assert self.configuration is not None, "No configuration defined"

        connection: object = None
        try:
            import pypolarisP4

            lib_mode: str = 'wrapper'
            connection: object = pypolarisP4.pypolarisP4()

            com_port: bytes = self.configuration['com_port'].encode(const.FS_ENCODE)
            probe_dir: bytes = self.configuration['probe_dir'].encode(const.FS_ENCODE)
            ref_dir: bytes = self.configuration['ref_dir'].encode(const.FS_ENCODE)
            obj_dir: bytes = self.configuration['obj_dir'].encode(const.FS_ENCODE)

            if connection.Initialize(com_port, probe_dir, ref_dir, obj_dir) != 0:
                connection: object = None
                lib_mode: str = None
                print('Could not connect to Polaris P4 tracker.')
            else:
                print('Connect to Polaris P4 tracking device.')

        except:
            lib_mode: str = 'error'
            connection: object = None
            print('Could not connect to Polaris P4 tracker.')

        self.connection: object = connection
        self.lib_mode: str = lib_mode

    def Disconnect(self) -> None:
        super().Disconnect()


class RobotTrackerConnection(TrackerConnection):
    def __init__(self, model: str = None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        select_tracker_dialog = dlg.SetTrackerDeviceToRobot()
        status: int = select_tracker_dialog.ShowModal()

        success: bool = False

        if status == ID_OK:
            tracker_id: str = select_tracker_dialog.GetValue()
            if tracker_id:
                connection: TrackerConnection = CreateTrackerConnection(tracker_id)
                connection.Configure()

                select_ip_dialog = dlg.SetRobotIP()
                status: int = select_ip_dialog.ShowModal()

                if status == ID_OK:
                    robot_ip: str = select_ip_dialog.GetValue()

                    self.configuration: dict = {
                        'tracker_id': tracker_id,
                        'robot_ip': robot_ip,
                        'tracker_configuration': connection.GetConfiguration(),
                    }
                    self.connection: TrackerConnection = connection

                    success: bool = True

                select_ip_dialog.Destroy()

        select_tracker_dialog.Destroy()

        return success

    def Connect(self) -> None:
        assert self.configuration is not None, "No configuration defined"

        tracker_id: str = self.configuration['tracker_id']
        robot_ip: str = self.configuration['robot_ip']
        tracker_configuration: dict = self.configuration['tracker_configuration']

        if self.connection is None:
            self.connection: TrackerConnection = CreateTrackerConnection(tracker_id)
            self.connection.SetConfiguration(tracker_configuration)

        Publisher.sendMessage('Connect to robot', robot_IP = robot_ip)

        self.connection.Connect()
        if not self.connection.IsConnected():
            print("Failed to connect to tracker.")

    def Disconnect(self) -> None:
        try:
            Publisher.sendMessage('Reset robot', data = None)

            self.connection.Disconnect()
            self.connection: bool = False

            self.lib_mode: str = 'wrapper'
            print('Tracker disconnected.')
        except:
            self.connection: bool = True
            self.lib_mode: str = 'error'
            print('The tracker could not be disconnected.')

    def GetTrackerId(self) -> str:
        tracker_id: str = self.configuration['tracker_id']
        return tracker_id

    def GetConnection(self) -> object:
        # XXX: This is a bit convoluted logic, so here's a short explanation: in other cases, self.connection
        #   is the object which can be used to communicate with the tracker directly. However, when using robot,
        #   self.connection is another TrackerConnection object, hence forward the query to that object.
        return self.connection.GetConnection()

    def GetLibMode(self) -> str:
        return self.connection.GetLibMode()

    def IsConnected(self) -> bool:
        return self.connection and self.connection.IsConnected()

    def SetConfiguration(self, configuration: dict) -> bool:
        self.configuration: dict = configuration
        return True


class DebugTrackerRandomConnection(TrackerConnection):
    def __init__(self, model: str = None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        return True

    def Connect(self) -> None:
        self.connection: bool = True
        self.lib_mode: str = 'debug'
        print('Debug device (random) started.')

    def Disconnect(self) -> None:
        self.connection: bool = False
        self.lib_mode: str = 'debug'
        print('Debug tracker (random) disconnected.')


class DebugTrackerApproachConnection(TrackerConnection):
    def __init__(self, model: str = None) -> None:
        super().__init__(model)

    def Configure(self) -> bool:
        return True

    def Connect(self) -> None:
        self.connection: bool = True
        self.lib_mode: str = 'debug'
        print('Debug device (approach) started.')

    def Disconnect(self) -> None:
        self.connection: bool = False
        self.lib_mode: str = 'debug'
        print('Debug tracker (approach) disconnected.')


TRACKER_CONNECTION_CLASSES: dict = {
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


def CreateTrackerConnection(tracker_id: str) -> TrackerConnection:
    """
    Initialize spatial tracker connection for coordinate detection during navigation.

    :param tracker_id: ID of tracking device.
    :return spatial tracker connection instance or None if could not open device.
    """
    tracker_connection_class: type = TRACKER_CONNECTION_CLASSES[tracker_id]

    # XXX: A better solution than to pass a 'model' parameter to the constructor of tracker
    #   connection would be to have separate class for each model, possibly inheriting
    #   the same base class, e.g., in this case, PolhemusTrackerConnection base class, which
    #   would be inherited by FastrakTrackerConnection class, etc.
    if tracker_id == const.FASTRAK:
        model: str = 'fastrak'
    elif tracker_id == const.ISOTRAKII:
        model: str = 'isotrak'
    elif tracker_id == const.PATRIOT:
        model: str = 'patriot'
    else:
        model: str = None

    tracker_connection: TrackerConnection = tracker_connection_class(
        model=model
    )
    return tracker_connection
