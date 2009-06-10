import cStringIO
import wx
import widgets.foldpanelbar as fpb
import wx.lib.filebrowsebutton as filebrowse
import wx.lib.hyperlink as hl
import wx.wizard as wiz

def getWizTest1Data():
    return \
'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00t\x00\x00\x01\x04\x08\x02\
\x00\x00\x00v\xad\x87\x05\x00\x00\x00\x03sBIT\x08\x08\x08\xdb\xe1O\xe0\x00\
\x00\x06\x06IDATx\x9c\xed\x9b\xc1\xcd\xdbF\x10FGA\xe0\xc0\x07]\x048M\xa8\x01\
\x9f\x9c\x02\xd4\x81\xd3\x84\x1a\x10\xec@\r\xa8\x89\xa4\x03\x15\x90\x9c\xd2\
\x80\x9aH\x00]t\x08\xec\x0bs`D\x04\xc9\x92\xe0\xee\xf2\xed\xceR\xdf;\x1a$\
\xbd\xf8\xf083\xbb?\xb5\xe9\xba\xce\x04\xc37\xb5\x17\xb0f\x14.\x88\xc2\x05Q\
\xb8 \n\x17D\xe1\x82(\\\x10\x85\x0b\xa2pA\x14.\x88\xc2\x05Q\xb8 \xdf\xe6?b\
\xb3\xd9\xa4\xdd\xb8\xfa3#\x99\x0b\xb2\x80\xb9O>c\x17\xb7\x8a\xcc\x05Y2\xdc\
\xae\xfb\xd4u\x9f\x16|`\xeb\xc8\\\x10\x85\x0b\xb2`C\x9b\xe6\xf3\xff\xffi\xce\
\x0c\xd7\xf4\xb8&sA\x8a\x99kf\x16ea\xea\xd6\xc4\x11\xb3\xc2M\xde\x83\xbd8*\
\x0b \x11ea\xec\x9d\x8e\xb4zx\xcc\xfa\xdf\x06\x99\x0b\x12\xd9\xd0\xfa\x964R\
\x827\x9b\x9f\xb2\xd7\xb3*d.\xc8f\xce\x94\xdeO\x0b\x9d\x85\xcd\x9d_;\xbb\xce\
\xe6\xd7\xdc\xfe?\xd1&B\x84Y`\x13\x11T\xab\xd7r\xf0\xee5\'e\x99\x0b\xa2pA\
\x8a\x9e-\x98\xd9+\xec\x1d\x06d.\x88\xc2\x05\x89,\x0byM\xff\xd5F\x06\x99\x0b\
\x12an\x8evMo\xb4\x92\x91\xb9 \xb3\xce\x16D\x1a2\x17D\xe1\x82(\\\x10\x85\x0b\
R\xfel\xe1\xbf\x1c\x0e\x87\xb4\x1b\xaf\xd7\xeb\xb2+Y\x1c\x99\x0bR\xdf\xdc\'?\
\xc6\\\xfc3\xb5\x8aE\x91\xb9 \x8e\xc2\xbd^?^\xaf\x1fk\xafbI\x1c\x85\xbb>\x14\
.\x88\x9f\x866M\xa0\x83\xcd\x99\xe1\xea\x8ek2\x17\xa4\x15s\xcd\xcc\xa2,L\xdd\
\x9a,I\x89p\x93\xf7`\xad\xa3\xb2\x00R\xae,\x8c\xbd\xd3\x91V\x0f\x8fi\xe0m\
\x90\xb9 e\x1bZ\xdf\x92FJ\xf0\xe1\xf0K\xd1\xc5\xf0\xc8\\\x10?\xa3X\x1b\x07]Q\
\xc8\\\x90\xfa\xe6\x06\xa7\x88\xbe*\x0f\x9b\xd7F\'e\x99\x0b\xa2pA\xea\x97\
\x85HZ\xaa\x0f2\x17D\xe1\x82\x94-\x0byM\xbf\xb9\x91A\xe6\x82\x9437G;\xff\x1f\
\xd7\x04\x91\xb9 \xfa\xf8\x19D\xe6\x82(\\\x10\x85\x0b\xa2pA\x14.\x88\xc2\x05\
Q\xb8 \n\x17\xa4\xb9\xf3\\3\xb3\xf3\xf9\x9cv\xe3\xe9tZv%\xd3\xc8\\\x90&\xcd}\
\xf2C\xcc\xc5\xbfR\xab\x18G\xe6\x82\xb4\x1d\xee\xe9\xf4\xe1t\xfaP{\x15\xa3\
\xb4\x1d\xaes\x14.H\xd3\rm\x9a@\x07\x9b3\xc3-8\xae\xc9\\\x90\x15\x9bkf\x16ea\
\xea\xd6d\x14\xa7\xe1&\xef\xc1\\\xa1\xb2\x00\xe2\xd4\xdc\x9e\xb1w:\xd2\xea\
\xe11\xa5\xdf\x06\x99\x0b\xe2\xda\\\xb3gK\x1a)\xc1\xe7\xf3oE\x17\x13\x89\xcc\
\x05qo\xee\x14\x15\x0e\xba\xa2\x90\xb9 M\x9a\x1b\x9c"\xfa\xaa<l^=L\xca2\x17D\
\xe1\x824Y\x16"\xa9V\x1fd.\x88\xc2\x05q_\x16\xf2\x9a~\xdd\x91A\xe6\x82\xb867\
G\xbb\xc2\x1f\xd7\x04\x91\xb9 \xfa\xc1\t\x88\xcc\x05Q\xb8 \n\x17D\xe1\x82(\\\
\x10\x85\x0b\xa2pA\\\xef\xd0\xe6s\xb9\\\xd2n<\x1e\x8f\xcb\xae\xe4\xdf\xc8\\\
\x90\x95\x98\xfb\xe4}\xcc\xc5\xbfS\xabx"sA\xd6\x16\xee\xf1\xf8\xfex\x8c\xf2\
\x17dm\xe1\xbaB\xe1\x82\xac\xac\xa1M\x13\xe8`sf\xb8\xe4qM\xe6\x82\xbc\x94\
\xb9ffQ\x16\xa6nM\xfe\xa1\x99p\x93\xf7`\x15QY\x00i\xc6\xdc\x9e\xb1w:\xd2\xea\
\xe11\xec\xdb sA\x1a3\xd7\xec\xd9\x92FJ\xf0\xe5\x82\x9f\x18\xccG\xe6\x824h\
\xee\x14\x8e\xb45\x99\x8b\xb2\x12s\x83SD_\x95\x87\xcdk\xf9IY\xe6\x82(\\\x90\
\x95\x94\x85H\n\xd5\x07\x99\x0b\xa2pA\x1a,\x0byM\xbf\xe4\xc8 sA\x1a37G;\xf4\
\xe3\x9a 2\x17D\xbf\x89\x00\x91\xb9 \n\x17D\xe1\x82(\\\x10\x85\x0b\xa2pA\x14\
.\x88\xc2\x05Q\xb8 \n\x17\xc4\xe3\xc1\xcd\xedvK\xbbq\xbf\xdf/\xbb\x92Ld.\x88\
Gs\x9f|\x1fs\xf1\x1f\xd4*2\x90\xb9 \xae\xc3\xdd\xef\xdf\xed\xf7\xefj\xaf"\
\x1d\xd7\xe1\xb6\x8e\xc2\x05\xf1\xdc\xd0\xa6\tt\xb093\\\xc9qM\xe6\x82\xb4k\
\xae\x99Y\x94\x85\xa9[\x93t\xea\x84\x9b\xbc\x07k\x0b\x95\x05\x90\x9aea\xec\
\x9d\x8e\xb4zx\x8c\xbb\xb7A\xe6\x82\xd4nh}K\x1a)\xc1\xb7\xdb\x9fE\x17\xb342\
\x17\xa4\xb6\xb9Sx<\xe8\x8aB\xe6\x82x478E\xf4Uy\xd8\xbc61)\xcb\\\x10\x85\x0b\
\xe2\xb1,D\xe2\xb7>\xc8\\\x10\x85\x0bR\xbb,\xe45}\xe7#\x83\xcc\x05\xa9in\x8e\
v\xde>\xae\t"sA\xf4S)\x10\x99\x0b\xa2pA\x14.\x88\xc2\x05Q\xb8 \n\x17D\xe1\
\x82\xd4\xd9\xa1\xdd\xef\xf7\xb4\x1bw\xbb\xdd\xb2+A\x91\xb9 uO\xc5\xde\xc6\\\
\xfc\x17\xb5\n\x0c\x99\x0bR9\xdc\xdd\xee\xedn\x17\xe5oK\xc8\\\x10\x85\x0bR\
\xfb\xcf<S\x04:\xd8\x9c\x19\xce\xcf\xb8&sA<\x9bkf\x16ea\xea\xd6\x84\x82\n7y\
\x0f\xb6&T\x16@\xd8\xb20\xf6NGZ=<\xa6\xb1\xb7A\xe6\x82\xf0\r\xadoI#%\xf8~o\
\xef\xc4`>2\x17\xa4\xee(\xb6fmM\xe6\xa2\xd4178E\xf4Uy\xd8\xbc\xae`R\x96\xb9 \
\n\x17\xc4\xfb\xd9\x82\x995\xb7w\x18\x90\xb9 \n\x17\x84/\x0byM\xbf\xe9\x91A\
\xe6\x82\xb0\xe6\xe6h\xe7\xe7\xaf5\xc9\xc8\\\x10\xfd&\x02D\xe6\x82(\\\x10\
\x85\x0b\xa2pA\x9c\x9e-<\x1e\x8f\xb4\x1b\xb7\xdb\xed\xb2+\xc9A\xe6\x8285\xf7\
\xc9w1\x17\x7f\xa1V\x91\x8a\xcc\x05\xf1\x1e\xeev\xfbf\xbb}S{\x15\x89x\x0f\
\xb7i\x14.\x88\xf3\x866M\xa0\x83\xcd\x99\xe1\x8a\x8dk2\x17\xa4is\xcd\xcc\xa2\
,L\xdd\x9a$R-\xdc\xe4=XC\xa8,\x80T.\x0bc\xeft\xa4\xd5\xc3c|\xbd\r2\x17\xc4AC\
\xeb[\xd2H\t~<\xbe\x16]\xcc\xa2\xc8\\\x10\x07\xe6N\xe1\xee\xa0+\n\x99\x0b\
\xe2\xd4\xdc\xe0\x14\xd1W\xe5a\xf3\xea\x7fR\x96\xb9 \n\x17\xc4iY\x88\xc4i}\
\x90\xb9 \n\x17\xc4AY\xc8k\xfa\x9eG\x06\x99\x0bR\xd9\xdc\x1c\xed\\}\\\x13D\
\xe6\x82\xe8\xe3g\x10\x99\x0b\xa2pA\x14.\x88\xc2\x05\xf9\x1b\xa1\x11\xf1\xe2\
?\xae\xd64\x00\x00\x00\x00IEND\xaeB`\x82' 

def getWizTest1Bitmap():
    return wx.BitmapFromImage(getWizTest1Image())

def getWizTest1Image():
    stream = cStringIO.StringIO(getWizTest1Data())
    return wx.ImageFromStream(stream)


def makePageTitle(wizPg, title):
    sizer = wx.BoxSizer(wx.VERTICAL)
    wizPg.SetSizer(sizer)
    title = wx.StaticText(wizPg, -1, title)
    title.SetFont(wx.Font(18, wx.SWISS, wx.NORMAL, wx.BOLD))
    sizer.Add(title, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
    sizer.Add(wx.StaticLine(wizPg, -1), 0, wx.EXPAND|wx.ALL, 5)
    return sizer

class BasePage(wiz.PyWizardPage):
    def __init__(self, parent, title, number):
        wiz.PyWizardPage.__init__(self, parent)
        # header data
        self.title = title
        self.number = number
        # previous / next page data
        self.next = self.prev = None
        self.jump_next_page = False
        
        self.__init_gui()
        
        self.Update()
        self.SetAutoLayout(1)
        self.Fit()
                
    def __init_gui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)        
        self.SetSizer(sizer)
        
        # Build header
        first_line = wx.BoxSizer(wx.HORIZONTAL)
        number = wx.StaticText(self, -1, str(self.number)+".")
        number.SetFont(wx.Font(20, wx.SWISS, wx.NORMAL, wx.BOLD))
        self.header_number = number
        title = wx.StaticText(self, -1, self.title)
        title.SetFont(wx.Font(16, wx.SWISS, wx.NORMAL, wx.NORMAL))
        first_line.Add(number, 0, wx.ALIGN_LEFT|wx.ALIGN_BOTTOM|wx.RIGHT, 5)
        first_line.Add(title, 0, wx.ALIGN_LEFT|wx.ALIGN_BOTTOM|wx.RIGHT|wx.BOTTOM, 2)
        sizer.AddSizer(first_line, 0)
        sizer.Add(wx.StaticLine(self, -1), 0, wx.EXPAND|wx.ALL, 5)
        
        self.sizer = sizer
        
    def DecreasePageNumber(self):
        print "number before", self.number
        self.number -= 1
        self.header_number.SetLabel(str(self.number)+".")
        
    def SetNext(self, next):
        self.next = next

    def SetPrev(self, prev):
        self.prev = prev
        
    # Classes derived from wxPyWizardPanel must override
    # GetNext and GetPrev, and may also override GetBitmap
    # as well as all those methods overridable by
    # wx.PyWindow.

    def GetNext(self):
        return self.next
        
    def GetPrev(self):
        return self.prev

class RawDataPage(BasePage):
    def __init__(self, parent, title, number):
        BasePage.__init__(self, parent, title, number)

class StudyPage(BasePage):
    def __init__(self, parent, title, number):
        BasePage.__init__(self, parent, title, number)

class DirPage(BasePage):
    """
    Wizard page for selecting which directory or directories should be searched
    for retrieving medical images.
    """
    
    def __init__(self, parent, title, number):
        BasePage.__init__(self, parent, title, number)
        self.__init_specific_gui()
        
        self.selected_dir = []
        
    def __init_specific_gui(self):
        
        line1 = wx.StaticText(self, -1,"Select the directory which "+\
                              "contains medical images of the study interest.")
        
        
        
        t1 = wx.TextCtrl(self, -1, "", size=(125, -1))
        
        #dbb = filebrowse.DirBrowseButton(
        #    self, -1, size=(450, -1), changeCallback = self.dbbCallback)
        #dbb.SetLabel("")
        #line2 = dbb
        #line2 = wx.BoxSizer(wx.HORIZONTAL)

        #line3 = wx.BoxSizer(wx.VERTICAL)
        #self.line3 = line3

        #link_add_another_dir = hl.HyperLinkCtrl(self, -1,"Add a new directory")
        #link_add_another_dir.SetUnderlines(True, False, False)
        #link_add_another_dir.SetColours("BLUE", "BLUE", "BLUE")
        #link_add_another_dir.AutoBrowse(False)
        #link_add_another_dir.UpdateLink()
        #link_add_another_dir.Bind(hl.EVT_HYPERLINK_LEFT, self.OnAddDir)
        #self.link_add_new = link_add_another_dir
        
        
        # ADVANCED
        # [] Save selected folders as default
        # [] Consider files inside inner folders of the selected folder, using recursion
        
        
        self.sizer.Add(line1, 0, wx.LEFT|wx.RIGHT|wx.TOP, 5)
        self.sizer.Add(line2, 0, wx.ALL, 5)
        self.sizer.Add(line3, 0, wx.ALL, 5)
        self.sizer.Add(link_add_another_dir, 0, wx.LEFT|wx.BOTTOM, 10)
        
        
        fold_panel = fpb.FoldPanelBar(self, -1, wx.DefaultPosition,
                                      (450, 100), 0,fpb.FPB_SINGLE_FOLD)

        # Fold panel style
        style = fpb.CaptionBarStyle()
        style.SetCaptionStyle(fpb.CAPTIONBAR_RECTANGLE)
        style.SetSecondColour(wx.Colour(255,255,255))

        # Fold 1 - Surface properties
        item = fold_panel.AddFoldPanel("Advanced options", 
                                        collapsed=True)
        fold_panel.ApplyCaptionStyle(item, style)
        fold_panel.AddFoldPanelWindow(item,
            wx.CheckBox(item, wx.ID_ANY, "Use selected folder(s) as default"),
                        Spacing= 0, leftSpacing=0, rightSpacing=0)
        fold_panel.AddFoldPanelWindow(item,
            wx.CheckBox(item, wx.ID_ANY, "Enable recursion in folder(s)"),
                        Spacing= 0, leftSpacing=0, rightSpacing=0)

     
        self.sizer.Add(fold_panel, 0, wx.TOP|wx.LEFT, 5)
        
        self.sizer.Fit(self)
        self.Update()
        self.SetAutoLayout(1)
        
        
    def JumpNextPage(self):
        self.jump_next_page = True
        self.next.GetNext().DecreasePageNumber()

    def OnAddDir(self, evt):
        dlg = wx.DirDialog(self, "Choose a directory:",
                           style=wx.DD_DIR_MUST_EXIST)
            
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.selected_dir.append(path)
            self.link_add_new.SetLabel("Add another directory")
            self.AddNewDir(path)
        dlg.Destroy()
        
    def OnChangeDir(self, prev_dir, text):
        dlg = wx.DirDialog(self, "Choose a directory:",
                           style=wx.DD_DIR_MUST_EXIST)
        dlg.SetPath(prev_dir)
        
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.selected_dir.remove(prev_dir)
            self.selected_dir.append(path)
            text.SetValue(path)
        dlg.Destroy()
        
        
    def AddNewDir(self, path):
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_BUTTON,
                        (12,12))
        btn = wx.BitmapButton(self, -1, folder_bmp)
    
        text_dir_path = wx.StaticText(self, -1, path)
        
        tooltip = wx.ToolTip("Remove this directory from list")
        link_remove = hl.HyperLinkCtrl(self, -1,"Remove")
        link_remove.SetUnderlines(True, False, False)
        link_remove.SetColours("BLUE", "BLUE", "BLUE")
        link_remove.SetToolTip(tooltip)
        link_remove.AutoBrowse(False)
        link_remove.UpdateLink()
        
        dir_line = wx.BoxSizer(wx.HORIZONTAL)
        dir_line.Add(btn, 0, wx.LEFT|wx.RIGHT, 5)
        dir_line.Add(text_dir_path, 0)
        dir_line.Add(link_remove, 0, wx.ALIGN_RIGHT|wx.RIGHT|wx.LEFT, 5)
        
        link_remove.Bind(hl.EVT_HYPERLINK_LEFT, lambda e: self.RemoveDir(path, dir_line))
        btn.Bind(wx.EVT_BUTTON, lambda e: self.OnChangeDir(path, link_remove))
        
        self.line3.Add(dir_line, 1, wx.LEFT, 2)
        #self.line3.Add(text_dir_path, 0, wx.ALL, 5)

        self.Fit()
        
    def RemoveDir(self, path, sizer):
        self.selected_dir.remove(path)
        self.line3.Hide(sizer)
        self.line3.RemoveSizer(sizer)
        if not self.selected_dir:
            self.link_add_new.SetLabel("Add another directory")
        self.Layout()
        self.Fit()
        
        
        
        
    def GetNext(self):
        """If jump_next_page is true then return the next page's next page"""
        if self.jump_next_page:
            try:
                self.next.GetNext().SetPrev(self)
            except AttributeError:
                print "Warning: Next is the last Wizard page."
                return None
            else:
                return self.next.GetNext()
        else:
            try:
                self.next.GetNext().SetPrev(self.next)
            except AttributeError:
                print "Worning: This is the last Wizard page"
            return self.next
            

    def dbbCallback(self, evt):
        self.log.write('DirBrowseButton: %s\n' % evt.GetString())

def CreateWizard(parent):  
    wizard = wiz.Wizard(parent, -1, "Import medical images", getWizTest1Bitmap())

    page1 = DirPage(wizard, "Choose directory", 1)
    page2 = RawDataPage(wizard, "Define RAW data", 2)
    page3 = StudyPage(wizard, "Select study", 3) # 2 can be 3


    wizard.FitToPage(page1)
    page3.sizer.Add(wx.StaticText(page3, -1, "\nThis is the last page."))

    # Set the initial order of the pages
    page1.SetNext(page2)
    page2.SetPrev(page1)
    page2.SetNext(page3)
    page3.SetPrev(page2)

    page1.JumpNextPage()

    wizard.GetPageAreaSizer().Add(page1)
    
    if wizard.RunWizard(page1):
        print "Completed - Send message to import data"
    else:
        print "Canceled"

class ImportApp(wx.App):
    def OnInit(self):
        CreateWizard(None)
        return True

if __name__ == '__main__':
    app = ImportApp(0)
    app.MainLoop()
