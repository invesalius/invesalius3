import time
from typing import Any
import wx
import wx.grid as gridlib
import wx.lib.agw.pybusyinfo as PBI
import json
from pacs_connection.constants import INV_PORT, INV_AET, INV_HOST, CONFIG_FILE
from pacs_connection.helpers import is_valid_ip_address, is_valid_port, json_serial
from pacs_connection.dicom_client.cecho import CEcho
from components import CustomDialog, BasicCompo


PACS_CONFIG_DATA = json_serial(CONFIG_FILE)
CONFIGURED_PACS = PACS_CONFIG_DATA['configured_pacs']



class Configuration(wx.Frame):
    def __init__(self, size: tuple = (600, 450)) -> None:
        wx.Frame.__init__(self, None, -1, "PACS Configuration",
                          size=size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        self.panel = wx.Panel(self, wx.ID_ANY, size=size)
        self.main_layout = wx.BoxSizer(wx.VERTICAL)
        self.pacs_data = PACS_CONFIG_DATA
        self.configured_pacs = self.pacs_data['configured_pacs']
        self.menu_options = self.pacs_data['menu_options']
        self.default_settings = self.pacs_data['default_settings']
        self.pacs_table = None
        self.panel.SetSizer(self.main_layout)
        self.create_ui()

    def create_line(self, horizontal: int = 1) -> None:
        if horizontal:
            self.sl = wx.StaticLine(self.panel, 1, style=wx.LI_HORIZONTAL)
        else:
            self.sl = wx.StaticLine(self.panel, 2, style=wx.LI_VERTICAL)
        self.main_layout.Add(self.sl, 0, wx.EXPAND | wx.ALL, 1)

    def create_ui(self) -> None:
        self.create_client_info_sizer = self.create_client_info()
        self.main_layout.Add(self.create_client_info_sizer,
                             0, wx.EXPAND | wx.ALL, 1)
        self.create_line(horizontal=1)
        self.create_pacs_info_sizeer = self.create_pacs_info()
        self.main_layout.Add(self.create_pacs_info_sizeer,
                             0, wx.EXPAND | wx.ALL, 1)
        self.create_add_pacs_server_sizer = self.create_add_pacs_server()
        self.main_layout.Add(
            self.create_add_pacs_server_sizer, 0, wx.EXPAND | wx.ALL, 1)
        self.create_footer_sizer = self.create_footer()
        self.main_layout.Add(self.create_footer_sizer, 0,
                             wx.RIGHT | wx.EXPAND | wx.ALL, 1)
        

        return


    def create_menu(self, key: str) -> wx.Menu:
        options = self.menu_options[key]
        menu = wx.Menu()
        des_pos = 0
        for option in options:
            if self.menu_options.get(option, None):
                des_pos = 0
                sub_menu = self.create_menu(option)
                menu.AppendSubMenu(sub_menu, option)
                if option in self.default_settings:
                    default_option = self.default_settings[option]
                    default_menu_item_id = sub_menu.FindItem(default_option)
                    default_menu_item = sub_menu.FindItemById(
                        default_menu_item_id)
            else:
                menu_item = menu.InsertRadioItem(des_pos,wx.ID_ANY, option)
                self.Bind(wx.EVT_MENU, self.on_menu_select, menu_item)
                if option == self.default_settings['Query Timeout']:
                    menu_item.Check(True)


                des_pos += 1
        return menu

    def on_menu_select(self, event: wx.MenuEvent) -> None:
        selected_item_id = event.GetId()
        menu = event.GetEventObject()
        selected_item = menu.FindItemById(selected_item_id)
        selected_item_label = selected_item.GetItemLabel()
        selected_item.Check(True)
        self.default_settings['Query Timeout'] = selected_item_label
        self.pacs_data['default_settings'] = self.default_settings
        event.Skip()


    def on_advance_setting_click(self, event: wx.CommandEvent) -> None:
        pos = self.advanced_settings_button.GetPosition()
        size = self.advanced_settings_button.GetSize()
        self.panel.PopupMenu(self.create_menu(
            'advanced_settings'), pos + (0, size[1]))

    def create_client_info(self) -> None:
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # port
        self.port_label, self.port_label_text = BasicCompo.create_label_textbox(panel =self.panel,
            label='Listener Port: ', text_box_value=str(INV_PORT), enable=False, textbox_needed=1, horizontal=1)
        main_sizer.Add(self.port_label, 1, wx.EXPAND | wx.ALL, 3)

        # AE Title
        self.ae_title_label, self.ae_title_label_text = BasicCompo.create_label_textbox(panel= self.panel,
            label='AE Title: ', text_box_value=INV_AET, enable=False, textbox_needed=1, horizontal=1)
        main_sizer.Add(self.ae_title_label, 1, wx.EXPAND | wx.ALL, 3)

        # Advanced Settings Button
        self.advanced_settings_button = BasicCompo.create_button(panel= self.panel,
            label='Advanced Settings', enable=True)
        self.advanced_settings_button.Bind(
            wx.EVT_BUTTON, self.on_advance_setting_click)
        main_sizer.Add(self.advanced_settings_button, 0, wx.EXPAND | wx.ALL, 5)
        return main_sizer

    def create_header_label(self) -> wx.BoxSizer:
        main_header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        label_sizer = wx.BoxSizer(wx.VERTICAL)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.pacs_label = wx.StaticText(self.panel, label='PACS Servers')
        label_sizer.Add(self.pacs_label, 0, wx.LEFT |
                        wx.TOP | wx.BOTTOM, border=5)
        main_header_sizer.Add(label_sizer, 0, wx.EXPAND | wx.ALL, 3)

        self.spacer = wx.StaticText(self.panel, label='', size=(150, 10))
        header_sizer.Add(self.spacer, 0, wx.ALIGN_CENTER_VERTICAL |
                         wx.LEFT | wx.TOP | wx.BOTTOM, border=5)

        self.verify_pacs_button = BasicCompo.create_button(panel= self.panel,
            label='Verify', enable=False)
        header_sizer.Add(self.verify_pacs_button, 0, wx.ALIGN_CENTER_VERTICAL |
                         wx.LEFT | wx.TOP | wx.BOTTOM, border=5)
        
        self.verify_pacs_button.Bind(wx.EVT_BUTTON, self.verify_pacs)

        self.delete_pacs_button = BasicCompo.create_button(panel= self.panel,
            label='Delete', enable=False)
        header_sizer.Add(self.delete_pacs_button, 0, wx.ALIGN_CENTER_VERTICAL |
                         wx.RIGHT | wx.TOP | wx.BOTTOM, border=5)

        self.delete_pacs_button.Bind(wx.EVT_BUTTON, self.delete_row)

        self.up_button = BasicCompo.create_button(panel= self.panel,label='Up', enable=False)
        header_sizer.Add(self.up_button, 0, wx.ALIGN_CENTER_VERTICAL |
                         wx.RIGHT | wx.TOP | wx.BOTTOM, border=5)
        self.up_button.Bind(wx.EVT_BUTTON, self.on_up)

        self.down_button = BasicCompo.create_button(panel= self.panel,label='Down', enable=False)
        header_sizer.Add(self.down_button, 0, wx.ALIGN_CENTER_VERTICAL |
                         wx.RIGHT | wx.TOP | wx.BOTTOM, border=5)
        self.down_button.Bind(wx.EVT_BUTTON, self.on_down)

        main_header_sizer.Add(header_sizer, 1, wx.LEFT, 5)

        return main_header_sizer

    def create_table(self, array: list, cols_list: list) -> gridlib.Grid:
        tmp_table = gridlib.Grid(self.panel, wx.ID_ANY)
        tmp_table.SetMinSize((500, 150))


        tmp_table.CreateGrid(len(array), len(cols_list))

        for i, col in enumerate(cols_list):
            tmp_table.SetColLabelValue(i, col)
            tmp_table.SetDefaultColSize(150)

        for i, row in enumerate(array):
            for j, col_tag in enumerate(cols_list):
                val = row.get(col_tag, '')
                tmp_table.SetCellAlignment(i, j, wx.ALIGN_CENTER, wx.ALIGN_CENTER)
                tmp_table.SetCellValue(i, j, val)
                tmp_table.SetCellOverflow(i, j, True)
        tmp_table.HideRowLabels()
        tmp_table.SetScrollbars(10, 10, 100, 100)


        return tmp_table
    

    def on_select(self, event: Any) -> None:
        # Enable the button if a row is selected
        initiator = self.pacs_table
        reactor_list = [self.verify_pacs_button, self.delete_pacs_button, self.up_button, self.down_button, self.ip_edit_button]
        row_id = event.GetRow()

        initiator.SelectRow(row_id)
        if row_id >= 0:
            for reactor in reactor_list:
                reactor.Enable()
        # fill the self.ip_add, self.port, self.ae_title of form with this data
        self.change_box_value(row_id)
        # enable all the buttons
        self.ip_add_button.Enable()
        self.ip_edit_button.Enable()

    def on_up(self, event: Any) -> None:
        initiator = self.pacs_table
        row_id = initiator.GetSelectedRows()[0]
        reactor = event.GetEventObject()
        if row_id > 0:
            initiator.MoveCursorDown(True)
            initiator.SelectRow(row_id-1)
            self.change_box_value(row_id-1)
            reactor.Enable()

        else:
            reactor.Disable()

    def change_box_value(self,row_id) -> None:
        initiator = self.pacs_table
        self.ip_address_textbox.SetValue(initiator.GetCellValue(row_id, 0))
        self.port_textbox.SetValue(initiator.GetCellValue(row_id, 1))
        self.ae_title_textbox.SetValue(initiator.GetCellValue(row_id, 2))
        self.description_textbox.SetValue(initiator.GetCellValue(row_id, 3))
        return
        
    def on_down(self, event: Any) -> None:
        reactor = event.GetEventObject()
        initiator = self.pacs_table
        row_id = initiator.GetSelectedRows()[0]
        if row_id < initiator.GetNumberRows()-1:
            initiator.MoveCursorUp(True)
            initiator.SelectRow(row_id+1)
            reactor.Enable()
            self.change_box_value(row_id+1)
            grid_cursor_row = initiator.GetGridCursorRow()
            initiator.SetGridCursor(max(0, grid_cursor_row - 1), 0)

    def delete_row(self, event: Any) -> None:
        try:
            initiator = self.pacs_table
            row_id = initiator.GetSelectedRows()[0]
            dialog = CustomDialog(
                self, 'Are you sure you want to delete this IP configuration?')
            if dialog.ShowModal() == wx.ID_YES:
                wx.MessageBox('PACS Configuration Deleted Successfully', "Success", wx.OK | wx.ICON_INFORMATION)
                initiator.DeleteRows(row_id)
                self.configured_pacs.pop(row_id)
                with open(CONFIG_FILE, 'w') as file:
                    json.dump(self.pacs_data, file)

            self.ip_address_textbox.SetValue('')
            self.port_textbox.SetValue('')
            self.ae_title_textbox.SetValue('')
            self.description_textbox.SetValue('')

        except Exception as e:
            wx.MessageBox('Please Select a row to delete', "", wx.OK | wx.ICON_INFORMATION)
            print(f"ERROR WHILE DELETING THE ROW: {e}")

    def verify_pacs(self, event: Any) -> None:

        initiator = self.pacs_table
        row_id = initiator.GetSelectedRows()[0]
        c_echo = CEcho(initiator.GetCellValue(row_id, 0),
                       int(initiator.GetCellValue(row_id, 1)))
        status = c_echo.verify()
        if status:
            wx.MessageBox('PACS Server Verified Successfully', "Success", wx.OK | wx.ICON_INFORMATION)
            
            num_cols = initiator.GetNumberCols()
            for col in range(num_cols):
                initiator.SetCellBackgroundColour(row_id, col, wx.GREEN)
        else:
            wx.MessageBox('PACS Server is not responding', "Failed", wx.OK | wx.ICON_INFORMATION)
            num_cols = initiator.GetNumberCols()
            for col in range(num_cols):
                initiator.SetCellBackgroundColour(row_id, col, wx.RED)
        self.deselect_rows_pacs(initiator)
        return status

    def deselect_rows(self, initiator: Any, reactor_list: list) -> None:
        #TODO: Add Logic
        return
    
    def deselect_rows_pacs(self, initiator: Any) -> None:
        #TODO: Add Logic
        return

    def create_pacs_info(self) -> wx.BoxSizer:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        #Labels and Buttons
        main_header_sizer = self.create_header_label()
        main_sizer.Add(main_header_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # grid
        configured_pacs_columns = ['IP ADDRESS', 'PORT', 'AE TITLE',
                                   'Description', 'Retrievel Protocol', 'Preferred Transfer Syntax']
        self.pacs_table = self.create_table(
            self.configured_pacs, configured_pacs_columns)
        self.pacs_table.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.on_select)
        main_sizer.Add(self.pacs_table, 1, wx.EXPAND | wx.ALL, 5)

        return main_sizer

    def create_add_pacs_server(self) -> wx.StaticBoxSizer:
        box = wx.StaticBox(self.panel, label='Add PACS Server')
        main_sizer = wx.StaticBoxSizer(box, wx.HORIZONTAL)

        ip_address, self.ip_address_textbox = BasicCompo.create_label_textbox(panel = self.panel,
            label='IP Address', enable=True, label_size=(10, -1), textbox_size=(30, -1))
        self.ip_address_textbox.Bind(wx.EVT_TEXT, self.on_text_enter)
        main_sizer.Add(ip_address, 1, wx.EXPAND | wx.ALL, 5)

        port, self.port_textbox = BasicCompo.create_label_textbox(panel = self.panel,
            label='Port', enable=True)
        self.port_textbox.Bind(wx.EVT_TEXT, self.on_text_enter)
        main_sizer.Add(port, 1, wx.EXPAND | wx.ALL, 5)

        ae_title, self.ae_title_textbox = BasicCompo.create_label_textbox(panel=self.panel,
            label='AE Title', enable=True)
        self.ae_title_textbox.Bind(wx.EVT_TEXT, self.on_text_enter)
        main_sizer.Add(ae_title, 1, wx.EXPAND | wx.ALL, 5)

        description, self.description_textbox = BasicCompo.create_label_textbox(panel = self.panel,
            label='Description', enable=True)
        # bind description with the on_text_enter fucntion
        self.description_textbox.Bind(wx.EVT_TEXT, self.on_text_enter) # wx.EVT_TEXT_ENTER
        main_sizer.Add(description, 1, wx.EXPAND | wx.ALL, 5)

        # add button
        button_sizer = wx.BoxSizer(wx.VERTICAL)
        self.ip_add_button = BasicCompo.create_button(panel= self.panel,label='Add', enable=False)
        self.ip_add_button.Bind(wx.EVT_BUTTON, self.add_pacs_server)

        self.ip_edit_button = BasicCompo.create_button(panel= self.panel,label='Update', enable=False)
        self.ip_edit_button.Bind(wx.EVT_BUTTON, self.add_pacs_server)

        button_sizer.Add(self.ip_add_button, 1, wx.EXPAND | wx.ALL, 5)
        button_sizer.Add(self.ip_edit_button, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 5)

        return main_sizer

    def validators(self, ip_address_value: str, port_value: int, ae_title_value: str, edit: bool = False, **kwargs) -> bool:
        if not is_valid_port(port_value):
            raise ValueError('Invalid Port')

        if not is_valid_ip_address(ip_address_value):
            raise ValueError('Invalid IP Address')

        # now same pair of ip_address and port_number should not be added
        same_ip_address_port_pair = any(ip_address_value == obj.get(
            'IP ADDRESS') and port_value == obj.get('PORT') for obj in self.configured_pacs)
        same_aet_title = any(ae_title_value == obj.get('AE TITLE')
                             for obj in self.configured_pacs)
        
        # for edit, we will check whether and pair is unique or not excluding the current row
        same_ip_address_port_pair_edit = any(ip_address_value == obj.get(
            'IP ADDRESS') and port_value == obj.get('PORT') and kwargs.get('row', 0) != index for index, obj in enumerate(self.configured_pacs))
        same_aet_title_edit = any(ae_title_value == obj.get('AE TITLE') and kwargs.get('row', 0) != index
                                for index, obj in enumerate(self.configured_pacs))
        
        if edit:
            if same_ip_address_port_pair_edit or same_aet_title_edit:
                raise ValueError('Same AE Title or IP Address and Port number already exists')
            else:
                return True
        else:
            if same_ip_address_port_pair or same_aet_title:
                raise ValueError('Same AE Title or IP Address and Port number already exists')
            else:
                return True
        

    def add_pacs_server(self, evt: Any) -> None:
        #TODO: Refactor this function, it's becoming hard to maintain
        ip_address_value = self.ip_address_textbox.GetValue()
        port_value = self.port_textbox.GetValue()
        ae_title_value = self.ae_title_textbox.GetValue()
        description_value = self.description_textbox.GetValue()
        evt_obj = evt.GetEventObject()
        button_label = evt_obj.GetLabel()
        edit = button_label == 'Update'
        try:
            self.row = 0
            if self.pacs_table.GetSelectedRows():
                self.row = self.pacs_table.GetSelectedRows()[0]
            self.validators(ip_address_value, port_value,
                            ae_title_value, edit=edit, row=self.row)
        except ValueError as ve:
            errordlg = wx.MessageDialog(
                self, f"Invalid: {ve}", f"Error: {ve}", wx.OK | wx.ICON_ERROR)
            errordlg.ShowModal()
            time.sleep(3)
            errordlg.Destroy()
            return
        dlg = CustomDialog(self, f"Do you want to {button_label} this item?")
        result = dlg.ShowModal()
        valid = True  # need to create_function to verify if the data are valid
        if valid and result == wx.ID_YES:
            try:
                ip_address_value = self.ip_address_textbox.GetValue()
                port_value = self.port_textbox.GetValue()
                ae_title_value = self.ae_title_textbox.GetValue()
                description_value = self.description_textbox.GetValue()

                configured_pacs_columns = ['IP ADDRESS', 'PORT', 'AE TITLE',
                                           'Description', 'Retrievel Protocol', 'Preferred Transfer Syntax']
                new_data = {'IP ADDRESS': ip_address_value, 'PORT': port_value, 'AE TITLE': ae_title_value,
                            'Description': description_value, 'Retrievel Protocol': 'DICOM', 'Preferred Transfer Syntax': 'Implicit VR Little Endian'}
                if edit:
                    row_number = self.pacs_table.GetSelectedRows()[0]
                    self.configured_pacs[row_number] = new_data
                    for col_nu in range(self.pacs_table.GetNumberCols()):
                        col_tag = configured_pacs_columns[col_nu]
                        self.pacs_table.SetCellValue(
                            row_number, col_nu, new_data.get(col_tag, ''))
                else:
                    self.configured_pacs.append(new_data)
                    self.pacs_table.AppendRows(1)
                    for col_nu in range(self.pacs_table.GetNumberCols()):
                        col_tag = configured_pacs_columns[col_nu]
                        self.pacs_table.SetCellValue(
                            self.pacs_table.GetNumberRows()-1, col_nu, new_data.get(col_tag, ''))
                        self.pacs_table.SetCellAlignment(self.pacs_table.GetNumberRows()-1, col_nu, wx.ALIGN_CENTER, wx.ALIGN_CENTER)

            except Exception as e:
                print(f"ERROR While Adding PACS Server details: {e}")
        if not valid and result == wx.ID_YES:
            self.show_error_message('Invalid Data', 'Please check your data')

        dlg.Destroy()

        self.ip_address_textbox.SetValue('')
        self.port_textbox.SetValue('')
        self.ae_title_textbox.SetValue('')
        self.description_textbox.SetValue('')
        return

    def create_footer(self) -> wx.BoxSizer:
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # save button
        save_button = BasicCompo.create_button(panel= self.panel,label='Save', enable=True)
        save_button.Bind(wx.EVT_BUTTON, self.on_save)
        

        # cancel button
        cancel_button = BasicCompo.create_button(panel= self.panel,label='Cancel', enable=True)
        cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer() 
        button_sizer.Add(cancel_button, 0, wx.RIGHT, 5) 
        button_sizer.Add(save_button, 0, wx.RIGHT)
        main_sizer.Add(button_sizer, 0,  wx.RIGHT | wx.EXPAND | wx.ALL, 3)

        return main_sizer

    def on_save(self, event: Any) -> None:
        dlg = CustomDialog(self, "Do you want to save this item?")
        result = dlg.ShowModal()
        if result == wx.ID_YES:
            with open(CONFIG_FILE, 'w') as file:
                print('Writing to json file')
                json.dump(self.pacs_data, file)
            self.Close()

        dlg.Destroy()

    def on_cancel(self, event: Any) -> None:
        dlg = CustomDialog(self, "Do you want to cancel this item?")
        result = dlg.ShowModal()
        if result == wx.ID_YES:
            self.Close()
        dlg.Destroy()

    def show_error_message(self, message: str = 'Some Error Occured') -> None:
        app = wx.App()
        msg_dlg = wx.MessageDialog(
            self, message, "Error", wx.OK | wx.ICON_ERROR)
        msg_dlg.ShowModal()

    def on_text_enter(self, event: Any)->None:
        if self.ip_address_textbox.GetValue()  and self.port_textbox.GetValue()  and self.ae_title_textbox.GetValue():
            self.ip_add_button.Enable(True)
        else:
            self.ip_add_button.Disable()

if __name__ == "__main__":
    
    app = wx.App()
    frame = Configuration()
    frame.Show()
    app.MainLoop()
