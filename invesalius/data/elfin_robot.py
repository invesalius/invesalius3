import invesalius.data.elfin as elfin

class elfin_server():
    def __init__(self, server_ip='169.254.153.251', port_number=10003):
        self.server_ip = server_ip
        self.port_number = port_number
        #print(cobot.ReadPcsActualPos())

    def Initialize(self):
        SIZE = 1024
        rbtID = 0
        self.cobot = elfin.elfin()
        self.cobot.connect(self.server_ip, self.port_number, SIZE, rbtID)
        print("conected!")

    def Run(self):
        #target = [540.0, -30.0, 850.0, 140.0, -81.0, -150.0]
        #print("starting move")
        return self.cobot.ReadPcsActualPos()

    def SendCoordinates(self, target):
        status = self.cobot.ReadMoveState()
        if status != 1009:
            self.cobot.MoveL(target)

    def Close(self):
        self.cobot.close()