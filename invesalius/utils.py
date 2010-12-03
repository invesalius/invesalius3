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
import platform
import sigar
import sys
import re
import locale

def debug(error_str):
    """
    Redirects output to file, or to the terminal
    This should be used in the place of "print"
    """
    from session import Session
    session = Session()
    if session.debug:
        print >> sys.stderr, error_str

def next_copy_name(original_name, names_list):
    """
    Given original_name of an item and a list of existing names,
    builds up the name of a copy, keeping the pattern:
        original_name
        original_name copy
        original_name copy#1
    """
    # is there only one copy, unnumbered?
    if original_name.endswith(" copy"):
        first_copy = original_name
        last_index = -1
    else:
        parts = original_name.rpartition(" copy#")
        # is there any copy, might be numbered?
        if parts[0] and parts[-1]: 
            # yes, lets check if it ends with a number
            if isinstance(eval(parts[-1]), int):
                last_index = int(parts[-1]) - 1 
                first_copy="%s copy"%parts[0]
            # no... well, so will build the copy name from zero
            else:
                last_index = -1
                first_copy = "%s copy"%original_name
                # apparently this isthe new copy name, check it
                if not (first_copy in names_list):
                    return first_copy
  
        else:
            # no, apparently there are no copies, as
            # separator was not found -- returned ("", " copy#", "")
            last_index = -1 
            first_copy = "%s copy"%original_name

            # apparently this isthe new copy name, check it 
            if not (first_copy in names_list):
                return first_copy

    # lets build up the new name based on last pattern value
    got_new_name = False
    while not got_new_name:
        last_index += 1
        next_copy = "%s#%d"%(first_copy, last_index+1)
        if not (next_copy in names_list):
            got_new_name = True
            return next_copy
                

def VerifyInvalidPListCharacter(text):
    #print text
    #text = unicode(text)
    
    _controlCharPat = re.compile(
    r"[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
    r"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f]")
    m = _controlCharPat.search(text)

    if m is not None:
        return True
    else:
        False


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

    def remove(self, key):
        try:
            self.pop(key)
        except TypeError:
            debug("TwoWaysDictionary: no item")

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


def predict_memory(nfiles, x, y, p):
    """
    Predict how much memory will be used, giving the following
    information:
        nfiles: number of dicom files
        x, y: dicom image size
        p: bits allocated for each pixel sample
    """
    m = nfiles * (x * y * p)
    #physical_memory in Byte
    physical_memory = get_physical_memory()

    if (sys.platform == 'win32'):

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

            #2147483648 byte = 2.0 GB
            #4294967296 byte = 4.0 GB

            if (physical_memory <= 2147483648) and (nfiles <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.04

            elif(physical_memory <= 2147483648) and (nfiles > 1200):
                 porcent = 1.5 + (m - 314859200) / 26999999 * 0.05

            elif(physical_memory > 2147483648) and \
                    (physical_memory <= 4294967296) and (nfiles <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.02

            else:
                return (x,y)

        return (x/porcent, y/porcent)

    elif(sys.platform == 'linux2'):

        if (platform.architecture()[0] == '32bit'):
            # 839000000 = 800 MB
            if (m <= 839000000) and (physical_memory <= 2147483648):
                return (x,y)
            elif (m > 839000000) and (physical_memory <= 2147483648) and (nfiles <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.02
            else:
                return (x,y)

        else:

            if (m <= 839000000) and (physical_memory <= 2147483648):
                return (x, y)
            elif (m > 839000000) and (physical_memory <= 2147483648) and (nfiles <= 1200):
                porcent = 1.5 + (m - 314859200) / 26999999 * 0.02
            else:
                return (x,y)

        return (x/porcent, y/porcent)

    elif(sys.platform == 'darwin'):
        return (x/2,y/2)



#def convert_bytes(bytes):
#    if bytes >= 1073741824:
#        return str(bytes / 1024 / 1024 / 1024) + ' GB'
#    elif bytes >= 1048576:
#        return str(bytes / 1024 / 1024) + ' MB'
#    elif bytes >= 1024:
#        return str(bytes / 1024) + ' KB'
#    elif bytes < 1024:
#        return str(bytes) + ' bytes'


def get_physical_memory():
    """
    Return physical memory in bytes
    """
    sg = sigar.open()
    mem = sg.mem()
    sg.close()
    return int(mem.total())


def get_system_encoding():
    if (sys.platform == 'win32'):
        return locale.getdefaultlocale()[1]
    else:
        return 'utf-8'
