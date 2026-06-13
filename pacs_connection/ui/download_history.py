import wx
import wx.grid

class DownloadTable(wx.grid.Grid):
    """A grid table to display download history."""
    COL_NAMES = ['Patient Name', 'Study Date', 'Size', 'Progress', 'Download Time', 'Bytes Transferred', 'PACS Location']

    def __init__(self, parent):
        super().__init__(parent)
        self.CreateGrid(0, len(self.COL_NAMES))
        for i, col_name in enumerate(self.COL_NAMES):
            self.SetColLabelValue(i, col_name)
        self.EnableEditing(False)
        self.HideRowLabels()

    def add_row(self, data:list):
        row = self.GetNumberRows()
        self.AppendRows(1)
        for i, value in enumerate(data):
            self.SetCellValue(row, i, str(value))

    def set_column_widths(self, widths):
        for i, width in enumerate(widths):
            self.SetColSize(i, width)


class DownloadHistory(wx.Frame):
    """A GUI to display download history."""

    def __init__(self, title:str ="Download History", size:tuple=(-1, 35), data=None) -> None:
        super().__init__(None, -1, title, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        self.data = data or []
        self.create_ui()

    def create_ui(self):
        self.panel = wx.Panel(self)
        self.main_layout = wx.BoxSizer(wx.VERTICAL)

        # Create the download table
        self.table = DownloadTable(self.panel)
        self.main_layout.Add(self.table, 1, wx.EXPAND|wx.ALL, 10)

        # Add the data to the download table
        for row_data in self.data:
            self.table.add_row(row_data)

        # Set the column widths of the download table
        self.table.set_column_widths([150, 100, 80, 80, 100, 120, 250])

        # Add the cancel and close buttons to the footer
        self.footer_layout = wx.BoxSizer(wx.HORIZONTAL)
        self.cancel_button = wx.Button(self.panel, wx.ID_ANY, 'Cancel')
        self.cancel_button.Disable()
        self.close_button = wx.Button(self.panel, wx.ID_ANY, 'Close')
        self.close_button.Bind(wx.EVT_BUTTON, self.on_close)

        self.footer_layout.Add(self.cancel_button, 0, wx.ALIGN_LEFT|wx.ALL, 5)
        self.footer_layout.AddStretchSpacer(1)
        self.footer_layout.Add(self.close_button, 0, wx.ALIGN_LEFT|wx.ALL, 5)
        self.main_layout.Add(self.footer_layout, 0, wx.EXPAND|wx.ALL, 10)

        # Set the panel sizer
        self.panel.SetSizer(self.main_layout)

    def enable_close_button(self, enabled=True):
        self.close_button.Enable(enabled)

    def update_row(self, row, data):
        for i, value in enumerate(data):
            self.table.SetCellValue(row, i, str(value))

    def on_close(self, event:wx.Event)->None:
        self.Close()


if __name__ == '__main__':
    app = wx.App()
    data=[
            ['John Doe', '2022-01-01', '100 MB', '50%', '00:10:00', '50 MB', 'https://pacs.example.com/study1'],
            ['Jane Doe', '2022-01-02', '200 MB', '75%', '00:20:00', '150 MB', 'https://pacs.example.com/study2'],
            ['Bob Smith', '2022-01-03', '50 MB', '25%', '00:05:00', '10 MB', 'https://pacs.example.com/study3'],
        ]
    frame = DownloadHistory(data=data)
    frame.Show()
    app.MainLoop()