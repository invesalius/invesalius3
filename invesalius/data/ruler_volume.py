# -----------------------------------------------------------------------------------
# This file contains the base class and child classes of the ruler for viewer slices
#
# Author: Ginigal Godage Vimukthi Pahasara
# GitHub ID: VimukthiPahasaraGodage
# Last Modified Date: 16th March 2023
#
# -----------------------------------------------------------------------------------
from abc import ABC, abstractmethod

import numpy as np
import vtkmodules.all as vtk
import wx

import invesalius.constants as const

E_SHAPED = TOP_OR_LEFT = 0
C_SHAPED = BOTTOM_OR_RIGHT = 1


class RulerVolume(ABC):
    """
    # This is the abstract class for a Ruler object
    # This class contains all the helper methods that any implementation of this abstract class will need

      Attributes:
        layer (int): Layer which Ruler will be drawn(Let's use the same layer as orientation texts)
        children (array): Array of children of Ruler([] for now)
        viewer_slice (invesalius.data.viewer_slice.Viewer): Viewer which the ruler should be drawn
        slice_data (invesalius.data.slice_data.SliceData): SliceData object associated with Viewer
        interactor (wxVTKRenderWindowInteractor): wxVTKRenderWindowInteractor object associated with Viewer

      Methods:
        GetCameraDirection(): Returns the camera up direction and the camera direction
        GetViewPortHeight(): Returns the height of the viewport in millimeters
        GetWindowSize(): Return the window size of viewer slice in pixels
        GetPixelSize(): Return the height/width represented by a pixel in viewer slice in millimeters
        GetFont(font_size): Returns a wx.Font object for a given font size
        GetTextSize(text, font_size): Return the size(width and height) of the bounding box containing
                                      specified text with the specified font size
        GetLeftTextProperties(): Returns properties of left text on viewer slice.
                                 The properties are coordinates of the left top corner of bounding box and
                                 the width and height of bounding box
        GetSliceNumberProperties(): Returns properties of slice number text on viewer slice.
                                    The properties are coordinates of the left top corner of bounding box and
                                    the width and height of bounding box
        GetImageSize(): Returns the slice image size(width and height) in millimeters
        RoundToMultiple(number, multiple, floor): Returns the number rounded to a multiple of the argument: multiple
        draw_to_canvas(gc, canvas): Abstract method that must be implemented.
                                    Called when the ruler has to drawn on the canvas.
    """

    def __init__(self, viewer_volume):
        self.layer = 99
        self.children = []
        self.viewer_volume = viewer_volume
        self.interactor = viewer_volume.interactor

        self.plot_count = 0

    def GetViewPortHeight(self):
        """
        Returns the height of the viewport in millimeters

        Returns:
            float: Height of viewport in mm
        """
        camera = self.viewer_volume.ren.GetActiveCamera()
        height = camera.GetParallelScale() * 2
        return height

    def GetWindowSize(self):
        """
        Return the window size of viewer slice in pixels

        Returns:
            tuple: (width in pixels, height in pixels), eg:- (651, 331)
        """
        return self.interactor.GetRenderWindow().GetSize()

    def GetPixelSize(self):
        """
        Return the height/width represented by a pixel in viewer slice in millimeters

        Returns:
            float: Length represented by a side of a pixel in mm
        """
        return self.GetViewPortHeight() / self.GetWindowSize()[1]

    def GetFont(self, font_size):
        """
        Returns a wx.Font object for a given font size

        Args:
            font_size (int): Predefined in wx, eg:- wx.FONTSIZE_SMALL, wx.FONTSIZE_MEDIUM

        Returns:
            wx.Font object
        """
        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font.SetSymbolicSize(font_size)
        font.Scale(self.viewer_volume.GetContentScaleFactor())
        return font

    def GetTextSize(self, text, font_size):
        """
        Return the size(width and height) of the bounding box containing specified text with the specified font size

        Args:
            text (string): text to be displayed
            font_size (int): Predefined in wx, eg:- wx.FONTSIZE_SMALL, wx.FONTSIZE_MEDIUM

        Returns:
            tuple: (width as a proportion of viewport width, height as a proportion of viewport height)
                    eg:- (0.03, .0.5)
        """
        w, h = self.viewer_volume.canvas.calc_text_size(
            text, self.GetFont(font_size)
        )  # w, h are in pixels
        return w / self.GetWindowSize()[0], h / self.GetWindowSize()[1]

    def GetWLTextProperties(self):
        """
        Returns properties of slice number text on viewer slice.
        The properties are coordinates of the left top corner of bounding box and
        the width and height of bounding box

        Returns:
            tuple: (x coordinate, y coordinate, width, height)
                    All properties are represented as a proportion to the size of viewport
        """
        wl_text = self.viewer_volume.text
        wl_text_font = self.GetFont(wl_text.symbolic_syze)
        w, h = self.viewer_volume.canvas.calc_text_size(
            wl_text.text, wl_text_font
        )  # w, h are in pixels
        if wl_text.position == const.TEXT_POS_LEFT_UP:
            x, y = const.TEXT_POS_LEFT_DOWN  # x, y are in proportions relative to window size
        return x, y, w / self.GetWindowSize()[0], h / self.GetWindowSize()[1]

    def GetVolumeSize(self):
        """
        Returns the slice image size(width and height) in millimeters

        Returns:
            tuple: (image width in mm, image height in mm)
        """
        # initial_orientation = (0, 0, 1)  # up direction is z-axis
        # initial_rotational_axis = (0, 1, 0)  # y-axis
        bounds = self.viewer_volume.surface.GetBounds()
        bounds_matrix = np.abs(
            np.array([bounds[0] - bounds[1], bounds[2] - bounds[3], bounds[4] - bounds[5]])
        )
        return bounds_matrix[0], bounds_matrix[
            2
        ]  # x-axis is the width, z-axis is the height; initially

    def RoundToMultiple(self, number, multiples, floor=True):
        """
        Returns the number rounded to a multiple of the argument: multiples

        Args:
            number (float): Number to be rounded
            multiples (list): Multiples [(5000, 1000, 100, 0), (1000, 500, 50, 0), (500, 250, 10, 0), (250, 25, 5, 0),
                                         (25, 1, 1, 0), (1, 0.1, 0.1, 1), (0.1, 0.01, 0.01, 2), (0.01, 0.001, 0.001, 3),
                                         (0.001, 0.0001, 0.0001, 4), (0.0001, 0.00001, 0.00001, 5),
                                         (0.00001, 0, 0.000001, 6)]
            floor (boolean): If True, the rounding will be done to the floor value
                             If False, the rounding will be done to the ceil value

        Returns:
            int: rounded value
                 eg:- number = 122.0567, multiple = 5 and floor = True will return 120
        """
        rounded = number
        decimals = 0
        for multiple in multiples:
            high = multiple[0]
            low = multiple[1]
            if high >= number > low:
                multiple_factor = multiple[2]
                rounded = multiple_factor * round(number / multiple_factor)
                if rounded > number:
                    rounded = rounded - multiple_factor
                decimals = multiple[3]
        return rounded, decimals

    def get_pixel_data(self, gc, canvas):
        if gc is not None and canvas is not None:
            renderer_window = self.viewer_volume.ren.GetRenderWindow()
            width, height = renderer_window.GetSize()
            pixel_data = vtk.vtkUnsignedCharArray()
            pixel_data.SetNumberOfComponents(4)
            pixel_data.SetNumberOfTuples(width * height)
            # TODO: Optimize to only get the pixel data of the area the ruler was drawn instead of the whole window
            pixel_data = renderer_window.GetRGBAPixelData(0, 0, width - 1, height - 1, vtk.VTK_RGBA)
            # TODO: Create an algorithm to check for a suitable contrasting colour by examining the pixel data

    @abstractmethod
    def draw_to_canvas(self, gc, canvas):
        """
        Abstract method that must be implemented.
        Called when the ruler has to drawn on the canvas.

        Args:
            gc (wx.GraphicsContext): GraphicContext the ruler has to be drawn on
            canvas (CanvasRendererCTX): The CanvasRendererCTX object associated with the gc

        Returns:
            None
        """
        pass


class GenericLeftRulerVolume(RulerVolume):
    """
    # This class implements the abstract Ruler class.
    # GenericLeftRuler class represent a ruler that has a shape of 'E' letter.
    # The ruler represented by this class is drawn on the left side of the viewer.
    # The middle line segment of three parallel line segments of the letter 'E' represents the zero mark
      while the other two represent a specific distance up and down from zero mark(in millimeters).
    # If the height of the image in the viewer is less than the maximum length the ruler can show(when zoom out),
      the ruler will show a rounded value of the height of the image.
    # If the height of the image in the viewer is greater than the maximum length the ruler can show(when zoom in),
      the ruler will show a rounded value of the maximum height the ruler can show.

      Attributes:
        viewer_slice (invesalius.data.viewer_slice.Viewer): The viewer the ruler has to be drawn
        left_padding (float): Padding to the ruler from left text(eg:- 'R', 'T') as a proportion to the viewport size
        scale_text_padding (float): Top and bottom padding of the measurement text(eg:- 120 mm)
        center_mark (float): The length of the middle line segment as a proportion to the viewport size
        edge_mark (float): The length of the up and bottom line segments as proportions to the viewport size
        font_size (int): Predefined in wx, eg:- wx.FONTSIZE_SMALL, wx.FONTSIZE_MEDIUM
        colour (tuple): Colour of the lines and text of the ruler, (red_value/255, green_value/255, blue_value/255)
        ruler_scale_step (int): The step size the ruler's length should be rounded to in millimeters
                                If 5mm, then ruler will change length in multiples of 5mm such as 120mm, 125mm, 130mm
                                when zoom in/out

      Methods:
        draw_to_canvas(gc, canvas): Draws the GenericLeftRuler on viewer
    """

    def __init__(self, viewer_volume):
        super().__init__(viewer_volume)
        self.left_padding = 0.015
        self.scale_text_padding = 0.005
        self.center_mark = 0.01
        self.edge_mark = 0.02
        self.font_size = wx.FONTSIZE_SMALL
        self.colour = (1, 1, 1)
        self.ruler_scale_step = [
            (5000, 1000, 100, 0),
            (1000, 500, 50, 0),
            (500, 250, 10, 0),
            (250, 25, 5, 0),
            (25, 1, 1, 0),
            (1, 0.1, 0.1, 1),
            (0.1, 0.01, 0.01, 2),
            (0.01, 0.001, 0.001, 3),
            (0.001, 0.0001, 0.0001, 4),
            (0.0001, 0.00001, 0.00001, 5),
            (0.00001, 0, 0.000001, 6),
        ]

    def draw_to_canvas(self, gc, canvas):
        image_height = self.GetVolumeSize()[1]
        dummy_scale_text_size = self.GetTextSize("120 mm", self.font_size)
        wl_text_prop = self.GetWLTextProperties()
        pixel_size = self.GetPixelSize()
        window_size = self.GetWindowSize()
        ruler_min_y = (
            wl_text_prop[1] + dummy_scale_text_size[1] + 2 * self.scale_text_padding
        ) * window_size[1]
        ruler_min_x = (wl_text_prop[0] + self.left_padding) * window_size[0]
        max_ruler_height = window_size[1] - 2 * ruler_min_y
        image_size_in_pixels = image_height / pixel_size
        if image_size_in_pixels < max_ruler_height:
            ruler_half_height, decimals = self.RoundToMultiple(
                image_height / 2, self.ruler_scale_step
            )
        else:
            ruler_half_height, decimals = self.RoundToMultiple(
                (max_ruler_height * pixel_size / 2), self.ruler_scale_step
            )
        ruler_height = ruler_half_height * 2
        ruler_height_pixels = ruler_height / pixel_size
        lines = [
            [
                (ruler_min_x, (window_size[1] - ruler_height_pixels) / 2),
                (ruler_min_x, (window_size[1] + ruler_height_pixels) / 2),
            ],
            [
                (ruler_min_x, (window_size[1] - ruler_height_pixels) / 2),
                (
                    ruler_min_x + self.edge_mark * window_size[0],
                    (window_size[1] - ruler_height_pixels) / 2,
                ),
            ],
            [
                (ruler_min_x, window_size[1] / 2),
                (ruler_min_x + self.center_mark * window_size[0], window_size[1] / 2),
            ],
            [
                (ruler_min_x, (window_size[1] + ruler_height_pixels) / 2),
                (
                    ruler_min_x + self.edge_mark * window_size[0],
                    (window_size[1] + ruler_height_pixels) / 2,
                ),
            ],
        ]
        r, g, b = self.colour
        for line in lines:
            canvas.draw_line(line[0], line[1], colour=(r * 255, g * 255, b * 255, 255), width=1)
        text_size = self.GetTextSize("{:.{}f} mm".format(ruler_height, decimals), self.font_size)
        x_text = (
            2 * ruler_min_x + self.edge_mark * window_size[0] - (text_size[0] * window_size[0])
        ) / 2
        y_text = (window_size[1] - ruler_height_pixels) / 2 - self.scale_text_padding
        canvas.draw_text(
            "{:.{}f} mm".format(ruler_height, decimals),
            (x_text, y_text),
            font=self.GetFont(self.font_size),
            txt_colour=(r * 255, g * 255, b * 255),
        )
