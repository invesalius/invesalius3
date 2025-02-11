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
import collections.abc
import locale
import math
import platform
import re
import sys
import time
import traceback
from functools import wraps
from typing import Any, List, Optional

import numpy as np
from packaging.version import Version


def format_time(value: str) -> str:
    sp1 = value.split(".")
    sp2 = value.split(":")

    if (len(sp1) == 2) and (len(sp2) == 3):
        new_value = str(sp2[0] + sp2[1] + str(int(float(sp2[2]))))
        data = time.strptime(new_value, "%H%M%S")
    elif len(sp1) == 2:
        data = time.gmtime(float(value))
    elif len(sp1) > 2:
        data = time.strptime(value, "%H.%M.%S")
    elif len(sp2) > 1:
        data = time.strptime(value, "%H:%M:%S")
    else:
        try:
            data = time.strptime(value, "%H%M%S")
        # If the time is not in a bad format only return it.
        except ValueError:
            return value
    return time.strftime("%H:%M:%S", data)


def format_date(value: str) -> str:
    sp1 = value.split(".")
    try:
        if len(sp1) > 1:
            if len(sp1[0]) <= 2:
                data = time.strptime(value, "%D.%M.%Y")
            else:
                data = time.strptime(value, "%Y.%M.%d")
        elif len(value.split("//")) > 1:
            data = time.strptime(value, "%D/%M/%Y")
        else:
            data = time.strptime(value, "%Y%M%d")
        return time.strftime("%d/%M/%Y", data)

    except ValueError:
        return ""


def debug(error_str: str) -> None:
    """
    Redirects output to file, or to the terminal
    This should be used in the place of "print"
    """
    from invesalius.session import Session

    session = Session()
    if session.GetConfig("debug"):
        print(error_str)


def next_copy_name(original_name: str, names_list: List[str]) -> str:
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
                first_copy = f"{parts[0]} copy"
            # no... well, so will build the copy name from zero
            else:
                last_index = -1
                first_copy = f"{original_name} copy"
                # apparently this isthe new copy name, check it
                if first_copy not in names_list:
                    return first_copy

        else:
            # no, apparently there are no copies, as
            # separator was not found -- returned ("", " copy#", "")
            last_index = -1
            first_copy = f"{original_name} copy"

            # apparently this isthe new copy name, check it
            if first_copy not in names_list:
                return first_copy

    # lets build up the new name based on last pattern value
    got_new_name = False
    while not got_new_name:
        last_index += 1
        next_copy = "%s#%d" % (first_copy, last_index + 1)
        if next_copy not in names_list:
            got_new_name = True
    return next_copy


def new_name_by_pattern(pattern: str) -> str:
    from invesalius.project import Project

    proj = Project()
    mask_dict = proj.mask_dict
    names_list = [i.name for i in mask_dict.values() if i.name.startswith(pattern + "_")]
    count = len(names_list) + 1
    return f"{pattern}_{count}"


def VerifyInvalidPListCharacter(text: str) -> bool:
    # print text
    # text = unicode(text)

    _controlCharPat = re.compile(
        r"[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
        r"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f]"
    )
    m = _controlCharPat.search(text)

    if m is not None:
        return True
    else:
        return False


# http://www.garyrobinson.net/2004/03/python_singleto.html
# Gary Robinson
class Singleton(type):
    def __init__(cls, name, bases, dic):
        super().__init__(name, bases, dic)
        cls.instance = None

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super().__call__(*args, **kw)
        return cls.instance


# Another possible implementation
# class Singleton(object):
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
        Find the key (first) with the given value
        """
        return self.get_keys(value)[0]

    def get_keys(self, value):
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


# DEPRECATED
def frange(start: float, end: Optional[float] = None, inc: Optional[float] = None) -> List[float]:
    "A range function, that accepts float increments."

    if end is None:
        end = start + 0.0
        start = 0.0

    if (inc is None) or (inc == 0):
        inc = 1.0

    L: List[float] = []
    while 1:
        next = start + len(L) * inc
        if inc > 0 and next >= end:
            break
        elif inc < 0 and next <= end:
            break
        L.append(next)

    return L


# Deprecated
def calculate_resizing_tofitmemory(x_size, y_size, n_slices, byte):
    """
    Predicts the percentage (between 0 and 1) to resize the image to fit the memory,
    giving the following information:
        x_size, y_size: image size
        n_slices: number of slices
        byte: bytes allocated for each pixel sample
    """
    imagesize = x_size * y_size * n_slices * byte * 28

    #  USING LIBSIGAR
    # import sigar
    # sg = sigar.open()
    # ram_free = sg.mem().actual_free()
    # ram_total = sg.mem().total()
    # swap_free = sg.swap().free()
    # sg.close()

    # USING PSUTIL
    import psutil

    try:
        if psutil.version_info >= (0, 6, 0):
            ram_free = psutil.virtual_memory().available
            ram_total = psutil.virtual_memory().total
            swap_free = psutil.swap_memory().free
        else:
            ram_free = psutil.phymem_usage().free + psutil.cached_phymem() + psutil.phymem_buffers()
            ram_total = psutil.phymem_usage().total
            swap_free = psutil.virtmem_usage().free
    except Exception:
        print("Exception! psutil version < 0.3 (not recommended)")
        ram_total = psutil.TOTAL_PHYMEM  # this is for psutil < 0.3
        ram_free = 0.8 * psutil.TOTAL_PHYMEM
        swap_free = psutil.avail_virtmem()

    print("RAM_FREE=", ram_free)
    print("RAM_TOTAL=", ram_total)

    if sys.platform == "win32":
        if platform.architecture()[0] == "32bit":
            if ram_free > 1400000000:
                ram_free = 1400000000
            if ram_total > 1400000000:
                ram_total = 1400000000

    if sys.platform.startswith("linux"):
        if platform.architecture()[0] == "32bit":
            if ram_free > 3500000000:
                ram_free = 3500000000
            if ram_total > 3500000000:
                ram_total = 3500000000

    if swap_free > ram_total:
        swap_free = ram_total
    resize = float((ram_free + 0.5 * swap_free) / imagesize)
    resize = math.sqrt(resize)  # this gives the "resize" for each axis x and y
    if resize > 1:
        resize = 1
    return round(resize, 2)


def get_system_encoding() -> Optional[str]:
    if sys.platform == "win32":
        return locale.getdefaultlocale()[1]
    else:
        return "utf-8"


def UpdateCheck() -> None:
    try:
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
    except ImportError:
        from urllib import urlencode

        from urllib2 import Request, urlopen

    import wx

    import invesalius.session as ses

    def _show_update_info():
        from invesalius.gui import dialogs
        # from invesalius.i18n import tr as _

        # msg = _(
        #     "A new version of InVesalius is available. Do you want to open the download website now?"
        # )
        # title = _("Invesalius Update")
        msgdlg = dialogs.UpdateMessageDialog(url)
        # if (msgdlg.Show()==wx.ID_YES):
        # wx.LaunchDefaultBrowser(url)
        msgdlg.Show()
        # msgdlg.Destroy()

    print("Checking updates...")

    # Check if a language has been set.
    session = ses.Session()
    lang = session.GetConfig("language")
    random_id = session.GetConfig("random_id")

    if lang:
        # Fetch update data from server
        import invesalius.constants as const

        url = "https://www.cti.gov.br/dt3d/invesalius/update/checkupdate.php"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MSIE 5.5; Windows NT)"}
        data: Any = {
            "update_protocol_version": "1",
            "invesalius_version": const.INVESALIUS_VERSION,
            "platform": sys.platform,
            "architecture": platform.architecture()[0],
            "language": lang,
            "random_id": random_id,
        }
        data = urlencode(data).encode("utf8")
        req = Request(url, data, headers)
        try:
            response = urlopen(req, timeout=10)
        except Exception:
            return
        last = response.readline().rstrip().decode("utf8")
        url = response.readline().rstrip().decode("utf8")

        try:
            last_ver = Version(last)
            actual_ver = Version(const.INVESALIUS_VERSION)
        except (ValueError, AttributeError):
            return

        if last_ver > actual_ver:
            print("  ...New update found!!! -> version:", last)  # , ", url=",url
            wx.CallAfter(wx.CallLater, 1000, _show_update_info)


def vtkarray_to_numpy(m):
    nm = np.zeros((4, 4))
    for i in range(4):
        for j in range(4):
            nm[i, j] = m.GetElement(i, j)
    return nm


def touch(fname: str) -> None:
    with open(fname, "a"):
        pass


def decode(text: Any, encoding: str, *args) -> Any:
    try:
        return text.decode(encoding, *args)
    except AttributeError:
        return text


def encode(text: Any, encoding: str, *args) -> Any:
    try:
        return text.encode(encoding, *args)
    except AttributeError:
        return text


def timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        print(f"{f.__name__} elapsed time: {end - start}")
        return result

    return wrapper


def log_traceback(ex: Any) -> str:
    if hasattr(ex, "__traceback__"):
        ex_traceback = ex.__traceback__
    else:
        _, _, ex_traceback = sys.exc_info()
    tb_lines = [
        line.rstrip("\n") for line in traceback.format_exception(ex.__class__, ex, ex_traceback)
    ]
    return "".join(tb_lines)


def deep_merge_dict(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_merge_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d
