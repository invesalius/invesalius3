# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
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
# --------------------------------------------------------------------------
import sys

from wx import ID_OK

import invesalius.constants as const
import invesalius.gui.dialogs as dlg
from invesalius import inv_paths

# TODO: Disconnect tracker when a new one is connected
# TODO: Test if there are too many prints when connection fails
# TODO: Redesign error messages. No point in having "Could not connect to default tracker" in all trackers


class TrackerConnection:
    def __init__(self, model=None, n_coils=1):
        self.connection = None
        self.configuration = None
        self.model = model

    def Configure(self):
        assert False, "Not implemented"

    def Connect(self):
        assert False, "Not implemented"

    def Disconnect(self):
        try:
            self.connection.Close()
            self.connection = False
            self.lib_mode = "wrapper"
            print("Tracker disconnected.")
        except Exception:
            self.connection = True
            self.lib_mode = "error"
            print("The tracker could not be disconnected.")

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

    def GetConfiguration(self):
        return self.configuration

    def SetConfiguration(self, configuration):
        self.configuration = configuration
        return True


class OptitrackTrackerConnection(TrackerConnection):
    """
    Connects to optitrack wrapper from Motive 2.2. Initialize cameras, attach listener, loads Calibration,
    loads User Profile (Rigid bodies information).
    """

    def __init__(self, model=None, n_coils=1):
        super().__init__(model)

    def Configure(self):
        dialog = dlg.ConfigureOptitrackDialog()

        status = dialog.ShowModal()
        success = status == ID_OK

        if success:
            calibration, user_profile = dialog.GetValue()
            self.configuration = {
                "calibration": calibration,
                "user_profile": user_profile,
            }
        else:
            self.lib_mode = None

        dialog.Destroy()
        return success

    def Connect(self):
        assert self.configuration is not None, "No configuration defined"

        import optitrack

        connection = optitrack.optr()

        calibration = self.configuration["calibration"]
        user_profile = self.configuration["user_profile"]

        if connection.Initialize(calibration, user_profile) == 0:
            connection.Run()  # Runs 'Run' function once to update cameras.
            lib_mode = "wrapper"

            self.connection = connection
        else:
            print("Could not connect to Optitrack tracker.")
            lib_mode = "error"

        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class ClaronTrackerConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        super().__init__(model)

    def Configure(self):
        return True

    def Connect(self):
        try:
            import pyclaron

            lib_mode = "wrapper"
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

                self.connection = connection

        except ImportError:
            lib_mode = "error"
            print("The ClaronTracker library is not installed.")

        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class PolhemusTrackerConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        assert model in [
            "fastrak",
            "isotrak",
            "patriot",
        ], f"Unsupported model for Polhemus tracker: {model}"

        super().__init__(model)

    def Configure(self):
        return True

    def ConfigureCOMPort(self):
        dialog = dlg.SetCOMPort(select_baud_rate=False)
        status = dialog.ShowModal()

        success = status == ID_OK

        if success:
            com_port = dialog.GetCOMPort()
            baud_rate = 115200

            self.configuration = {
                "com_port": com_port,
                "baud_rate": baud_rate,
            }
        else:
            print("Could not connect to Polhemus tracker.")

        dialog.Destroy()

        return success

    # XXX: The workflow in connecting to Polhemus is that, first, a wrapper connection
    #   and a USB connection are attempted. If both fail, the user is asked to configure
    #   the COM port, and a serial connection is attempted. Unfortunately, that requires
    #   some additional logic in Connect function to support connecting with preset configuration
    #   (namely, by setting 'reconfigure' to False.)
    def Connect(self, reconfigure):
        connection = None
        try:
            connection = self.PolhemusWrapperConnection()
            lib_mode = "wrapper"
            if not connection:
                print("Could not connect with Polhemus wrapper, trying USB connection...")

                connection = self.PolhemusUSBConnection()
                lib_mode = "usb"
                if not connection:
                    print("Could not connect with Polhemus USB, trying serial connection...")

                    if reconfigure:
                        self.ConfigureCOMPort()
                    connection = self.PolhemusSerialConnection()
                    lib_mode = "serial"
        except Exception:
            lib_mode = "error"
            print("Could not connect to Polhemus by any method.")

        self.connection = connection
        self.lib_mode = lib_mode

    def PolhemusWrapperConnection(self):
        try:
            from time import sleep

            if self.model == "fastrak":
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
                print(
                    "Could not connect to Polhemus via wrapper without error: Initialize is False."
                )
        except Exception:
            connection = None
            print("Could not connect to Polhemus via wrapper without error: Import failed.")

        return connection

    def PolhemusSerialConnection(self):
        assert self.configuration is not None, "No configuration defined"

        import serial

        connection = None

        try:
            com_port = self.configuration["com_port"]
            baud_rate = self.configuration["baud_rate"]

            connection = serial.Serial(com_port, baudrate=baud_rate, timeout=0.03)

            if self.model == "fastrak":
                # Polhemus FASTRAK needs configurations first
                connection.write(0x02, str.encode("u"))
                connection.write(0x02, str.encode("F"))

            elif self.model == "isotrak":
                # Polhemus ISOTRAK needs to set tracking point from
                # center to tip.
                connection.write(str.encode("u"))
                connection.write(str.encode("F"))
                connection.write(str.encode("Y"))

            connection.write(str.encode("P"))
            data = connection.readlines()
            if not data:
                connection = None
                print("Could not connect to Polhemus serial without error.")

        except Exception:
            connection = None
            print("Could not connect to Polhemus tracker.")

        return connection

    def PolhemusUSBConnection(self):
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
                    pass

            connection.set_configuration()
            endpoint = connection[0][(0, 0)][0]

            if self.model == "fastrak":
                # Polhemus FASTRAK needs configurations first

                # TODO: Check configurations to standardize initialization for all Polhemus devices
                connection.write(0x02, "u")
                connection.write(0x02, "F")

            # First run to confirm that everything is working
            connection.write(0x02, "P")
            data = connection.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize)
            if not data:
                connection = None
                print("Could not connect to Polhemus USB without error.")

        except Exception:
            print("Could not connect to Polhemus USB with error.")

        return connection

    def Disconnect(self):
        try:
            if self.model == "isotrak":
                self.connection.close()
                self.lib_mode = "serial"
            else:
                self.connection.Close()
                self.lib_mode = "wrapper"

            self.connection = False
            print("Tracker disconnected.")
        except Exception:
            self.connection = True
            self.lib_mode = "error"
            print("The tracker could not be disconnected.")


class CameraTrackerConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        super().__init__(model)

    def Configure(self):
        return True

    def Connect(self):
        try:
            import invesalius.data.camera_tracker as cam

            connection = cam.camera()
            connection.Initialize()
            print("Connected to camera tracking device.")

            lib_mode = "wrapper"

            self.connection = connection
        except Exception:
            print("Could not connect to camera tracker.")
            lib_mode = "error"

        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class PolarisTrackerConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        self.n_coils = n_coils
        super().__init__(model)

    def Configure(self):
        dialog = dlg.ConfigurePolarisDialog(self.n_coils)
        status = dialog.ShowModal()

        success = status == ID_OK
        if success:
            com_port, probe_dir, ref_dir, obj_dirs = dialog.GetValue()

            self.configuration = {
                "com_port": com_port,
                "probe_dir": probe_dir,
                "ref_dir": ref_dir,
                "obj_dirs": obj_dirs,
            }
        else:
            self.lib_mode = None
            print("Could not connect to polaris tracker.")

        dialog.Destroy()

        return success

    def Connect(self):
        assert self.configuration is not None, "No configuration defined"

        try:
            if sys.platform == "win32":
                import pypolaris

                connection = pypolaris.pypolaris()
            else:
                from pypolaris import pypolaris

                connection = pypolaris.pypolaris()

            lib_mode = "wrapper"

            com_port = self.configuration["com_port"].encode(const.FS_ENCODE)
            probe_dir = self.configuration["probe_dir"].encode(const.FS_ENCODE)
            ref_dir = self.configuration["ref_dir"].encode(const.FS_ENCODE)
            obj_dirs = pypolaris.StringVector()  # SWIG fails to convert python list to vector<string>, so we directly create StringVector
            for obj_dir in self.configuration["obj_dirs"]:
                obj_dirs.append(obj_dir.encode(const.FS_ENCODE))

            if connection.Initialize(com_port, probe_dir, ref_dir, obj_dirs) != 0:
                lib_mode = None
                print("Could not connect to polaris tracker.")
            else:
                print("Connected to polaris tracking device.")
                self.connection = connection

        except Exception:
            lib_mode = "error"
            connection = None
            print("Could not connect to polaris tracker.")

        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class PolarisP4TrackerConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        super().__init__(model)

    def Configure(self):
        dialog = dlg.ConfigurePolarisDialog(1)
        status = dialog.ShowModal()

        success = status == ID_OK
        if success:
            com_port, probe_dir, ref_dir, obj_dir = dialog.GetValue()

            self.configuration = {
                "com_port": com_port,
                "probe_dir": probe_dir,
                "ref_dir": ref_dir,
                "obj_dir": obj_dir,
            }
        else:
            self.lib_mode = None
            print("Could not connect to Polaris P4 tracker.")

        dialog.Destroy()

        return success

    def Connect(self):
        assert self.configuration is not None, "No configuration defined"

        connection = None
        try:
            import pypolarisP4

            lib_mode = "wrapper"
            connection = pypolarisP4.pypolarisP4()

            com_port = self.configuration["com_port"].encode(const.FS_ENCODE)
            probe_dir = self.configuration["probe_dir"].encode(const.FS_ENCODE)
            ref_dir = self.configuration["ref_dir"].encode(const.FS_ENCODE)
            obj_dir = self.configuration["obj_dir"].encode(const.FS_ENCODE)

            if connection.Initialize(com_port, probe_dir, ref_dir, obj_dir) != 0:
                connection = None
                lib_mode = None
                print("Could not connect to Polaris P4 tracker.")
            else:
                print("Connect to Polaris P4 tracking device.")

        except Exception:
            lib_mode = "error"
            connection = None
            print("Could not connect to Polaris P4 tracker.")

        self.connection = connection
        self.lib_mode = lib_mode

    def Disconnect(self):
        super().Disconnect()


class DebugTrackerRandomConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        super().__init__(model)

    def Configure(self):
        return True

    def Connect(self):
        self.connection = True
        self.lib_mode = "debug"
        print("Debug device (random) started.")

    def Disconnect(self):
        self.connection = False
        self.lib_mode = "debug"
        print("Debug tracker (random) disconnected.")


class DebugTrackerApproachConnection(TrackerConnection):
    def __init__(self, model=None, n_coils=1):
        super().__init__(model)

    def Configure(self):
        return True

    def Connect(self):
        self.connection = True
        self.lib_mode = "debug"
        print("Debug device (approach) started.")

    def Disconnect(self):
        self.connection = False
        self.lib_mode = "debug"
        print("Debug tracker (approach) disconnected.")


TRACKER_CONNECTION_CLASSES = {
    const.MTC: ClaronTrackerConnection,
    const.FASTRAK: PolhemusTrackerConnection,
    const.ISOTRAKII: PolhemusTrackerConnection,
    const.PATRIOT: PolhemusTrackerConnection,
    const.CAMERA: CameraTrackerConnection,
    const.POLARIS: PolarisTrackerConnection,
    const.POLARISP4: PolarisP4TrackerConnection,
    const.OPTITRACK: OptitrackTrackerConnection,
    const.DEBUGTRACKRANDOM: DebugTrackerRandomConnection,
    const.DEBUGTRACKAPPROACH: DebugTrackerApproachConnection,
}


def CreateTrackerConnection(tracker_id, n_coils):
    """
    Initialize spatial tracker connection for coordinate detection during navigation.

    :param tracker_id: ID of tracking device.
    :return spatial tracker connection instance or None if could not open device.
    """
    tracker_connection_class = TRACKER_CONNECTION_CLASSES[tracker_id]

    # XXX: A better solution than to pass a 'model' parameter to the constructor of tracker
    #   connection would be to have separate class for each model, possibly inheriting
    #   the same base class, e.g., in this case, PolhemusTrackerConnection base class, which
    #   would be inherited by FastrakTrackerConnection class, etc.
    if tracker_id == const.FASTRAK:
        model = "fastrak"
    elif tracker_id == const.ISOTRAKII:
        model = "isotrak"
    elif tracker_id == const.PATRIOT:
        model = "patriot"
    else:
        model = None

    tracker_connection = tracker_connection_class(model=model, n_coils=n_coils)
    return tracker_connection
