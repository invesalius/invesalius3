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

    if inc == None:
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