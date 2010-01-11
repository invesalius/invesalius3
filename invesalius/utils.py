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
import os
import platform
import subprocess
import re
import sys


def debug(error_str):
    from project import Project
    proj = Project()
    if proj.debug:
        print >> stderr, str


#http://www.garyrobinson.net/2004/03/python_singleto.html
# Gary Robinson
class Singleton(type):
    def __init__(cls,name,bases,dic):
        super(Singleton,cls).__init__(name,bases,dic)
        cls.instance=None
    def __call__(cls,*args,**kw):
        if cls.instance is None:
            cls.instance=super(Singleton,cls).__call__(*args,**kw)
        return cls.instance

# Another possible implementation
#class Singleton(object):
#   def __new__(cls, *args, **kwargs):
#      if '_inst' not in vars(cls):
#         cls._inst = type.__new__(cls, *args, **kwargs)
#      return cls._inst

class TwoWaysDictionary(dict):
    """
    Dictionary that can be searched based on a key or on a item.
    The idea is to be able to search for the key given the item it maps.
    """
    def __init__(self, items=[]):
        dict.__init__(self, items)

    def get_key(self, value):
        """
        Find the key(s) as a list given a value.
        """
        return [item[0] for item in self.items() if item[1] == value]

    def get_value(self, key):
        """
        Find the value given a key.
        """
        return self[key]

def frange(start, end=None, inc=None):
    "A range function, that accepts float increments."

    if end == None:
        end = start + 0.0
        start = 0.0

    if (inc == None) or (inc == 0):
        inc = 1.0

    L = []
    while 1:
        next = start + len(L) * inc
        if inc > 0 and next >= end:
            break
        elif inc < 0 and next <= end:
            break
        L.append(next)

    return L


def PredictingMemory(qtd, x, y, p):
    m = qtd * (x * y * p)

    if (sys.platform == 'win32'):

        physical_memory = GetWindowsInformation()[3]

        if (platform.architecture()[0] == '32bit'):
            #(314859200 = 300 MB)
            #(26999999 = 25 MB)

            #case occupy more than 300 MB image is reduced to 1.5,
            #and 25 MB each image is resized 0.04.
            if (m >= 314859200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.04
            else:
                return (x, y)
        else: #64 bits architecture

            if (physical_memory <= 2.0) and (qtd <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.02

            elif(physical_memory <= 2.0) and (qtd > 1200):
                 porcent = 1.5 + (m - 314859200) / 26999999 * 0.03

            elif(physical_memory > 2.0) and (physical_memory <= 4.0) and (qtd <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.01

            else:
                return (x,y)

        return (x/porcent, y/porcent)

    elif(sys.platform == 'linux2'):

        physical_memory = GetLinuxInformation()[2]

        if (platform.architecture()[0] == '32bit'):
            # 839000000 = 800 MB
            if (m <= 839000000) and (physical_memory <= 2.0):
                return (x,y)
            elif (m > 839000000) and (physical_memory <= 2.0) and (qtd <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.02
            else:
                return (x,y)

        else:

            if (m <= 839000000) and (physical_memory <= 2.0):
                return (x, y)
            elif (m > 839000000) and (physical_memory <= 2.0) and (qtd <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.02
            else:
                return (x,y)

        return (x/porcent, y/porcent)

    elif(sys.platform == 'darwin'):

        physical_memory = GetDarwinInformation()

        if (m <= 839000000) and (physical_memory <= 2.0):
            return (x, y)
        elif (m > 839000000) and (physical_memory <= 2.0) and (qtd <= 1200):
            porcent = 1.5 + (m - 314859200) / 26999999 * 0.02
        else:
            return (x, y)

        return (x/porcent,y/porcent)



def BytesConvert(bytes):
    if bytes >= 1073741824:
        return str(bytes / 1024 / 1024 / 1024) + ' GB'
    elif bytes >= 1048576:
        return str(bytes / 1024 / 1024) + ' MB'
    elif bytes >= 1024:
        return str(bytes / 1024) + ' KB'
    elif bytes < 1024:
        return str(bytes) + ' bytes'


def GetWindowsInformation():

    command = "systeminfo"

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info = subprocess.Popen([command], startupinfo=startupinfo,
                            stdout=subprocess.PIPE).communicate()

    lines = info[0].splitlines()

    #Architecture of the system, x86 or x64
    architecture = lines[14]
    architecture = re.findall('[0-9]+', architecture)[0]
    architecture = "x" + architecture

    #Number of processors or number of nucleus
    number_processors = lines[15]
    number_processors = re.findall('[0-9]+', number_processors)[0]

    #Clock of the processor in Mhz
    processor_clock = lines[16]
    processor_clock = re.findall('~[0-9]+', processor_clock)[0]
    processor_clock = float(re.findall('[0-9]+', processor_clock)[0])

    #Total of Physical Memory in MB
    total_physical_memory = lines[24 + (int(number_processors) - 1)]
    total_physical_memory = float(re.findall('[0-9.]+', total_physical_memory)[0])

    #Total of Physical Memory Avaliable in MB
    available_physical_memory = lines[25 + (int(number_processors) - 1)]
    available_physical_memory = float(re.findall('[0-9.]+',
                                      available_physical_memory)[0])

    return (architecture, number_processors,
            processor_clock, total_physical_memory,
            available_physical_memory)

def GetDarwinInformation():
    memory = 2.0
    return (memory)


def GetLinuxInformation():

    #Architecture of the system, x86 or x64
    architecture = LinuxCommand("uname -m")
    architecture = architecture[0].splitlines()[0]

    #Clock of the processor in Mhz
    processor_clock = LinuxCommand("more /proc/cpuinfo")
    processor_clock = processor_clock[0].splitlines()
    processor_clock = float(re.findall('[0-9.]+', processor_clock[6])[0])


    #processor_clock = float(re.findall('[0-9]+', processor_clock)[0])
    return (architecture, processor_clock, 2.0)


def LinuxCommand(command):
    return subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).communicate()


