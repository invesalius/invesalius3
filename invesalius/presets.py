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
import glob
import os
import plistlib

import invesalius.constants as const

from wx.lib.pubsub import pub as Publisher

from invesalius.utils import TwoWaysDictionary
class Presets():

    def __init__(self):
        self.thresh_ct = TwoWaysDictionary({
            _("Bone"):(226,3071),
            _("Soft Tissue"):(-700,225),
            _("Enamel (Adult)"):(1553,2850),
            _("Enamel (Child)"):(2042,3071),
            _("Compact Bone (Adult)"):(662,1988),
            _("Compact Bone (Child)"):(586,2198),
            _("Spongial Bone (Adult)"):(148,661),
            _("Spongial Bone (Child)"):(156,585),
            _("Muscle Tissue (Adult)"):(-5,135),
            _("Muscle Tissue (Child)"):(-25,139),
            _("Fat Tissue (Adult)"):(-205,-51),
            _("Fat Tissue (Child)"):(-212,-72),
            _("Skin Tissue (Adult)"):(-718,-177),
            _("Skin Tissue (Child)"):(-766,-202), 
            _("Custom"):('', '')
        })

        self.thresh_mri = TwoWaysDictionary({
            _("Bone"):(1250,4095),
            _("Soft Tissue"):(324,1249),
            _("Enamel (Adult)"):(2577,3874),
            _("Enamel (Child)"):(3066,4095),
            _("Compact Bone (Adult)"):(1686,3012),
            _("Compact Bone (Child)"):(1610,3222),
            _("Spongial Bone (Adult)"):(1172,1685),
            _("Spongial Bone (Child)"):(1180,1609),
            _("Muscle Tissue (Adult)"):(1019,1159),
            _("Muscle Tissue (Child)"):(999,1163),
            _("Fat Tissue (Adult)"):(819,973),
            _("Fat Tissue (Child)"):(812,952),
            _("Skin Tissue (Adult)"):(306,847),
            _("Skin Tissue (Child)"):(258,822), 
            _("Custom"):('', '')
        })
        self.__bind_events()
        
    def __bind_events(self):
        Publisher.subscribe(self.UpdateThresholdModes,
                                'Update threshold limits list')
        
    def UpdateThresholdModes(self, evt):
    
        thresh_min, thresh_max = evt.data
        presets_list = (self.thresh_ct, self.thresh_mri)

        for presets in presets_list:
            for key in presets:
                (t_min, t_max) = presets[key]


                if (t_min is None) or (t_max is None): # setting custom preset
                    t_min = thresh_min
                    t_max = thresh_max
                if (t_min < thresh_min):
                    t_min = thresh_min
                if (t_max > thresh_max):
                    t_max = thresh_max
                    
                # This has happened in Analyze files
                # TODO: find a good solution for presets in Analyze files
                if (t_min > thresh_max):
                    t_min = thresh_min
                if (t_max < thresh_min):
                    t_max = thresh_max

                presets[key] = (t_min, t_max)
                    
        Publisher.sendMessage('Update threshold limits', (thresh_min,     
                                    thresh_max))

    def SavePlist(self, filename):
        filename = "%s$%s" % (filename, 'presets.plist')
        preset = {}
        
        translate_to_en = {_("Bone"):"Bone",
                _("Soft Tissue"):"Soft Tissue",
                _("Enamel (Adult)"):"Enamel (Adult)",
                _("Enamel (Child)"): "Enamel (Child)",
                _("Compact Bone (Adult)"):"Compact Bone (Adult)",
                _("Compact Bone (Child)"):"Compact Bone (Child)",
                _("Spongial Bone (Adult)"):"Spongial Bone (Adult)",
                _("Spongial Bone (Child)"):"Spongial Bone (Child)",
                _("Muscle Tissue (Adult)"):"Muscle Tissue (Adult)",
                _("Muscle Tissue (Child)"):"Muscle Tissue (Child)",
                _("Fat Tissue (Adult)"):"Fat Tissue (Adult)",
                _("Fat Tissue (Child)"):"Fat Tissue (Child)",
                _("Skin Tissue (Adult)"):"Skin Tissue (Adult)",
                _("Skin Tissue (Child)"):"Skin Tissue (Child)", 
                _("Custom"):"Custom"}

        thresh_mri_new = {}
        for name in self.thresh_mri.keys():
            thresh_mri_new[translate_to_en[name]] = self.thresh_mri[name]

        thresh_ct_new = {}
        for name in self.thresh_ct.keys():
            thresh_ct_new[translate_to_en[name]] = self.thresh_ct[name]
        
        preset['thresh_mri'] = thresh_mri_new
        preset['thresh_ct'] = thresh_ct_new
        plistlib.writePlist(preset, filename)
        return os.path.split(filename)[1]

    def OpenPlist(self, filename):

        translate_to_x = {"Bone":_("Bone"),
                "Soft Tissue":_("Soft Tissue"),
                "Enamel (Adult)":_("Enamel (Adult)"),
                "Enamel (Child)": _("Enamel (Child)"),
                "Compact Bone (Adult)": _("Compact Bone (Adult)"),
                "Compact Bone (Child)":_("Compact Bone (Child)"),
                "Spongial Bone (Adult)":_("Spongial Bone (Adult)"),
                "Spongial Bone (Child)":_("Spongial Bone (Child)"),
                "Muscle Tissue (Adult)":_("Muscle Tissue (Adult)"),
                "Muscle Tissue (Child)":_("Muscle Tissue (Child)"),
                "Fat Tissue (Adult)":_("Fat Tissue (Adult)"),
                "Fat Tissue (Child)":_("Fat Tissue (Child)"),
                "Skin Tissue (Adult)":_("Skin Tissue (Adult)"),
                "Skin Tissue (Child)":_("Skin Tissue (Child)"), 
                "Custom":_("Custom")}


        p = plistlib.readPlist(filename)
        thresh_mri = p['thresh_mri'].copy()
        thresh_ct = p['thresh_ct'].copy()

        thresh_ct_new = {}
        for name in thresh_ct.keys(): 
            thresh_ct_new[translate_to_x[name]] = thresh_ct[name]

        thresh_mri_new = {}
        for name in thresh_mri.keys(): 
            thresh_mri_new[translate_to_x[name]] = thresh_mri[name]    

        self.thresh_mri = TwoWaysDictionary(thresh_mri_new)
        self.thresh_ct = TwoWaysDictionary(thresh_ct_new)



def get_wwwl_presets():
    files = glob.glob(os.path.join(const.RAYCASTING_PRESETS_COLOR_DIRECTORY, '*.plist'))
    presets = {}
    for f in files:
        p = os.path.splitext(os.path.basename(f))[0]
        presets[p] = f
    return presets


def get_wwwl_preset_colours(pfile):
    preset = plistlib.readPlist(pfile)
    ncolours = len(preset['Blue'])
    colours = []
    for i in xrange(ncolours):
        r = preset['Red'][i]
        g = preset['Green'][i]
        b = preset['Blue'][i]

        colours.append((r, g, b))

    return colours
