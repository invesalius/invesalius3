import wx.lib.pubsub as ps

from utils import TwoWaysDictionary

class Presets():

    def __init__(self):
        self.thresh_ct = TwoWaysDictionary({
            "Bone":(226,3071),
            "Soft Tissue":(-700,225),
            "Enamel (Adult)":(1553,2850),
            "Enamel (Child)":(2042,3071),
            "Compact Bone (Adult)":(662,1988),
            "Compact Bone (Child)":(586,2198),
            "Spongial Bone (Adult)":(148,661),
            "Spongial Bone (Child)":(156,585),
            "Muscle Tissue (Adult)":(-5,135),
            "Muscle Tissue (Child)":(-25,139),
            "Fat Tissue (Adult)":(-205,-51),
            "Fat Tissue (Adult)":(-212,-72),
            "Skin Tissue (Adult)":(-718,-177),
            "Skin Tissue (Child)":(-766,-202), 
            "Custom":(None, None)
        })

        self.thresh_mri = TwoWaysDictionary({
            "Bone":(1250,4095),
            "Soft Tissue":(324,1249),
            "Enamel (Adult)":(2577,3874),
            "Enamel (Child)":(3066,4095),
            "Compact Bone (Adult)":(1686,3012),
            "Compact Bone (Child)":(1610,3222),
            "Spongial Bone (Adult)":(1172,1685),
            "Spongial Bone (Child)":(1180,1609),
            "Muscle Tissue (Adult)":(1019,1159),
            "Muscle Tissue (Child)":(999,1163),
            "Fat Tissue (Adult)":(819,973),
            "Fat Tissue (Adult)":(812,952),
            "Skin Tissue (Adult)":(306,847),
            "Skin Tissue (Child)":(258,822), 
            "Custom":(None, None)
        })
        self.__bind_events()
        
    def __bind_events(self):
        ps.Publisher.subscribe(self.UpdateThresholdModes,
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
                    
        ps.Publisher().sendMessage('Update threshold limits', (thresh_min,     
                                    thresh_max))
