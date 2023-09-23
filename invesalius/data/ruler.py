# -----------------------------------------------------------------------------------
# This file contains the base class and child classes of the ruler for viewer slices
#
# Author: Ginigal Godage Vimukthi Pahasara
# GitHub ID: VimukthiPahasaraGodage
# Last Modified Date: 16th March 2023
#
# -----------------------------------------------------------------------------------

from abc import ABC, abstractmethod

import wx
import vtkmodules.all as vtk
import invesalius.project as project
import invesalius.constants as const
import matplotlib.pyplot as plt
import numpy as np

E_SHAPED = TOP_OR_LEFT = 0
C_SHAPED = BOTTOM_OR_RIGHT = 1



class Ruler(ABC):
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

    def __init__(self, viewer_slice):
        self.layer = 99
        self.children = []
        self.viewer_slice = viewer_slice
        self.slice_data = viewer_slice.slice_data
        self.interactor = viewer_slice.interactor

        self.plot_count = 0

    def GetCameraDirections(self):
        """
        Returns the camera up direction and the camera direction

        Returns:
            tuple: (up direction, camera position), eg:- ((1, 0, 0), (0, -1, 0))
        """
        proj = project.Project()
        original_orientation = proj.original_orientation
        view_orientation = self.slice_data.orientation
        return (const.SLICE_POSITION[original_orientation][0][view_orientation],
                const.SLICE_POSITION[original_orientation][1][view_orientation])

    def GetViewPortHeight(self):
        """
        Returns the height of the viewport in millimeters

        Returns:
            float: Height of viewport in mm
        """
        camera = self.slice_data.renderer.GetActiveCamera()
        # print(f"Viewport Height in Millimeters: {camera.GetParallelScale() * 2}")
        return camera.GetParallelScale() * 2

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
        font.Scale(self.viewer_slice.GetContentScaleFactor())
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
        w, h = self.viewer_slice.canvas.calc_text_size(text, self.GetFont(font_size))  # w, h are in pixels
        return w / self.GetWindowSize()[0], h / self.GetWindowSize()[1]

    def GetLeftTextProperties(self):
        """
        Returns properties of left text on viewer slice.
        The properties are coordinates of the left top corner of bounding box and
        the width and height of bounding box

        Returns:
            tuple: (x coordinate, y coordinate, width, height)
                    All properties are represented as a proportion to the size of viewport
        """
        left_text = self.viewer_slice.left_text
        left_text_font = self.GetFont(left_text.symbolic_syze)
        w, h = self.viewer_slice.canvas.calc_text_size(left_text.text, left_text_font)  # w, h are in pixels
        x, y = left_text.position  # x, y are in proportions relative to window size
        return x, y, w / self.GetWindowSize()[0], h / self.GetWindowSize()[1]

    def GetSliceNumberProperties(self):
        """
        Returns properties of slice number text on viewer slice.
        The properties are coordinates of the left top corner of bounding box and
        the width and height of bounding box

        Returns:
            tuple: (x coordinate, y coordinate, width, height)
                    All properties are represented as a proportion to the size of viewport
        """
        slice_number = self.slice_data.text
        slice_number_font = self.GetFont(slice_number.symbolic_syze)
        w, h = self.viewer_slice.canvas.calc_text_size(slice_number.text, slice_number_font)  # w, h are in pixels
        x, y = slice_number.position  # x, y are in proportions relative to window size
        return x, y, w / self.GetWindowSize()[0], h / self.GetWindowSize()[1]

    def GetImageSize(self):
        """
        Returns the slice image size(width and height) in millimeters

        Returns:
            tuple: (image width in mm, image height in mm)
        """
        const_direction = np.array([1, 1, 1])
        bounds = self.slice_data.actor.GetBounds()
        bounds_matrix = np.array([bounds[0:2], bounds[2:4], bounds[4:]])
        direction_matrix = np.array(self.GetCameraDirections())
        direction_matrix = np.array([abs(direction_matrix[0]),
                                     const_direction - abs(direction_matrix[0] + direction_matrix[1])])
        image_size_matrix = np.dot(direction_matrix, bounds_matrix)
        image_size = (abs(image_size_matrix[1][1] - image_size_matrix[1][0]),
                      abs(image_size_matrix[0][1] - image_size_matrix[0][0]))
        return image_size

    def RoundToMultiple(self, number, multiple, floor=True):
        """
        Returns the number rounded to a multiple of the argument: multiple

        Args:
            number (float): Number to be rounded
            multiple (int): Multiple
            floor (boolean): If True, the rounding will be done to the floor value
                             If False, the rounding will be done to the ceil value

        Returns:
            int: rounded value
                 eg:- number = 122.0567, multiple = 5 and floor = True will return 120
        """
        rounded = multiple * round(number / multiple)
        if rounded > number and floor:
            rounded = rounded - multiple * 2
        elif rounded < number and not floor:
            rounded = rounded + multiple * 2
        return rounded

    def get_pixel_data(self, gc, canvas):
        if gc is not None and canvas is not None:
            renderer_window = self.slice_data.renderer.GetRenderWindow()
            width, height = renderer_window.GetSize()
            pixel_data = vtk.vtkUnsignedCharArray()
            pixel_data.SetNumberOfComponents(4)
            pixel_data.SetNumberOfTuples(width * height)
            # TODO: Optimize to only get the pixel data of the area the ruler was drawn instead of the whole window
            pixel_data = renderer_window.GetRGBAPixelData(0, 0, width - 1, height - 1, vtk.VTK_RGBA)

            # TODO: Create an algorithm to check for a suitable contrasting colour by examining the pixel data

    # bitmap = canvas.bitmap
    # width, height = bitmap.GetSize()
    # r = g = b = [0 for i in range(0, 256)]
    # values = [i for i in range(0, 256)]
    # img = bitmap.ConvertToImage()
    # for y in range(height):
    #     for x in range(width):
    #         red = img.GetRed(x, y)
    #         green = img.GetGreen(x, y)
    #         blue = img.GetBlue(x, y)
    #         r[red] = r[red] + 1
    #         g[green] = g[green] + 1
    #         b[blue] = b[blue] + 1
    #
    # plt.plot(values, r, label="Red", color="red")
    # plt.plot(values, g, label="Green", color="green")
    # plt.plot(values, b, label="Blue", color="blue")

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


class GenericRuler(Ruler):
    """
    # This class implements the abstract Ruler class.
    # GenericRuler class represent a ruler that has a shape of 'E' letter.
    # The ruler represented by this class is drawn on the left, top, right, and bottom side of the viewer.
    # The middle line segment of three parallel line segments of the letter 'E' represents the zero mark
      while the other two represent a specific distance up and down(or left and right) from zero mark(in millimeters).
    # If the height(or width) of the image in the viewer is less than the maximum length the ruler can show(when zoom out),
      the ruler will show a rounded value of the height(or width) of the image.
    # If the height(or width) of the image in the viewer is greater than the maximum length the ruler can show(when zoom in),
      the ruler will show a rounded value of the maximum height(or width) the ruler can show.

      Attributes:
        viewer_slice (invesalius.data.viewer_slice.Viewer): The viewer the ruler has to be drawn
        left (boolean): True if the ruler has to be drawn on left side of viewer (default is True)
        top (boolean): True if the ruler has to be drawn on top side of viewer (default is False)
        right (boolean): True if the ruler has to be drawn on right side of viewer (default is False)
        bottom (boolean): True if the ruler has to be drawn on bottom side of viewer (default is False)
        padding (float): Padding to the ruler from left text(eg:- 'R', 'T') as a proportion to the viewport size
        scale_text_padding (float): Top and bottom padding of the measurement text(eg:- 120 mm)
        center_mark (float): The length of the middle line segment as a proportion to the viewport size
        edge_mark (float): The length of the up and bottom line segments as proportions to the viewport size
        font_size (int): Predefined in wx, eg:- wx.FONTSIZE_SMALL, wx.FONTSIZE_MEDIUM
        colour (tuple): Colour of the lines and text of the ruler, (red_value/255, green_value/255, blue_value/255)
        ruler_scale_step (list of tuples): ruler_scale_step is something like [(-1, 25, 5), (25, 1, 1), (1, 0.1, 0.1), (0.1, 0, 0.01)]
                                           The meaning of this is
                                                when infinity < m <= 25 mm: step size =  5 mm
                                                when 25 < m <= 1 mm: step size =  1 mm
                                                when 1 < m <= 0.1 mm: step size =  0.1 mm
                                                when 0.1 < m <= 0 mm: step size =  0.01 mm
                                           step size is the multiple which the measurement of the ruler(the height of the viewport in mm)
                                           is rounded to(e.g.:- if the viewport height is 123 mm, a ruler will be drawn to represent a 120 mm of height)

      Methods:
        draw_to_canvas(gc, canvas): Draws the GenericLeftRuler on viewer
    """
    def __init__(self, viewer_slice, left=True, top=False, right=False, bottom=False):
        super().__init__(viewer_slice)
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
        self.padding = 0.015
        self.scale_text_padding = 0.005
        self.center_mark = 0.01
        self.edge_mark = 0.02
        self.font_size = wx.FONTSIZE_SMALL
        self.colour = (1, 1, 1)
        self.ruler_scale_step = [(-1, 25, 5), (25, 1, 1), (1, 0.1, 0.1), (0.1, 0, 0.01)]

    def draw_to_canvas(self, gc, canvas):
        if self.left:
            # TODO: Draw a ruler in the left side of viewer
            pass

        if self.top:
            # TODO: Draw a ruler in the top side of viewer
            pass

        if self.right:
            # TODO: Draw a ruler in the right side of viewer
            pass

        if self.bottom:
            # TODO: Draw a ruler in the bottom side of viewer
            pass


class GenericLeftRuler(Ruler):
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

    def __init__(self, viewer_slice):
        super().__init__(viewer_slice)
        self.left_padding = 0.015
        self.scale_text_padding = 0.005
        self.center_mark = 0.01
        self.edge_mark = 0.02
        self.font_size = wx.FONTSIZE_SMALL
        self.colour = (1, 1, 1)
        self.ruler_scale_step = 5

    def draw_to_canvas(self, gc, canvas):
        image_height = self.GetImageSize()[1]
        dummy_scale_text_size = self.GetTextSize("120 mm", self.font_size)
        slice_number_prop = self.GetSliceNumberProperties()
        left_text_prop = self.GetLeftTextProperties()
        pixel_size = self.GetPixelSize()
        window_size = self.GetWindowSize()
        ruler_min_y = (slice_number_prop[1] + dummy_scale_text_size[1] + 2 * self.scale_text_padding) * window_size[1]
        ruler_min_x = (left_text_prop[0] + left_text_prop[2] + self.left_padding) * window_size[0]
        max_ruler_height = window_size[1] - 2 * ruler_min_y
        image_size_in_pixels = image_height / pixel_size
        if image_size_in_pixels < max_ruler_height:
            ruler_height = self.RoundToMultiple(image_height / 2, self.ruler_scale_step) * 2
        else:
            ruler_height = self.RoundToMultiple((max_ruler_height * pixel_size / 2), self.ruler_scale_step) * 2
        ruler_height_pixels = ruler_height / pixel_size
        lines = [[(ruler_min_x, (window_size[1] - ruler_height_pixels) / 2),
                  (ruler_min_x, (window_size[1] + ruler_height_pixels) / 2)],
                 [(ruler_min_x, (window_size[1] - ruler_height_pixels) / 2),
                  (ruler_min_x + self.edge_mark * window_size[0], (window_size[1] - ruler_height_pixels) / 2)],
                 [(ruler_min_x, window_size[1] / 2),
                  (ruler_min_x + self.center_mark * window_size[0], window_size[1] / 2)],
                 [(ruler_min_x, (window_size[1] + ruler_height_pixels) / 2),
                  (ruler_min_x + self.edge_mark * window_size[0], (window_size[1] + ruler_height_pixels) / 2)]]
        r, g, b = self.colour
        for line in lines:
            canvas.draw_line(line[0], line[1], colour=(r * 255, g * 255, b * 255, 255), width=1)
        text_size = self.GetTextSize(str(round(ruler_height / 2)) + " mm", self.font_size)
        x_text = (2 * ruler_min_x + self.edge_mark * window_size[0] - (text_size[0] * window_size[0])) / 2
        y_text = (window_size[1] - ruler_height_pixels) / 2 - self.scale_text_padding
        canvas.draw_text(f"{round(ruler_height / 2)} mm", (x_text, y_text), font=self.GetFont(self.font_size),
                         txt_colour=(r * 255, g * 255, b * 255))
        self.get_pixel_data(gc, canvas)


class StyledRuler(GenericRuler):
    """
    # This class implements the abstract Ruler class.
    # StyledRuler class represent a ruler that has a shape of 'E' letter or 'C' letter. And between the marks, small
      marks representing the step size(5mm, 2mm, 1mm, 0.1mm) will be added. In the 'E' letter shaped ruler the zero mark
      is the center mark while in letter 'C' shaped ruler, the zero mark will be either of the two edge marks.
    # The ruler represented by this class is drawn on the left, top, right, and bottom side of the viewer.
    # In ruler with letter 'E' shape, the center mark represents the zero mark
      while the other two represent a specific distance up and down(or left and right) from zero mark(in millimeters).
    # If the height(or width) of the image in the viewer is less than the maximum length the ruler can show(when zoom out),
      the ruler will show a rounded value of the height(or width) of the image.
    # If the height(or width) of the image in the viewer is greater than the maximum length the ruler can show(when zoom in),
      the ruler will show a rounded value of the maximum height(or width) the ruler can show.

      Attributes:
        viewer_slice (invesalius.data.viewer_slice.Viewer): The viewer the ruler has to be drawn
        type (int): E shaped ruler = 0; C shaped ruler = 0
        zero_pos (int): If the ruler type is 1('C' shaped ruler) then,
                        0=top for vertical and left for horizontal
                        1=bottom for vertical and right for horizontal
        left (boolean): True if the ruler has to be drawn on left side of viewer (default is True)
        top (boolean): True if the ruler has to be drawn on top side of viewer (default is False)
        right (boolean): True if the ruler has to be drawn on right side of viewer (default is False)
        bottom (boolean): True if the ruler has to be drawn on bottom side of viewer (default is False)
        padding (float): Padding to the ruler from left text(eg:- 'R', 'T') as a proportion to the viewport size
        scale_text_padding (float): Top and bottom padding of the measurement text(eg:- 120 mm)
        center_mark (float): The length of the middle line segment as a proportion to the viewport size
        edge_mark (float): The length of the up and bottom line segments as proportions to the viewport size
        font_size (int): Predefined in wx, eg:- wx.FONTSIZE_SMALL, wx.FONTSIZE_MEDIUM
        colour (tuple): Colour of the lines and text of the ruler, (red_value/255, green_value/255, blue_value/255)
        ruler_scale_step (list of tuples): ruler_scale_step is something like [(-1, 25, 5), (25, 1, 1), (1, 0.1, 0.1), (0.1, 0, 0.01)]
                                           The meaning of this is
                                                when infinity < m <= 25 mm: step size =  5 mm
                                                when 25 < m <= 1 mm: step size =  1 mm
                                                when 1 < m <= 0.1 mm: step size =  0.1 mm
                                                when 0.1 < m <= 0 mm: step size =  0.01 mm
                                           step size is the multiple which the measurement of the ruler(the height of the viewport in mm)
                                           is rounded to(e.g.:- if the viewport height is 123 mm, a ruler will be drawn to represent a 120 mm of height)

      Methods:
        draw_to_canvas(gc, canvas): Draws the GenericLeftRuler on viewer
    """
    def __init__(self, viewer_slice, type_, zero_pos=0, left=True, top=False, right=False, bottom=False):
        super().__init__(viewer_slice, left, top, right, bottom)
        self.type_ = type_
        self.zero_pos = zero_pos

    def draw_to_canvas(self, gc, canvas):
        if self.type_ == E_SHAPED:
            super().draw_to_canvas(gc, canvas)
            # TODO: Implement adding of marks corresponding to step size
        else:
            # TODO: Implement drawing a 'C' shaped ruler
            pass
