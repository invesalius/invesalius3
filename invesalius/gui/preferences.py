import wx

ID = wx.NewId()

try:
    from agw import flatnotebook as fnb
except ImportError: # if it's not there locally, try the wxPython lib.
    import wx.lib.agw.flatnotebook as fnb


class Preferences(wx.Dialog):

    def __init__( self, parent, id = ID, title = "Preferences", size=wx.DefaultSize,\
                                pos=wx.DefaultPosition, style=wx.DEFAULT_DIALOG_STYLE):
    
        pre = wx.PreDialog()
        pre.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        pre.Create(parent, ID, title, pos, size, style)

        self.PostCreate(pre)

        sizer = wx.BoxSizer(wx.VERTICAL)
    
        bookStyle = fnb.FNB_NODRAG | fnb.FNB_NO_NAV_BUTTONS | fnb.FNB_NO_X_BUTTON
        self.book = fnb.FlatNotebook(self, wx.ID_ANY, agwStyle=bookStyle)
        sizer.Add(self.book, 80, wx.EXPAND|wx.ALL)
        
        self.pnl_volume_rendering = Viewer3D(self)
        self.pnl_language = Language(self)

        self.book.AddPage(self.pnl_volume_rendering, "Visualization")
        self.book.AddPage(self.pnl_language, "Language")

        line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        btnsizer = wx.StdDialogButtonSizer()
        
        btn = wx.Button(self, wx.ID_OK, "Apply")
        btnsizer.AddButton(btn)
    
        btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btnsizer.AddButton(btn)

        btnsizer.Realize()
        
        sizer.AddSizer(btnsizer, 10, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)
    


class Viewer3D(wx.Panel):

    def __init__(self, parent):

        wx.Panel.__init__(self, parent, size = wx.Size(800,600))

        
        box_visualization = wx.StaticBox(self, -1, "Surface")
        bsizer = wx.StaticBoxSizer(box_visualization, wx.VERTICAL)

        lbl_inter = wx.StaticText(self, -1, "Interpolation ")
        bsizer.Add(lbl_inter, 0, wx.TOP|wx.LEFT, 10)

        rb_inter = wx.RadioBox(self, -1, "", wx.DefaultPosition, wx.DefaultSize,
                    ['Flat','Gouraud','Phong'], 3, wx.RA_SPECIFY_COLS | wx.NO_BORDER)

        bsizer.Add(rb_inter, 0, wx.TOP|wx.LEFT, 0)

        box_rendering = wx.StaticBox(self, -1, "Volume Rendering")
        bsizer_ren = wx.StaticBoxSizer(box_rendering, wx.VERTICAL)

        lbl_rendering = wx.StaticText(self, -1, "Rendering")
        bsizer_ren.Add(lbl_rendering, 0, wx.TOP | wx.LEFT, 10)
        
        rb_rendering = wx.RadioBox(self, -1, "", wx.DefaultPosition, wx.DefaultSize,
                    ['CPU', 'GPU (Only NVidia video card)'], 3, wx.RA_SPECIFY_COLS | wx.NO_BORDER)

        bsizer_ren.Add(rb_rendering, 0, wx.TOP | wx.LEFT, 0)

        border = wx.BoxSizer(wx.VERTICAL)
        border.Add(bsizer, 50, wx.EXPAND|wx.ALL, 10)
        border.Add(bsizer_ren, 50, wx.EXPAND|wx.ALL, 10)
        self.SetSizer(border)

        border.Fit(self)

class Language(wx.Panel):

    def __init__(self, parent):

        wx.Panel.__init__(self, parent, size = wx.Size(800,600))

        
        box = wx.StaticBox(self, -1, "Language")
        bsizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        t = wx.StaticText(self, -1, "Control Test....")
        bsizer.Add(t, 0, wx.TOP|wx.LEFT, 10)


        border = wx.BoxSizer()
        border.Add(bsizer, 1, wx.EXPAND|wx.ALL, 20)
        self.SetSizer(border)

        border.Fit(self)
