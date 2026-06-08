"""Template capture tool for the chat test framework.

Usage:
    python -m src.template_capture

Flow:
    1. User opens the target UI element on screen
    2. Click Capture -> fullscreen screenshot taken instantly
    3. Overlay appears -> drag-select the region
    4. Region cropped from frozen screenshot -> saved
"""

import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

TEMPLATES = [
    "float_button.png",
    "chat_menu.png",
    "send_button.png",
    "reset_chat.png",
]


class RegionSelector(tk.Toplevel):
    """Fullscreen overlay for drag-selecting a region.

    Uses overrideredirect + explicit geometry to reliably cover the full
    physical screen, avoiding Tkinter's broken -fullscreen on some Windows.
    """

    def __init__(self, screenshot: Image.Image, on_done):
        super().__init__()
        self.screenshot = screenshot
        self.on_done = on_done

        import pyautogui
        self.sw, self.sh = pyautogui.size()

        self.overrideredirect(True)
        self.geometry(f"{self.sw}x{self.sh}+0+0")
        self.attributes("-topmost", True)
        self.config(cursor="cross")

        self.canvas = tk.Canvas(self, highlightthickness=0,
                                width=self.sw, height=self.sh)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Display frozen screenshot as canvas background
        self._bg_photo = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, image=self._bg_photo, anchor=tk.NW)

        # Hint text
        self.canvas.create_text(
            self.sw // 2, self.sh // 2 - 60,
            text="Drag to select the element region\nPress ESC to cancel",
            fill="lime", font=("Microsoft YaHei", 14),
            justify=tk.CENTER,
        )

        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self._cancel())

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="lime", width=3,
        )

    def _on_drag(self, event):
        self.canvas.coords(
            self.rect_id, self.start_x, self.start_y, event.x, event.y,
        )

    def _on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        self.destroy()
        self.on_done(x1, y1, x2, y2)

    def _cancel(self):
        self.destroy()
        self.on_done(None, None, None, None)


class CaptureApp(tk.Tk):
    """Main control window."""

    def __init__(self):
        super().__init__()
        self.title("Template Capture")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.geometry("320x420")
        self.config(padx=10, pady=10)
        self._screenshot = None
        self._pending_template = None

        tk.Label(self, text="Template Capture Tool",
                 font=("Microsoft YaHei", 12, "bold")).pack(pady=(0, 5))
        tk.Label(
            self, text="1. Open element  2. Click Capture  3. Drag select",
            font=("Microsoft YaHei", 8), fg="gray50",
        ).pack(pady=(0, 10))

        buttons_frame = tk.Frame(self)
        buttons_frame.pack(fill=tk.X, pady=5)
        for name in TEMPLATES:
            row = tk.Frame(buttons_frame)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=name, width=18, anchor="w",
                     font=("Consolas", 9)).pack(side=tk.LEFT)
            btn = tk.Button(
                row, text="Capture", width=10,
                command=lambda n=name: self._start_capture(n),
            )
            btn.pack(side=tk.RIGHT)

        tk.Label(self, text="Preview:", font=("Microsoft YaHei", 9)).pack(
            anchor="w", pady=(15, 0))
        self.preview = tk.Label(self, text="(no capture yet)",
                                relief=tk.SUNKEN, bg="gray20", fg="gray60",
                                width=38, height=8)
        self.preview.pack(pady=5)
        tk.Button(self, text="Close", width=15,
                  command=self.destroy).pack(pady=(10, 0))

    def _start_capture(self, template_name: str):
        import pyautogui
        self._screenshot = pyautogui.screenshot()
        self._pending_template = template_name
        self.withdraw()
        self.update_idletasks()
        RegionSelector(self._screenshot, lambda x1, y1, x2, y2:
                       self._on_capture(x1, y1, x2, y2))

    def _on_capture(self, x1, y1, x2, y2):
        self.deiconify()
        self.lift()
        self.focus_force()
        if x1 is None or self._screenshot is None:
            self._screenshot = None
            return
        w, h = x2 - x1, y2 - y1
        if w < 5 or h < 5:
            self._screenshot = None
            return
        img = self._screenshot.crop((x1, y1, x2, y2))
        self._screenshot = None
        save_path = TEMPLATES_DIR / self._pending_template
        img.save(str(save_path))
        print(f"Saved: {save_path} ({img.width}x{img.height})")
        preview_img = img.copy()
        preview_img.thumbnail((280, 120))
        self._photo = ImageTk.PhotoImage(preview_img)
        self.preview.config(image=self._photo, text="")


def main():
    app = CaptureApp()
    app.mainloop()


if __name__ == "__main__":
    main()
