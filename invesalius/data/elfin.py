#!/usr/bin/env python3

import sys
from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM

class elfin:
    def __init__(self):
        self.end_msg = ",;"

    def connect(self, SERVER_IP, PORT_NUMBER, SIZE, rbtID):
        mySocket = socket(AF_INET, SOCK_STREAM)
        mySocket.connect((SERVER_IP, PORT_NUMBER))

        self.size = SIZE
        self.rbtID = str(rbtID)
        self.mySocket = mySocket

    def send(self, message):
        self.mySocket.sendall(message.encode('utf-8'))
        data = self.mySocket.recv(self.size).decode('utf-8').split(',')
        status = self.check_status(data)
        if status and type(data) != bool:
            if len(data) > 3:
                return data[2:-1]
        return status

    def check_status(self, recv_message):
        status = recv_message[1]
        if status == 'OK':
            return True

        elif status == 'Fail':
            print("Error code: ", recv_message[2])
            return False

    def Electrify(self):
        """
        Function: Power the robot
        Notes: successful completion of power up before returning, power up time is
        about 44s.
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "Electrify" + self.end_msg
        status = self.send(message)
        return status

    def BlackOut(self):
        """
        Function: Robot blackout
        Notes: successful power outage will only return, power failure time is 3s.
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "BlackOut" + self.end_msg
        status = self.send(message)
        return status

    def StartMaster(self):
        """
        Function: Start master station
        Notes: the master station will not be returned until successfully started, startup
        master time is about 4s.
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "StartMaster" + self.end_msg
        status = self.send(message)
        return status

    def CloseMaster(self):
        """
        Function: Close master station
        Notes: the master station will not be returned until successfully closed, shut
        down the master station time is about 2s.
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "CloseMaster" + self.end_msg
        status = self.send(message)
        return status

    def GrpPowerOn(self):
        """
        Function: Robot servo on
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "GrpPowerOn," + self.rbtID + self.end_msg
        status = self.send(message)
        return status

    def GrpPowerOff(self):
        """
        Function: Robot servo off
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "GrpPowerOff," + self.rbtID + self.end_msg
        status = self.send(message)
        return status

    def GrpStop(self):
        """
        Function: Stop robot
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "GrpStop," + self.rbtID + self.end_msg
        status = self.send(message)
        return status

    def SetOverride(self, override):
        """
        function: Set speed ratio
        :param override:
            double: set speed ratio, range of 0.01~1
        :return:
        if Error Return False
            if not Error Return True
        """

        message = "SetOverride," + self.rbtID + ',' + str(override) + self.end_msg
        status = self.send(message)
        return status

    def ReadPcsActualPos(self):
        """Function: Get the actual position of the space coordinate
        :return:
            if True Return x,y,z,a,b,c
            if Error Return False
        """
        message = "ReadPcsActualPos," + self.rbtID + self.end_msg
        coord = self.send(message)
        if coord:
            return [float(s) for s in coord]

        return coord

    def MoveL(self, target):
        """
        function: Robot moves straight to the specified space coordinates
        :param: target:[X,Y,Z,RX,RY,RZ]
        :return:
        """
        target = [str(s) for s in target]
        target = (",".join(target))
        message = "MoveL," + self.rbtID + ',' + target + self.end_msg
        return self.send(message)

    def SetToolCoordinateMotion(self, status):
        """
        function: Function: Set tool coordinate motion
        :param: int Switch 0=close 1=open
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "SetToolCoordinateMotion," + self.rbtID + ',' + str(status) + self.end_msg
        status = self.send(message)
        return status

    def ReadMoveState(self):
        """
        Function: Get the motion state of the robot
        :return:
            Current state of motion of robot:
            0=motion completion;
            1009=in motion;
            1013=waiting for execution;
            1025 =Error reporting
        """
        message = "ReadMoveState," + self.rbtID + self.end_msg
        status = int(self.send(message)[0])
        return status

    def MoveHoming(self):
        """
        Function: Robot returns to the origin
        :return:
            if Error Return False
            if not Error Return True
        """
        message = "MoveHoming," + self.rbtID + self.end_msg
        status = self.send(message)
        return status

    def MoveC(self, target):
        """
        function: Arc motion
        :param: Through position[X,Y,Z],GoalCoord[X,Y,Z,RX,RY,RZ],Type[0 or 1],;
        :return:
        """
        target = [str(s) for s in target]
        target = (",".join(target))
        message = "MoveC," + self.rbtID + ',' + target + self.end_msg
        return self.send(message)
