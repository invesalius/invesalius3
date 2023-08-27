import wx
from pubsub import pub as Publisher

from invesalius.data import styles
from invesalius import project

from . import func_overlay

def load():
    style_id = styles.Styles.add_style(func_overlay.FunctionalOverlayStyle, 2)
    print(f"Style: {style_id}")

    Publisher.sendMessage("Disable actual style")
    Publisher.sendMessage("Enable style", style=style_id)