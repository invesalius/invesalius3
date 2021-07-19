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
import invesalius.constants as const
import invesalius.gui.dialogs as dlg
# TODO: Disconnect tracker when a new one is connected
# TODO: Test if there are too many prints when connection fails
# TODO: Redesign error messages. No point in having "Could not connect to default tracker" in all trackers


def TrackerConnection(tracker_id, trck_init, action):
    """
    Initialize or disconnect spatial trackers for coordinate detection during navigation.

    :param tracker_id: ID of tracking device.
    :param trck_init: tracker initialization instance.
    :param action: string with to decide whether connect or disconnect the selected device.
    :return spatial tracker initialization instance or None if could not open device.
    """

    if action == 'connect':
        trck_fcn = {const.MTC: ClaronTracker,
                    const.FASTRAK: PolhemusTracker,    # FASTRAK
                    const.ISOTRAKII: PolhemusTracker,    # ISOTRAK
                    const.PATRIOT: PolhemusTracker,    # PATRIOT
                    const.CAMERA: CameraTracker,      # CAMERA
                    const.POLARIS: PolarisTracker,      # POLARIS
                    const.POLARISP4: PolarisP4Tracker,  # POLARISP4
                    const.OPTITRACK: OptitrackTracker,   #Optitrack
                    const.DEBUGTRACKRANDOM: DebugTrackerRandom,
                    const.DEBUGTRACKAPPROACH: DebugTrackerApproach,
                    const.HYBRID: HybridTracker}

        trck_init = trck_fcn[tracker_id](tracker_id)

    elif action == 'disconnect':
        trck_init = DisconnectTracker(tracker_id, trck_init)

    return trck_init


def DefaultTracker(tracker_id):
    trck_init = None
    try:
        # import spatial tracker library
        print('Connect to default tracking device.')

    except:
        print('Could not connect to default tracker.')

    # return tracker initialization variable and type of connection
    return trck_init, 'wrapper'

def OptitrackTracker(tracker_id):
    """
    Imports optitrack wrapper from Motive 2.2. Initialize cameras, attach listener, loads Calibration, loads User Profile
    (Rigid bodies information).

    Parameters
    ----------
    tracker_id : Optitrack ID

    Returns
    -------
    trck_init : local name for Optitrack module
    """
    trck_init = None
    try:
        import optitrack
        trck_init = optitrack.optr()
        if trck_init.Initialize()==0:
            trck_init.Run() #Runs once Run function, to update cameras.
        else:
            trck_init = None
    except ImportError:
        print('Error')
    return trck_init, 'wrapper'

def PolarisTracker(tracker_id):
    from wx import ID_OK
    trck_init = None
    dlg_port = dlg.SetNDIconfigs()
    if dlg_port.ShowModal() == ID_OK:
        com_port, PROBE_DIR, REF_DIR, OBJ_DIR = dlg_port.GetValue()
        try:
            import pypolaris
            lib_mode = 'wrapper'
            trck_init = pypolaris.pypolaris()

            if trck_init.Initialize(com_port, PROBE_DIR, REF_DIR, OBJ_DIR) != 0:
                trck_init = None
                lib_mode = None
                print('Could not connect to polaris tracker.')
            else:
                print('Connect to polaris tracking device.')

        except:
            lib_mode = 'error'
            trck_init = None
            print('Could not connect to polaris tracker.')
    else:
        lib_mode = None
        print('Could not connect to polaris tracker.')

    # return tracker initialization variable and type of connection
    return trck_init, lib_mode


def PolarisP4Tracker(tracker_id):
    from wx import ID_OK
    trck_init = None
    dlg_port = dlg.SetNDIconfigs()
    if dlg_port.ShowModal() == ID_OK:
        com_port, PROBE_DIR, REF_DIR, OBJ_DIR = dlg_port.GetValue()
        try:
            import pypolarisP4
            lib_mode = 'wrapper'
            trck_init = pypolarisP4.pypolarisP4()

            if trck_init.Initialize(com_port, PROBE_DIR, REF_DIR, OBJ_DIR) != 0:
                trck_init = None
                lib_mode = None
                print('Could not connect to Polaris P4 tracker.')
            else:
                print('Connect to Polaris P4 tracking device.')

        except:
            lib_mode = 'error'
            trck_init = None
            print('Could not connect to Polaris P4 tracker.')
    else:
        lib_mode = None
        print('Could not connect to Polaris P4 tracker.')
    # return tracker initialization variable and type of connection
    return trck_init, lib_mode


def CameraTracker(tracker_id):
    trck_init = None
    try:
        import invesalius.data.camera_tracker as cam
        trck_init = cam.camera()
        trck_init.Initialize()
        print('Connect to camera tracking device.')

    except:
        print('Could not connect to camera tracker.')

    # return tracker initialization variable and type of connection
    return trck_init, 'wrapper'

def ElfinRobot(tracker_id=const.ELFIN):
    trck_init = None
    try:
        import invesalius.data.elfin_robot as elfin
        #TODO: dialog to set IP and port
        trck_init = elfin.elfin_server('143.107.220.251', 10003)
        #trck_init = elfin.elfin_server('169.254.153.251', 10003)
        #trck_init = elfin.elfin_server('127.0.0.1', 10003)
        trck_init.Initialize()
        lib_mode = 'wrapper'
        print('Connect to elfin robot tracking device.')

    except:
        lib_mode = 'disconnect'
        trck_init = None
        print('Could not connect to elfin robot tracker.')

    # return tracker initialization variable and type of connection
    return trck_init, lib_mode

def ClaronTracker(tracker_id):
    import invesalius.constants as const
    from invesalius import inv_paths

    trck_init = None
    try:
        import pyclaron

        lib_mode = 'wrapper'
        trck_init = pyclaron.pyclaron()
        trck_init.CalibrationDir = inv_paths.MTC_CAL_DIR.encode(const.FS_ENCODE)
        trck_init.MarkerDir = inv_paths.MTC_MAR_DIR.encode(const.FS_ENCODE)
        trck_init.NumberFramesProcessed = 1
        trck_init.FramesExtrapolated = 0
        trck_init.PROBE_NAME = const.MTC_PROBE_NAME.encode(const.FS_ENCODE)
        trck_init.REF_NAME = const.MTC_REF_NAME.encode(const.FS_ENCODE)
        trck_init.OBJ_NAME = const.MTC_OBJ_NAME.encode(const.FS_ENCODE)
        trck_init.Initialize()

        if trck_init.GetIdentifyingCamera():
            trck_init.Run()
            print("MicronTracker camera identified.")
        else:
            trck_init = None

    except ImportError:
        lib_mode = 'error'
        print('The ClaronTracker library is not installed.')

    return trck_init, lib_mode


def PolhemusTracker(tracker_id):
    try:
        trck_init = PlhWrapperConnection(tracker_id)
        lib_mode = 'wrapper'
        if not trck_init:
            print('Could not connect with Polhemus wrapper, trying USB connection...')
            trck_init = PlhUSBConnection(tracker_id)
            lib_mode = 'usb'
            if not trck_init:
                print('Could not connect with Polhemus USB, trying serial connection...')
                trck_init = PlhSerialConnection(tracker_id)
                lib_mode = 'serial'
    except:
        trck_init = None
        lib_mode = 'error'
        print('Could not connect to Polhemus by any method.')

    return trck_init, lib_mode


def DebugTrackerRandom(tracker_id):
    trck_init = True
    print('Debug device (random) started.')
    return trck_init, 'debug'


def DebugTrackerApproach(tracker_id):
    trck_init = True
    print('Debug device (approach) started.')
    return trck_init, 'debug'


def PlhWrapperConnection(tracker_id):
    try:
        from time import sleep
        if tracker_id == 2:
            import polhemusFT
            trck_init = polhemusFT.polhemusFT()
        else:
            import polhemus
            trck_init = polhemus.polhemus()

        trck_check = trck_init.Initialize()

        if trck_check:
            # Sequence of runs necessary to throw away unnecessary data
            for n in range(0, 5):
                trck_init.Run()
                sleep(0.175)
        else:
            trck_init = None
            print('Could not connect to Polhemus via wrapper without error: Initialize is False.')
    except:
        trck_init = None
        print('Could not connect to Polhemus via wrapper without error: Import failed.')

    return trck_init


def PlhSerialConnection(tracker_id):
    import serial
    from wx import ID_OK
    trck_init = None
    dlg_port = dlg.SetCOMport()
    if dlg_port.ShowModal() == ID_OK:
        com_port = dlg_port.GetValue()
        try:
            trck_init = serial.Serial(com_port, baudrate=115200, timeout=0.03)

            if tracker_id == 2:
                # Polhemus FASTRAK needs configurations first
                trck_init.write(0x02, str.encode("u"))
                trck_init.write(0x02, str.encode("F"))
            elif tracker_id == 3:
                # Polhemus ISOTRAK needs to set tracking point from
                # center to tip.
                trck_init.write(str.encode("u"))
                trck_init.write(str.encode("F"))
                trck_init.write(str.encode("Y"))

            trck_init.write(str.encode("P"))
            data = trck_init.readlines()
            if not data:
                trck_init = None
                print('Could not connect to Polhemus serial without error.')

        except:
            lib_mode = 'error'
            trck_init = None
            print('Could not connect to Polhemus tracker.')
    else:
        lib_mode = None
        print('Could not connect to Polhemus tracker.')

    return trck_init


def PlhUSBConnection(tracker_id):
    trck_init = None
    try:
        import usb.core as uc
        # Check the idProduct using the usbdeview software, the idProduct is unique for each
        # device and connection fails when is incorrect
        # trck_init = uc.find(idVendor=0x0F44, idProduct=0x0003) [used in a different device]
        trck_init = uc.find(idVendor=0x0F44, idProduct=0xEF12)
        cfg = trck_init.get_active_configuration()
        for i in cfg:
            for x in i:
                # TODO: try better code
                x = x
        trck_init.set_configuration()
        endpoint = trck_init[0][(0, 0)][0]
        if tracker_id == 2:
            # Polhemus FASTRAK needs configurations first
            # TODO: Check configurations to standardize initialization for all Polhemus devices
            trck_init.write(0x02, "u")
            trck_init.write(0x02, "F")
        # First run to confirm that everything is working
        trck_init.write(0x02, "P")
        data = trck_init.read(endpoint.bEndpointAddress,
                              endpoint.wMaxPacketSize)
        if not data:
            trck_init = None
            print('Could not connect to Polhemus USB without error.')

    except:
        print('Could not connect to Polhemus USB with error.')

    return trck_init

def HybridTracker(tracker_id):
    from wx import ID_OK
    trck_init = None
    dlg_device = dlg.SetTrackerDevice2Robot()
    if dlg_device.ShowModal() == ID_OK:
        tracker_id = dlg_device.GetValue()
        trck_init = TrackerConnection(tracker_id, None, 'connect')
        #TODO: deal with errors
    else:
        trck_init = ClaronTracker(1)
    trck_init_robot = ElfinRobot()

    return [trck_init, trck_init_robot, tracker_id, const.ELFIN]


def DisconnectTracker(tracker_id, trck_init):
    """
    Disconnect current spatial tracker

    :param tracker_id: ID of tracking device.
    :param trck_init: Initialization variable of tracking device.
    """

    if tracker_id == const.DEBUGTRACKRANDOM or tracker_id == const.DEBUGTRACKAPPROACH:
        trck_init = False
        lib_mode = 'debug'
        print('Debug tracker disconnected.')
    else:
        try:
            if tracker_id == const.ISOTRAKII:
                trck_init.close()
                trck_init = False
                lib_mode = 'serial'
                print('Tracker disconnected.')
            else:
                trck_init.Close()
                trck_init = False
                lib_mode = 'wrapper'
                print('Tracker disconnected.')
        except:
            trck_init = True
            lib_mode = 'error'
            print('The tracker could not be disconnected.')

    return trck_init, lib_mode
