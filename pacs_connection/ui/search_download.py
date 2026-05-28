from typing import Any
import time
import wx
import wx.adv as wxadv
import wx.grid as gridlib
import concurrent.futures  
from concurrent.futures import ThreadPoolExecutor
import sys
sys.path.append('D:\Opensource\Invesaliusproject\\fork\invesalius3')
from pacs_connection.dicom_client.cfind import CFind
from pacs_connection.ui.pacs_config import Configuration
from pacs_connection.ui.download_history import DownloadHistory
from pacs_connection.helpers import json_serial
from pacs_connection.constants import COLS, CONFIG_FILE
import datetime


def get_pacs_details():
    pacs_config_data  = json_serial(CONFIG_FILE)
    configured_pacs = pacs_config_data['configured_pacs']
    configured_pacs_mapper = {}
    all_pacs = []
    for i, pacs_obj in enumerate(configured_pacs):
        configured_pacs_mapper[pacs_obj['AE TITLE']] = pacs_obj
        all_pacs.append(pacs_obj['AE TITLE'])
    return configured_pacs_mapper, all_pacs, configured_pacs


class Browse(wx.Frame):

    CONFIGURED_PACS_MAPPER, ALL_PACS, CONFIGURED_PACS = get_pacs_details()
    def __init__(self, title:str ="Browse and Download", size:tuple=(800, 550)) -> None:
        wx.Frame.__init__(self, None, -1, title, size =size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER) 
        self.panel = wx.Panel(self, wx.ID_ANY, size=size)
        self.main_layout = wx.BoxSizer(wx.VERTICAL)
        self.configured_pacs_mapper = self.CONFIGURED_PACS_MAPPER
        self.all_pacs = self.ALL_PACS
        self.configured_pacs = self.CONFIGURED_PACS
        self.create_ui()
        self.panel.SetSizer(self.main_layout)

    def create_line(self, horizontal:int =1) -> None:
        if horizontal:
            self.sl = wx.StaticLine(self.panel, 1, style=wx.LI_HORIZONTAL)
        else:
            self.sl = wx.StaticLine(self.panel, 2, style=wx.LI_VERTICAL)
        self.main_layout.Add(self.sl, 0, wx.EXPAND | wx.ALL, 1)

    def create_ui(self) -> None:
        self.main_layout.Add(self.create_header_1(), 0, wx.EXPAND | wx.ALL, 1)
        self.create_line()
        self.main_layout.Add(self.create_header_2(), 0, wx.EXPAND | wx.ALL, 1)
        self.main_layout.Add(self.create_show_search_result([]), 1, wx.EXPAND | wx.ALL, 1)
        self.main_layout.Add(self.create_image_details(size = (-1,130)), 1, wx.EXPAND | wx.ALL, 1)
        self.main_layout.Add(self.create_footer(),1, wx.RIGHT, 1)

    def create_select_box(self, locations:list, cur_selection:int=0, **kwargs) -> wx.ComboBox:
        combo = wx.ComboBox(self.panel, choices=locations, style =wx.CB_DROPDOWN | wx.CB_SORT)
        combo.SetSelection(cur_selection)
        combo.Bind(wx.EVT_COMBOBOX_CLOSEUP, lambda event: self.on_selection_X(event, **kwargs))
        return combo

    def on_selection_X(self, event:wx.Event, **kwargs) ->None:
        obj = event.GetEventObject()
        selected_text = obj.GetStringSelection()
        idx = obj.FindString(selected_text)
        if kwargs.get('reactors'):
            reactors = kwargs.get('reactors')
            on_option = kwargs.get('on_option')
            if selected_text == on_option or idx == on_option:
                for reactor in reactors:
                    reactor.Enable()
            else:
                for reactor in reactors:
                    reactor.Disable()

    def popup(self, event:wx.Event)->None:
        pop = Configuration()
        pop.Show()
        pop.Bind(wx.EVT_CLOSE, self.on_close)

    
    def on_close(self, event:wx.Event)->None:
        obj = json_serial(CONFIG_FILE)
        self.configured_pacs_mapper, self.all_pacs, self.configured_pacs = get_pacs_details()
        self.pacs_location.Clear()
        for i, pacs in enumerate(self.all_pacs):
            self.pacs_location.Append(pacs)
        self.pacs_location.SetSelection(0)
        event.Skip()

    def on_date_changed(self, event:wx.Event)->None:

        try:
            print(event.GetEventObject())
            print(dir (event.GetEventObject()) )
            print(event.GetEventObject().LabelText)
            print(f"cur_date is: {event.GetEventObject().GetValue()}")
        except Exception as e:
            print(f"ERROR IS: {e}")


    def date_range_helper(self, option:str)->str:
        if option == 'ALL': return "19000101-99991231"
        elif option == 'TODAY':
            # find today's date
            today = datetime.date.today()
            # format this in string of "YYYYMMDD"
            today = today.strftime("%Y%m%d")
            return f"{today}-{today}"
        elif option == 'YESTERDAY':
            # find yesterday's date
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            # format this in string of "YYYYMMDD"
            yesterday = yesterday.strftime("%Y%m%d")
            return f"{yesterday}-{yesterday}"
        
        elif option == 'LAST 7 DAYS':
            # find today's date
            today = datetime.date.today()
            # find 7 days before today's date
            last_7_days = today - datetime.timedelta(days=7)
            # format this in string of "YYYYMMDD"
            today = today.strftime("%Y%m%d")
            last_7_days = last_7_days.strftime("%Y%m%d")
            return f"{last_7_days}-{today}"
        
        elif option == 'LAST 30 DAYS':
            today = datetime.date.today()
            last_30_days = today - datetime.timedelta(days=30)
            today = today.strftime("%Y%m%d")
            last_30_days = last_30_days.strftime("%Y%m%d")
            return f"{last_30_days}-{today}"
        else:
            start_date_range = self.start_date_range.GetValue()
            start_date_range = start_date_range.FormatISODate().replace('-', '')
            end_date_range = self.end_date_range.GetValue().FormatISODate().replace('-', '')
            return f"{start_date_range}-{end_date_range}"
        

    def search_result(self, event:wx.Event, **kwargs)->None:
        """
        This function is called when the search button is clicked or Enter is pressed
        It Make CFIND Request to the PACS and get the result
        """

        date_range = self.date_range_helper(self.all_dates.GetValue())

        pacs_location = self.pacs_location.GetStringSelection()

        # get the value of the data type
        data_type = self.search_type.GetStringSelection()
        data_type = data_type.replace(' ', '')
        search_value = kwargs.get('obj').GetValue() if kwargs.get('obj') else self.search_textbox.GetValue()

        search_filter = {
            'PatientID': '*',
            'PatientName': '*',
            'AccessionNumber': '*',
        }
        search_filter[data_type] = search_value

        #host, port = self.configured_pacs_mapper.get(pacs_location).get('IP ADDRESS'), int(self.configured_pacs_mapper.get(pacs_location).get('PORT'))
        

        
        def make_c_find_request(pacs_obj):
            thost = pacs_obj.get('IP ADDRESS')
            tport = pacs_obj.get('PORT', 104)
            cfind_obj = CFind(host=thost, port=tport)
            print(date_range, "daterange")
            tmp_result = cfind_obj.make_request(aet='', aet_title='', StudyDate=date_range, pacs_location=pacs_location, PatientID=search_filter.get('PatientID', '*'), PatientName=search_filter.get('PatientName', '*'), AccessionNumber=search_filter.get('AccessionNumber', '*'))
            
            return tmp_result

        result = []
        self.searching_text.SetLabel("Searching.....")
        PUBLIC_PACS_SERVER = [{'IP ADDRESS': 'DicomServer.co.uk', 'PORT': 104}] #configured_pacs
        #PUBLIC_PACS_SERVER = self.configured_pacs
        msg_dialog = wx.MessageDialog(self, "Searching, please wait...", "Search", wx.OK|wx.ICON_INFORMATION)
        msg_dialog.ShowModal()
        
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=len(PUBLIC_PACS_SERVER)) as executor:
            future_to_obj = {executor.submit(make_c_find_request, pacs_obj): pacs_obj for pacs_obj in PUBLIC_PACS_SERVER}
            for future in concurrent.futures.as_completed(future_to_obj):
                obj = future_to_obj[future]
                try:
                    tmp_result = future.result()
                except Exception as exc:
                    print('%r generated an exception: %s' % (obj, exc))
                else:
                    result.extend(tmp_result)

        end_time = time.time()
        msg_dialog.Destroy()
        print(f"Time taken is: {end_time - start_time}")
        search_img_table = self.result_table
        if search_img_table.GetNumberRows() > 0:
            search_img_table.DeleteRows(0, numRows=search_img_table.GetNumberRows())
        try:
            tables_data = result 
        except Exception as e:
            print(f"ERROR IS: {e}")
            tables_data = []

        for i in range(len(tables_data)):
            values = tables_data[i]
            search_img_table.AppendRows(numRows=1)
            for col_nu in range(search_img_table.GetNumberCols()):
                cols_name = search_img_table.GetColLabelValue(col_nu)
                cell_value = str(values.get(cols_name, 'NA'))
                
                search_img_table.SetCellValue( max(0, search_img_table.GetNumberRows()-1), col_nu, cell_value )
                search_img_table.SetCellOverflow(max(0, search_img_table.GetNumberRows()-1), col_nu,True)


        self.searching_text.SetLabel(f"Total Result Found: {len(tables_data)}")                                
        
    def on_clear(self, event:wx.Event, obj:Any):
        obj.SetValue("")

    def on_selection(self, event:wx.Event):
        obj = event.GetEventObject()
        print(obj)
        row_id = event.GetRow()
        print(row_id)
        obj.SelectRow(row_id)
        d = {}
        for col in range(obj.GetNumberCols()):
            label = obj.GetColLabelValue(col)
            value = obj.GetCellValue(row_id, col)
            d[label] = value
            print(label, value)

        image_details_panel = self.img_details_table
        if image_details_panel.GetNumberRows() >0:
            image_details_panel.DeleteRows(0)
        image_details_panel.AppendRows(1)
        for col_nu in range(image_details_panel.GetNumberCols()):
            col_label = image_details_panel.GetColLabelValue(col_nu)
            print(d.get(col_label, "TEST DATA"))
            image_details_panel.SetCellValue(image_details_panel.GetNumberRows()-1, col_nu, d.get(col_label, "TEST DATA"))
        self.download_image_btn.Enable()

    def create_header_1(self):
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        #pacs configuration button
        pacs_config_button = wx.Button(self.panel, label="PACS Config")
        pacs_config_button.Bind(wx.EVT_BUTTON, self.popup)
        main_sizer.Add(pacs_config_button, 0, wx.ALL, 5)

        # pacs location selector
        self.pacs_locations_list = self.all_pacs
        self.pacs_location = self.create_select_box(self.pacs_locations_list, 0)
        main_sizer.Add(self.pacs_location, 0, wx.ALL, 5)

        # modalitites
        self.modalities_list = ["All Modalities", "CT", "MR", "US", "CR", "DX", "MG", "NM", "OT", "PT", "RF", "SC", "XA", "XC"]
        self.modalities = self.create_select_box(self.modalities_list, 0)
        main_sizer.Add(self.modalities, 0, wx.ALL, 5)



        #custom date range
        self.start_date_range = wxadv.DatePickerCtrl(self.panel, style=wxadv.DP_DROPDOWN)
        self.start_date_range.Bind(wxadv.EVT_DATE_CHANGED, self.on_date_changed)
        self.start_date_range.Disable()
        self.end_date_range = wxadv.DatePickerCtrl(self.panel, style=wxadv.DP_DROPDOWN)
        self.end_date_range.Bind(wxadv.EVT_DATE_CHANGED, self.on_date_changed)
        self.end_date_range.Disable()


        # all dates
        self.all_dates_list = ['ALL','Custom', 'Today', 'Yesterday', 'Last 7 Days']
        self.all_dates = self.create_select_box(self.all_dates_list, 0, reactors=[self.start_date_range, self.end_date_range], on_option='Custom')
        
        main_sizer.Add(self.all_dates, 0, wx.ALL, 5)
        main_sizer.Add(self.start_date_range, 0, wx.ALL, 5)
        main_sizer.Add(self.end_date_range, 0, wx.ALL, 5)

        return main_sizer

    def create_header_2(self):

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        #search type
        search_type_list = ["Patient ID", "Patient Name", "Accession Number"]
        self.search_type = self.create_select_box(search_type_list, 2)
        main_sizer.Add(self.search_type, 0, wx.ALL, 5)

        #textbox
        self.search_textbox = wx.TextCtrl(self.panel, size=(250, -1) ,style=wx.TE_PROCESS_ENTER)
        self.search_textbox.SetHint("Enter Search Text")
        self.search_textbox.Bind(wx.EVT_TEXT_ENTER, self.search_result)
        main_sizer.Add(self.search_textbox, 0, wx.ALL, 5)

        #search button
        search_button = wx.Button(self.panel, label="Search")
        search_button.Bind(wx.EVT_BUTTON, lambda event :self.search_result(event, obj= self.search_textbox))
        main_sizer.Add(search_button, 0, wx.ALL, 5)

        #clear button
        clear_button = wx.Button(self.panel, label="Clear")
        clear_button.Bind(wx.EVT_BUTTON, lambda event : self.on_clear(event, self.search_textbox))

        main_sizer.Add(clear_button, 0, wx.ALL, 5)

        return main_sizer
    
    def create_table(self, array:list, cols_list:list, size:tuple= (-1,200)) -> gridlib.Grid:
        cur_table = gridlib.Grid(self.panel, wx.ID_ANY, size=size)
        cur_table.CreateGrid(len(array), len(cols_list))
        cur_table.SetDefaultColSize(150)
        
        for i,col in enumerate(cols_list):
            cur_table.SetColLabelValue(i, col)

        for i, row in enumerate(array):
            for j, val in enumerate(row):
                cur_table.SetCellValue(i, j, str(val))
        cur_table.HideRowLabels()

        cur_table.SetScrollbars(100, 100, 10, 10)
        return cur_table
        
    def create_show_search_result(self, arr:list)-> wx.StaticBoxSizer:
        box = wx.StaticBox(self.panel, label='')
        main_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        cols_list = COLS
        self.result_table = self.create_table(arr, cols_list)
        self.result_table.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self.on_selection)
        main_sizer.Add(self.result_table, 1, wx.EXPAND | wx.ALL, 5)
        return main_sizer
    
    def create_image_details(self, size:tuple= (-1,200))-> wx.StaticBoxSizer:
        box = wx.StaticBox(self.panel, label='')
        main_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        cols_list = COLS
        self.img_details_table= self.create_table([], cols_list, size= size)
        main_sizer.Add(self.img_details_table, 1, wx.EXPAND | wx.ALL, 5)
        return main_sizer
    
    def create_footer(self)-> wx.BoxSizer:
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.download_image_btn = wx.Button(self.panel, label = 'Download')
        self.download_image_btn.Disable()
        button_sizer.Add(self.download_image_btn, 0, wx.ALL, 5)
        self.download_history = wx.Button(self.panel, label = 'Download History')
        self.download_history.Bind(wx.EVT_BUTTON, self.show_download_history)

        main_sizer.Add(button_sizer, 1, wx.RIGHT, 1)
        main_sizer.Add(self.download_history, 0, wx.ALL, 5)
        self.searching_text = wx.StaticText(self.panel, label="")
        main_sizer.Add(self.searching_text, 0, wx.ALL, 5)
        return main_sizer
    
    def show_download_history(self, event:wx.Event)->None:
        pop = DownloadHistory()
        pop.Show()
        pop.Bind(wx.EVT_CLOSE, self.on_close)


if __name__ == '__main__':
    app = wx.App()
    frame = Browse()
    frame.Show()
    app.MainLoop()

