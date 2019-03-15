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
# TODO: Disconnect tracker when a new one is connected
# TODO: Test if there are too many prints when connection fails


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
                    const.DEBUGTRACK: DebugTracker}

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

def PolarisTracker(tracker_id):
    trck_init = None
    try:
        import pypolaris
        trck_init = pypolaris.pypolaris()
        trck_init.Initialize(const.NDICOMPORT)
        print('Connect to polaris tracking device.')

    except:
        print('Could not connect to default tracker.')

    # return tracker initialization variable and type of connection
    return trck_init, 'wrapper'

def CameraTracker(tracker_id):
    trck_init = None
    try:
        import invesalius.data.camera_tracker as cam
        trck_init = cam.camera()
        trck_init.Initialize()
        print('Connect to camera tracking device.')

    except:
        print('Could not connect to default tracker.')

    # return tracker initialization variable and type of connection
    return trck_init, 'wrapper'

def ClaronTracker(tracker_id):
    trck_init = None
    try:
        import pyclaron

        lib_mode = 'wrapper'
        trck_init = pyclaron.pyclaron()
        trck_init.CalibrationDir = const.CAL_DIR.encode(const.FS_ENCODE)
        trck_init.MarkerDir = const.MAR_DIR.encode(const.FS_ENCODE)
        trck_init.NumberFramesProcessed = 1
        trck_init.FramesExtrapolated = 0
        trck_init.PROBE_NAME = const.PROBE_NAME.encode(const.FS_ENCODE)
        trck_init.REF_NAME = const.REF_NAME.encode(const.FS_ENCODE)
        trck_init.OBJ_NAME = const.OBJ_NAME.encode(const.FS_ENCODE)
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
        print('Could not connect to Polhemus.')

    return trck_init, lib_mode


def DebugTracker(tracker_id):
    trck_init = True
    print('Debug device started.')
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
            print('Could not connect to Polhemus via wrapper without error.')
    except:
        trck_init = None
        print('Could not connect to Polhemus via wrapper with error.')

    return trck_init


def PlhSerialConnection(tracker_id):
    import serial

    trck_init = serial.Serial('COM3', baudrate=115200, timeout=0.03)

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


def DisconnectTracker(tracker_id, trck_init):
    """
    Disconnect current spatial tracker

    :param tracker_id: ID of tracking device.
    :param trck_init: Initialization variable of tracking device.
    """

    if tracker_id == const.DEBUGTRACK:
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
