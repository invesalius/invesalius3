import gdcm

class DicomNet:
    
    def __init__(self):
        self.address = ''
        self.port = ''
        self.aetitle_call = ''
        self.aetitle = ''
   
    def SetHost(self, address):
        self.address = address

    def SetPort(self, port):
        self.port = port

    def SetAETitleCall(self, name):
        self.aetitle_call = name

    def SetAETitle(self, ae_title):
        self.aetitle = ae_title

    def RunCEcho(self):
        cnf = gdcm.CompositeNetworkFunctions()
        return cnf.CEcho(self.address, int(self.port),\
                         self.aetitle, self.aetitle_call)
