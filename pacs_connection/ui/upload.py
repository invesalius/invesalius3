import wx
from pacs_connection.dicom_client.cstore import CStore
from components import BasicCompo


class UploadFiles(wx.Frame):
    
    def __init__(self):
        super().__init__(parent=None, size= (-1,700), title='Upload Files')
        self.panel = wx.Panel(self)
        self.main_layout = wx.BoxSizer(wx.VERTICAL)
        self.panel.SetSizer(self.main_layout)
        self.create_gui()

    def create_gui(self):
        self.main_layout.Add(self.create_export_option(), 0, wx.EXPAND | wx.ALL, 5)
        self.main_layout.Add(self.create_file_format_option(), 0, wx.EXPAND | wx.ALL, 5)
        self.main_layout.Add(self.create_export_location(), 0, wx.EXPAND | wx.ALL, 5)
        self.main_layout.Add(self.create_file_settings(), 0, wx.EXPAND | wx.ALL, 5)
        self.main_layout.Add(self.create_footer(), 0, wx.EXPAND | wx.ALL, 5)
        pass

    def create_export_option(self):
        self.export_options = wx.RadioBox(self.panel, label='Export', choices=['Selected series', 'Selected Studies'], majorDimension=1, style=wx.RA_SPECIFY_ROWS)
        
        return self.export_options
    
    def create_file_format_option(self):
        self.file_format_options = wx.RadioBox(self.panel,label='File Format', choices=['DICOM', 'NIFTI', 'JPEG', 'MP4', 'BMP'], majorDimension=1, style=wx.RA_SPECIFY_ROWS)
        #bind with on_file_format_selection
        self.file_format_options.Bind(wx.EVT_RADIOBOX, self.on_file_format_selection)
        return self.file_format_options
    
    def create_export_location(self):
        border = wx.StaticBox(self.panel, label='Export Location')
        box = wx.StaticBoxSizer(border, wx.VERTICAL)
        browse_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.folder_form, self.folder_form_textbox= BasicCompo.create_label_textbox(self.panel, 'Folder Name', '', True,horizontal=1 )
        self.folder_browse_button = BasicCompo.create_button(self.panel, 'Browse', True)

        browse_sizer.Add(self.folder_form, 0, wx.EXPAND | wx.ALL, 5)
        browse_sizer.Add(self.folder_browse_button, 0, wx.EXPAND | wx.ALL, 5)

        box.Add(browse_sizer, 0, wx.EXPAND | wx.ALL, 5)

        #Bind actions
        self.folder_browse_button.Bind(wx.EVT_BUTTON, self.on_browse_file)
        return box

    def create_file_settings(self):

        border = wx.StaticBox(self.panel, label='File Settings')
        sizer= wx.StaticBoxSizer(border, wx.VERTICAL)
        self.image_size = wx.RadioBox(self.panel, label='image size', choices=['Original', 'Default(1:1)', 'Custom'], majorDimension=2, style=wx.RA_SPECIFY_ROWS)
        self.annotations = wx.RadioBox(self.panel, label='Annotations', choices=['None', 'Default', 'Custom'], majorDimension=1, style=wx.RA_SPECIFY_ROWS)

        self.frame_rate = wx.RadioBox(self.panel, label='Frame Rate', choices=['Default', 'Custom'], majorDimension=2, style=wx.RA_SPECIFY_ROWS)
        self.frame_rate.Disable()
        self.frame_rate.Bind(wx.EVT_RADIOBOX, self.on_radio_box)
        self.custom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.custom_label = wx.StaticText(self.panel, label="FPS")
        self.custom_sizer.Add(self.custom_label, 0, wx.EXPAND | wx.ALL, 5)

        self.custom_frame_rate = wx.TextCtrl(self.panel, style=wx.TE_PROCESS_ENTER, value='30')
        self.custom_sizer.Add(self.custom_frame_rate, 0, wx.EXPAND | wx.ALL, 5)
        self.custom_frame_rate.Enable(False)
        self.custom_frame_rate.Bind(wx.EVT_TEXT_ENTER, self.on_custom_frame_rate, self.custom_frame_rate)

        self.jpeg_conf = wx.BoxSizer(wx.HORIZONTAL)
        self.jpeg_label = wx.StaticText(self.panel, label='JPEG Quality')
        self.jpeg_quality = BasicCompo.create_slider(self.panel, 'JPEG Quality',100, 0, 100)
        self.jpeg_quality.Disable()
        self.jpeg_conf.Add(self.jpeg_label, 0, wx.EXPAND | wx.ALL, 5)
        self.jpeg_conf.Add(self.jpeg_quality, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.image_size, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.annotations, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.frame_rate, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.custom_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.jpeg_conf, 0, wx.EXPAND | wx.ALL, 5)

        return sizer

    def create_footer(self):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.cancel_button = BasicCompo.create_button(self.panel, 'Cancel', True)
        self.cancel_button.SetPosition((self.GetSize().GetWidth() - self.cancel_button.GetSize().GetWidth(), 50))
        self.export_button = BasicCompo.create_button(self.panel, 'Export', True)
        self.export_button.SetPosition((self.GetSize().GetWidth() - self.export_button.GetSize().GetWidth(), 0))

        #Bind actions
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.export_button.Bind(wx.EVT_BUTTON, self.on_export)


        sizer.Add(self.cancel_button, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.export_button, 0, wx.EXPAND | wx.ALL, 5)

        return sizer

    def on_cancel(self, event:wx.Event)->None:
        self.Close()

    def on_custom_frame_rate(self, event:wx.Event)->None:
        try:
            frame_rate = int(self.custom_frame_rate.GetValue())
            print(f"Custom frame rate: {frame_rate}")
        except ValueError:
            wx.MessageBox("Please enter an integer value.", "Invalid Value", wx.OK|wx.ICON_ERROR)
    
    def on_radio_box(self, event: wx.Event)->None:
        if event.GetInt() == 1:  # Custom option selected
            self.custom_frame_rate.Enable(True)
        else:
            self.custom_frame_rate.Enable(False)
    
    def on_export(self, even: wx.Event)->None:
        # find which export option is selected
        try:
            export_option = self.export_options.GetStringSelection()
            # find which file format is selected
            file_format = self.file_format_options.GetStringSelection()
            cstore =  CStore("DicomServer.co.uk", 104)
            path = self.folder_form_textbox.GetValue()

            # get other information like JPEG Quality, FPS Rate
            jpeg_quality = self.jpeg_quality.GetValue()
            print(self.jpeg_quality.IsEnabled())
            print(f"JPEG Quality: {jpeg_quality}")
            frame_rate = self.custom_frame_rate.GetValue()
            print(self.custom_frame_rate.IsEnabled())
            print(f"Frame Rate: {frame_rate}")
            
            if export_option == 'Selected series':
                print('Selected series')
                print('File format: ', file_format)
                req = cstore.upload(path, False)
                print(req)
            elif export_option =='Selected Studies':
                print('Selected Studies')
                print('File format: ', file_format)
                req = cstore.upload(path, True)
                print(req)
            # Notifications for success/failure
            req_status = "Success" if req else "Failed"
            msg = 'Successfully exported' if req else 'Failed to export'
            wx.MessageBox(msg, req_status, wx.OK | wx.ICON_INFORMATION)
            print(msg)
        except Exception as e:
            print(e)
            wx.MessageBox("Please select a valid export option.", "Invalid Value", wx.OK|wx.ICON_ERROR)

        return

    def on_file_format_selection(self, event:wx.Event)->None:
        event = event.GetEventObject()
        file_format = event.GetStringSelection()
        print(file_format)

        if file_format  in  ['JPEG', 'BITMAP']:
            print('HERE 290')
            self.jpeg_quality.Enable()
            self.frame_rate.Disable()
        
        elif file_format in ['MP4']:
            self.frame_rate.Enable()
            self.jpeg_quality.Disable()
        else:
            self.frame_rate.Disable()
            self.jpeg_quality.Enable()
        
        return

    def on_browse_file(self, event: wx.Event)->None:
        evt_obj = event.GetEventObject()
        # now we wanna see the selected Export Type
        export_type = self.export_options.GetStringSelection()
        file_format = self.file_format_options.GetStringSelection()
        wildcard = self.wild_card_mapper(file_format)
        if export_type == 'Selected series':
            dialog = wx.FileDialog(None, "Choose a file",
                                wildcard=wildcard,
                                style=wx.FD_OPEN | wx.FD_MULTIPLE)
            if dialog.ShowModal() == wx.ID_OK:
                paths = dialog.GetPaths()
                print("Selected files:")
                self.folder_form_textbox.SetValue(paths[0])
                for path in paths:
                    print(path)
            dialog.Destroy()

        else:
            dialog = wx.DirDialog(None, "Choose a directory:",
                                style=wx.DD_DEFAULT_STYLE
                                )
            if dialog.ShowModal() == wx.ID_OK:
                folder_path = dialog.GetPath()
                import os
                files = os.listdir(folder_path)
                # print the names of any files in the folder
                self.folder_form_textbox.SetValue(folder_path)
                for file in files:
                    if os.path.isfile(os.path.join(folder_path, file)):
                        print(file)
            dialog.Destroy()

        # TODO: WE NEED TO SELECT SET OF REQUIRED FILES, so let users select folders
        return

    @staticmethod
    def wild_card_mapper(file_format:str)->str:
        if file_format == 'DICOM':
            return "DICOM files (*.dcm)|*.dcm"
        elif file_format == 'NIFTI':
            return "NIFTI files (*.nii)|*.nii"
        elif file_format == 'JPEG':
            return "JPEG files (*.jpg)|*.jpg"
        elif file_format == 'MP4':
            return "MP4 files (*.mp4)|*.mp4"
        elif file_format == 'BMP':
            return "BMP files (*.bmp)|*.bmp"
        else:
            return "All files (*.*)|*.*"







if __name__ == '__main__':
    app = wx.App()
    frame = UploadFiles()
    frame.Show()
    app.MainLoop()