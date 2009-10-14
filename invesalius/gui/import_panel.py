import wx
import wx.gizmos as gizmos
import wx.lib.pubsub as ps
import wx.lib.splitter as spl

import dicom_preview_panel as dpp

class Panel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5),
                          size=wx.Size(280, 656))
        
        sizer = wx.BoxSizer(wx.VERTICAL)        
        sizer.Add(InnerPanel(self), 1, wx.EXPAND|wx.GROW|wx.ALL, 5)
        self.SetSizer(sizer)

# Inner fold panel
class InnerPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, pos=wx.Point(5, 5),
                          size=wx.Size(680, 656))
        
        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.VERTICAL)
        self.splitter = splitter
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)
        
        self.text_panel = TextPanel(splitter)
        splitter.AppendWindow(self.text_panel, 250)
        
        self.image_panel = ImagePanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)
        
        self.__bind_evt()
        
    def __bind_evt(self):
        ps.Publisher().subscribe(self.ShowDicomPreview, "Load import panel")
        
    def ShowDicomPreview(self, pubsub_evt):
        dict = pubsub_evt.data
        self.text_panel.Populate(dict)
        
        
class TextPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour((255,0,0))
        self.Bind(wx.EVT_SIZE, self.OnSize)
        
        
        tree = gizmos.TreeListCtrl(self, -1, style =
                                        wx.TR_DEFAULT_STYLE
                                        | wx.TR_HIDE_ROOT
                                        | wx.TR_ROW_LINES
                                        | wx.TR_COLUMN_LINES
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                        )
                                   
                                   
        tree.AddColumn("Patient name")
        tree.AddColumn("Patient ID")
        tree.AddColumn("Age")
        tree.AddColumn("Gender")
        tree.AddColumn("Study description")
        tree.AddColumn("Modality")
        tree.AddColumn("Date acquired")
        tree.AddColumn("# Images")
        tree.AddColumn("Institution")
        tree.AddColumn("Date of birth")
        tree.AddColumn("Accession Number")
        tree.AddColumn("Referring physician")

        tree.SetMainColumn(0)        # the one with the tree in it...
        tree.SetColumnWidth(0, 280)  # Patient name
        tree.SetColumnWidth(1, 110)  # Patient ID
        tree.SetColumnWidth(2, 40)   # Age
        tree.SetColumnWidth(3, 60)   # Gender
        tree.SetColumnWidth(4, 160)  # Study description
        tree.SetColumnWidth(5, 70)   # Modality
        tree.SetColumnWidth(6, 200)  # Date acquired
        tree.SetColumnWidth(7, 70)   # Number Images
        tree.SetColumnWidth(8, 130)  # Institution
        tree.SetColumnWidth(9, 100)  # Date of birth
        tree.SetColumnWidth(10, 140) # Accession Number
        tree.SetColumnWidth(11, 160) # Referring physician
        

        self.root = tree.AddRoot("InVesalius Database")
        self.tree = tree

    def Populate(self, dict):
        tree = self.tree

        i = 0

        # For each patient on dictionary
        for patient_name in dict:
            # In spite of the patient name, we'll show number of
            # series also
            title = patient_name + " (%d series)"%(len(dict[patient_name]))
            parent = tree.AppendItem(self.root, title)
            patient_data = dict[patient_name]
            
            # Row background colour
            if i%2:
                tree.SetItemBackgroundColour(parent, (242,246,254))
            
            # Insert patient data into columns based on first series
            for item in xrange(1, len(patient_data[0])-1):
                value = patient_data[0][item]
                # Sum slices of all patient's series
                if (item == 7):
                    value = 0
                    for series in xrange(len(patient_data)):
                        value += int(patient_data[series][7])
                tree.SetItemText(parent, str(value), item) # ID

            # For each series on patient 
            j = 0
            for series in xrange(len(patient_data)):
                series_title = patient_data[series][0]

                child = self.tree.AppendItem(parent, series_title)
                if not j%2:
                    tree.SetItemBackgroundColour(child, (242,246,254))

                # TODO: change description "protocol_name"
                description = patient_data[series][-1]
                modality = patient_data[series][5]
                # TODO: add to date the time
                date = patient_data[series][6]
                nimages = patient_data[series][7]

                tree.SetItemText(child, series_title, 0)
                tree.SetItemText(child, description, 4)
                tree.SetItemText(child, modality, 5)
                tree.SetItemText(child, date, 6)
                tree.SetItemText(child, nimages, 7)

                j += 1
            i += 1 
        
        tree.Expand(self.root)
        
        tree.GetMainWindow().Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
        tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)


    def OnActivate(self, evt):
        print 'OnActivate: %s' % self.tree.GetItemText(evt.GetItem())
        

    def OnRightUp(self, evt):
        pos = evt.GetPosition()
        item, flags, col = self.tree.HitTest(pos)
        if item:
            print 'Flags: %s, Col:%s, Text: %s' %\
                           (flags, col, self.tree.GetItemText(item, col))

    def OnSize(self, evt):
        self.tree.SetSize(self.GetSize())
        
class ImagePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour((0,255,0))
        
        splitter = spl.MultiSplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetOrientation(wx.HORIZONTAL)
        self.splitter = splitter
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(sizer)
        
        self.text_panel = SeriesPanel(splitter)
        splitter.AppendWindow(self.text_panel, 600)
        
        self.image_panel = SlicePanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)
        
class SeriesPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour((0,0,0))
        self.serie_preview = dpp.DicomPreviewSeries(self)

        self.__bind_evt()

    def __bind_evt(self):
        ps.Publisher().subscribe(self.ShowDicomSeries, "Load dicom preview")

    def ShowDicomSeries(self, pubsub_evt):
        print "---- ShowDicomSeries ----"
        list_dicom = pubsub_evt.data
        print list_dicom
        self.serie_preview.SetDicomSeries(list_dicom)
        


class SlicePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour((255,255,255))
