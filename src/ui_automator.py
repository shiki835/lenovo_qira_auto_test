"""UI automation layer using image template matching.

Flow:
  float_button → (3s) → chat_menu → (3s) → chat window
  → send_button (anchor) → type → send → wait → screenshot
"""

import time
import logging
from pathlib import Path
from dataclasses import dataclass

import pyautogui
from pyscreeze import Box
from PIL import Image

from .config import Config

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.2

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@dataclass
class Response:
    text: str
    screenshot_path: str
    elapsed_seconds: float
    error: str = ""


class UIAutomator:

    def __init__(self, config: Config, results_dir: Path):
        self.config = config
        self.results_dir = results_dir
        self.screenshots_dir = results_dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.confidence = self.config.ui.template_confidence

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_app_ready(self) -> bool:
        """Navigate: float_button → chat_menu → chat window."""
        if self._find("send_button.png"):
            logger.info("Chat window already open")
            return True

        if not self._click_template("float_button.png", timeout=5, label="float button"):
            raise RuntimeError("Cannot find float button. Is Lenovo Qira running?")
        logger.info("Float button clicked, waiting 3s...")
        time.sleep(3)

        if not self._click_template("chat_menu.png", timeout=3, label="chat menu"):
            raise RuntimeError("Chat menu item not found. Update templates/chat_menu.png")
        logger.info("Chat menu clicked, waiting 3s...")
        time.sleep(3)

        if not self._wait_for("send_button.png", timeout=10):
            pyautogui.screenshot(str(self.screenshots_dir / "debug_no_send_button.png"))
            raise RuntimeError("Chat window did not appear. Debug screenshot saved.")

        logger.info("Chat window ready")
        return True

    def reset_chat(self):
        """Click the reset button (top-left of chat window) to clear history."""
        if self._click_template("reset_chat.png", timeout=3, label="reset chat"):
            time.sleep(1)
            logger.info("Chat reset")

    def ask_question(self, question: str, index: int, reset_first: bool = False) -> Response:
        """Send a question, wait for response, take scroll-stitch screenshot."""
        out = str(self.screenshots_dir / f"q{index:04d}")
        poll_interval = self.config.execution.poll_interval

        send_btn = self._find("send_button.png")
        if send_btn is None:
            self.ensure_app_ready()
            send_btn = self._find("send_button.png")
            if send_btn is None:
                return Response("", "", 0, "SEND_BUTTON_NOT_FOUND")

        if reset_first:
            self.reset_chat()
            time.sleep(0.5)
            send_btn = self._find("send_button.png")
            if send_btn is None:
                return Response("", "", 0, "SEND_BUTTON_NOT_FOUND")

        # Type and send
        self._focus_and_type(question, send_btn)
        pyautogui.press("enter")
        time.sleep(0.5)
        if self._find("send_button.png"):
            pyautogui.click(pyautogui.center(send_btn))

        # Wait for response: after sending, button stays visible briefly
        # Wait 3s minimum then poll for send_button (it may have moved/returned)
        start = time.time()
        time.sleep(3)
        send_after = self._wait_for("send_button.png",
                                    timeout=self.config.execution.response_timeout - 3,
                                    interval=poll_interval)
        elapsed = time.time() - start

        if send_after is None:
            try:
                pyautogui.screenshot(out + "_timeout.png")
            except Exception:
                pass
            self.reset_chat()
            return Response("", out + "_timeout.png", elapsed, "TIMEOUT")

        # Screenshot the conversation
        after_path = out + "_after.png"
        try:
            self._screenshot_conversation(after_path)
        except Exception:
            pyautogui.screenshot(after_path)

        return Response("", after_path, elapsed)

    def _screenshot_conversation(self, save_path: str):
        """Capture the full conversation window (scroll+stitch if needed)."""
        reset_btn = self._find("reset_chat.png")
        send_btn = self._find("send_button.png")
        if reset_btn is not None and send_btn is not None:
            self._capture_full_response(reset_btn, send_btn, save_path)
        else:
            pyautogui.screenshot(save_path)

    def restart_app(self):
        import subprocess
        proc = self.config.app.process_name
        launch = self.config.app.launch_path
        try:
            subprocess.run(["taskkill", "/F", "/IM", proc],
                           capture_output=True, timeout=10)
        except Exception:
            pass
        time.sleep(2)
        if launch:
            subprocess.Popen([launch], shell=True)
            time.sleep(5)

    def has_reset(self) -> bool:
        """Check if reset button is visible (chat window is open with content)."""
        return self._find("reset_chat.png") is not None

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _focus_and_type(self, text: str, send_btn: Box):
        import pyperclip

        send_cx, send_cy = pyautogui.center(send_btn)
        input_x = max(10, send_btn.left - 150)
        pyautogui.click(input_x, send_cy)
        time.sleep(0.3)
        # Clear existing text
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("backspace")
        time.sleep(0.1)

        # Use clipboard for all text (required for Chinese, works for English too)
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)

    # ------------------------------------------------------------------
    # Template matching
    # ------------------------------------------------------------------

    def _find(self, template_name: str, confidence: float | None = None) -> Box | None:
        import cv2
        import numpy as np

        path = TEMPLATES_DIR / template_name
        if not path.exists():
            return None

        cf = confidence or self.confidence
        needle = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if needle is None:
            return None

        screen = pyautogui.screenshot()
        haystack = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)

        h, w = needle.shape[:2]
        if haystack.shape[0] < h or haystack.shape[1] < w:
            return None

        if needle.shape[2] == 4:
            alpha = needle[:, :, 3]
            needle_rgb = needle[:, :, :3]
            if np.any(alpha != 255):
                result = cv2.matchTemplate(haystack, needle_rgb, cv2.TM_CCOEFF_NORMED, mask=alpha)
            else:
                result = cv2.matchTemplate(haystack, needle_rgb, cv2.TM_CCOEFF_NORMED)
        else:
            result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)

        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= cf:
            return Box(max_loc[0], max_loc[1], w, h)
        return None

    def _wait_for(self, template_name: str, timeout: float, interval: float = 0.5) -> Box | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self._find(template_name)
            if result is not None:
                return result
            time.sleep(interval)
        return None

    def _click_template(self, template_name: str, timeout: float, label: str = "") -> bool:
        box = self._find(template_name)
        if box is None:
            box = self._wait_for(template_name, timeout=timeout)
        if box is None:
            return False
        cx, cy = pyautogui.center(box)
        pyautogui.click(cx, cy)
        logger.debug(f"Clicked {label or template_name} at ({cx}, {cy})")
        return True

    def _capture_full_response(self, reset_btn: Box, send_btn: Box, save_path: str) -> str:
        """Capture the full chat response, scrolling and stitching if needed.

        Scrolls to top, then takes screenshots while paging down.
        Stitches all pages into one tall image.
        """
        import numpy as np

        # Content area: between reset button and send button
        content_left = reset_btn.left + 4
        content_top = reset_btn.top + reset_btn.height + 4
        content_right = send_btn.left + send_btn.width - 4
        content_bottom = send_btn.top - 4
        content_w = content_right - content_left
        content_h = content_bottom - content_top
        logger.debug(f"_capture_full_response: reset=({reset_btn.left},{reset_btn.top}) "
                     f"send=({send_btn.left},{send_btn.top}) "
                     f"content=({content_left},{content_top},{content_right},{content_bottom}) "
                     f"w={content_w} h={content_h}")

        # If content area is too small, capture the entire window instead
        if content_w <= 0 or content_h <= 20:
            logger.warning(f"Content area too small (w={content_w}, h={content_h}), capturing full window")
            win_w = send_btn.left + send_btn.width - reset_btn.left
            win_h = send_btn.top + send_btn.height - reset_btn.top
            if win_w > 0 and win_h > 0:
                img = pyautogui.screenshot(
                    region=(reset_btn.left, reset_btn.top, win_w, win_h))
                img.save(save_path)
                return save_path
            pyautogui.screenshot(save_path)
            return save_path

        # Click content area and scroll to very top
        mid_x = (content_left + content_right) // 2
        mid_y = (content_top + content_bottom) // 2
        pyautogui.click(mid_x, mid_y)
        time.sleep(0.2)
        for _ in range(20):
            pyautogui.scroll(500)
            time.sleep(0.02)

        max_pages = 10
        pages = []
        prev_img = None

        for page in range(max_pages):
            if content_w <= 0 or content_h <= 0:
                break

            img = pyautogui.screenshot(
                region=(content_left, content_top, content_w, content_h))

            if prev_img is not None:
                arr_new = np.array(img)
                arr_old = np.array(prev_img)
                diff = np.mean(arr_new != arr_old)
                if diff < 0.008:
                    break

            pages.append(img)
            prev_img = img

            pyautogui.press("pagedown")
            time.sleep(0.3)

        if not pages:
            pyautogui.screenshot(save_path)
            return save_path

        if len(pages) == 1:
            pages[0].save(save_path)
            return save_path

        total_height = sum(p.height for p in pages)
        max_width = max(p.width for p in pages)
        stitched = Image.new("RGB", (max_width, total_height))
        y_offset = 0
        for p in pages:
            stitched.paste(p, (0, y_offset))
            y_offset += p.height

        stitched.save(save_path)
        return save_path
