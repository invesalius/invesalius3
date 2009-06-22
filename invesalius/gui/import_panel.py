import wx
import wx.gizmos as gizmos
import wx.lib.pubsub as ps
import wx.lib.splitter as spl

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
        
        
        self.tree = gizmos.TreeListCtrl(self, -1, style =
                                        wx.TR_DEFAULT_STYLE
                                        | wx.TR_HIDE_ROOT
                                        | wx.TR_ROW_LINES
                                        | wx.TR_COLUMN_LINES
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                        | wx.TR_FULL_ROW_HIGHLIGHT
                                        )
                                   
                                   
        self.tree.AddColumn("Patient name")
        self.tree.AddColumn("Patient ID")
        self.tree.AddColumn("Age")
        self.tree.AddColumn("Study description")
        self.tree.AddColumn("Modality")
        self.tree.AddColumn("Date acquired")
        self.tree.AddColumn("# Images")
        self.tree.AddColumn("Institution")
        self.tree.AddColumn("Date of birth")
        self.tree.AddColumn("Accession Number")
        self.tree.AddColumn("Referring physician")
        self.tree.AddColumn("Performing")

        self.tree.SetMainColumn(0) # the one with the tree in it...
        self.tree.SetColumnWidth(0, 250) # ok
        self.tree.SetColumnWidth(1, 80) # ok
        self.tree.SetColumnWidth(2, 40) # ok
        self.tree.SetColumnWidth(3, 160) # ok
        self.tree.SetColumnWidth(4, 80) # ok
        self.tree.SetColumnWidth(5, 110)
        self.tree.SetColumnWidth(6, 70)
        self.tree.SetColumnWidth(7, 90)
        self.tree.SetColumnWidth(8, 130)
        self.tree.SetColumnWidth(9, 240)
        self.tree.SetColumnWidth(10, 120)
        

        self.root = self.tree.AddRoot("InVesalius Database")

    def Populate(self, dict):
        
        for i in xrange(4):
            txt = "Name %d" % i
            child = self.tree.AppendItem(self.root, txt)
            if i%2:
                self.tree.SetItemBackgroundColour(child, (242,246,254))
            self.tree.SetItemText(child, txt, 1)
            self.tree.SetItemText(child, "age", 2)
            
            for j in xrange(4):
                txt = "Series name %d" % i
                child2 = self.tree.AppendItem(child, txt)
                if j%2:
                    self.tree.SetItemBackgroundColour(child2, (242,246,254))
                self.tree.SetItemText(child2, txt, 1)
                self.tree.SetItemText(child2, txt, 2)
        
        
        self.tree.Expand(self.root)
        
        self.tree.GetMainWindow().Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
        self.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate)


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
        splitter.AppendWindow(self.text_panel, 400)
        
        self.image_panel = SlicePanel(splitter)
        splitter.AppendWindow(self.image_panel, 250)
        
class SeriesPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour((255,255,255))
        
class SlicePanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour((0,0,0))