"""GUI components for IRC Ebook Fetcher."""

from tkinter import Frame, Canvas, Scrollbar, Widget
from tkinter import VERTICAL, Y, RIGHT, LEFT, BOTH, TRUE


class VerticalScrolledFrame:
    """
    A vertically scrolled Frame that can be treated like any other Frame.
    Revised from https://gist.github.com/novel-yet-trivial/3eddfce704db3082e38c84664fc1fdf8
    """

    def __init__(self, master, **kwargs):
        """
        Initialize scrolled frame.

        Args:
            master: Parent widget
            **kwargs: Additional arguments for Frame
        """
        width = kwargs.pop("width", None)
        height = kwargs.pop("height", None)
        self.outer = Frame(master, **kwargs)

        self.vsb = Scrollbar(self.outer, orient=VERTICAL)
        self.vsb.pack(fill=Y, side=RIGHT)
        self.canvas = Canvas(self.outer, highlightthickness=0, width=width, height=height)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.canvas["yscrollcommand"] = self.vsb.set

        # Mouse scroll bindings
        self.canvas.bind("<Enter>", self._bind_mouse)
        self.canvas.bind("<Leave>", self._unbind_mouse)
        self.vsb["command"] = self.canvas.yview

        self.inner = Frame(self.canvas)
        self.canvas.create_window(4, 4, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_frame_configure)

        self.outer_attr = set(dir(Widget))

    def __getattr__(self, item):
        """Delegate attributes to appropriate frame."""
        if item in self.outer_attr:
            return getattr(self.outer, item)
        else:
            return getattr(self.inner, item)

    def _on_frame_configure(self, event=None):
        """Handle frame resize."""
        x1, y1, x2, y2 = self.canvas.bbox("all")
        height = self.canvas.winfo_height()
        self.canvas.config(scrollregion=(0, 0, x2, max(y2, height)))

    def _bind_mouse(self, event=None):
        """Bind mouse wheel events."""
        self.canvas.bind_all("<4>", self._on_mousewheel)
        self.canvas.bind_all("<5>", self._on_mousewheel)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mouse(self, event=None):
        """Unbind mouse wheel events."""
        self.canvas.unbind_all("<4>")
        self.canvas.unbind_all("<5>")
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")


def color_scale(hexstr: str, scale_factor: float) -> str:
    """
    Scale a hex color by a factor.

    Args:
        hexstr: Hex color string (e.g., "#FFFFFF")
        scale_factor: Scale factor (< 1 to darken, > 1 to brighten)

    Returns:
        Scaled hex color string
    """
    hexstr = hexstr.strip("#")

    if scale_factor < 0 or len(hexstr) != 6:
        return f"#{hexstr}"

    r = int(hexstr[:2], 16)
    g = int(hexstr[2:4], 16)
    b = int(hexstr[4:], 16)

    r = int(min(max(r * scale_factor, 0), 255))
    g = int(min(max(g * scale_factor, 0), 255))
    b = int(min(max(b * scale_factor, 0), 255))

    return f"#{r:02x}{g:02x}{b:02x}"
