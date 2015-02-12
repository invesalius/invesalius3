import ClaronTracker
import usb.core
import serial
import usb.util
import sys
import gui.dialogs as dlg


class Tracker_Init: 
    def PolhemusISO_init(self):
        try:
            plh = serial.Serial(0, baudrate = 115200, timeout=0.2)
            return plh
            
        except:
            dlg.TrackerNotConnected(1)
            raise ValueError('Device not found')  
    
    def Polhemus_init(self):
        dev = usb.core.find(idVendor=0x0F44, idProduct=0xEF12)
        if dev is None:
            dlg.TrackerNotConnected(1)
            raise ValueError('Device not found')  
        try:
            cfg = dev.get_active_configuration()
            for i in cfg:
                for x in i:
                    x = x        
            dev.set_configuration()
        except usb.core.USBError as e:
            sys.exit("Could not set configuration: %s" % str(e))
        return dev
    
    def Claron_init(self):
        try:
            mtc = ClaronTracker.ClaronTracker()
            mtc.CalibrationDir = "C:\CalibrationFiles"
            mtc.MarkerDir = "C:\Markers"
            mtc.NumberFramesProcessed = 10
            mtc.FramesExtrapolated = 0
            mtc.Initialize()
            if mtc.GetIdentifyingCamera():
                print "Camera Identified."
                mtc.Run()
            else:
                dlg.TrackerNotConnected(2)
                print "The Claron MicronTracker is not connected!"
            return mtc
        
        except:
            dlg.TrackerNotConnected(2)
            raise ValueError('Device not found') 
         
        
    def Zebris_init(self):
        dlg.TrackerNotConnected(3)
        return