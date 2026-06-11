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
TEMPLATE_CONFIDENCE_FLOORS = {
    "send_button.png": 0.85,
    "send_button_purple.png": 0.85,
}


def _read_image(path: Path):
    """Read an image from a Windows path that may contain non-ASCII characters."""
    import cv2
    import numpy as np

    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


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
        if self._chat_window_open():
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

        if not self._wait_for_chat_window(timeout=10):
            pyautogui.screenshot(str(self.screenshots_dir / "debug_no_send_button.png"))
            raise RuntimeError("Chat window did not appear. Debug screenshot saved.")

        logger.info("Chat window ready")
        return True

    def reset_chat(self):
        """Click the new-chat/reset button when it is available."""
        if self.start_new_chat():
            logger.info("Chat reset")

    def ask_question(self, question: str, index: int, reset_first: bool = False) -> Response:
        """Send a question, wait for response, take scroll-stitch screenshot."""
        out = str(self.screenshots_dir / f"q{index:04d}")
        poll_interval = self.config.execution.poll_interval

        if not self._chat_window_open():
            self.ensure_app_ready()
        send_btn = self._find_chat_send_button()
        if send_btn is None:
            return Response("", "", 0, "SEND_BUTTON_NOT_FOUND")

        if reset_first:
            self.reset_chat()
            time.sleep(0.5)
            send_btn = self._find_chat_send_button()
            if send_btn is None:
                return Response("", "", 0, "SEND_BUTTON_NOT_FOUND")

        # Type and send. Enter inserts a newline in Qira, so click the active send button.
        # Verify that the click submitted the input; if Qira ignores the click, retry it.
        self._focus_and_type(question, send_btn)
        if not self._click_send_until_submitted(send_btn):
            fail_path = out + "_send_click_failed.png"
            try:
                pyautogui.screenshot(fail_path)
            except Exception:
                fail_path = ""
            return Response("", fail_path, 0, "SEND_CLICK_FAILED")

        # Wait for response: after sending, button stays visible briefly
        # Wait 3s minimum then poll for send_button (it may have moved/returned)
        start = time.time()
        time.sleep(3)

        self._click_template("confirm.png", timeout=8, label="oauth confirm")

        # Wait for response
        start = time.time()
        time.sleep(3)
        
        # 回答完成后，输入框重新变空，按钮又变回白色，这里继续用白按钮监听结束状态
        send_after = self._wait_for_inactive_chat_send_button(
            timeout=self.config.execution.response_timeout - 3,
            interval=poll_interval,
        )
        elapsed = time.time() - start

        if send_after is None:
            try:
                pyautogui.screenshot(out + "_timeout.png")
            except Exception:
                pass
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
        send_btn = self._find_chat_send_button(reset_btn)
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

    def start_new_chat(self) -> bool:
        """Open a fresh chat by clicking the top-left new-chat button."""
        if not self._chat_window_open():
            try:
                self.ensure_app_ready()
            except RuntimeError:
                pass

        new_btn = self._find("reset_chat.png") or self._wait_for("reset_chat.png", timeout=2)
        if new_btn is None:
            return False
        pyautogui.click(pyautogui.center(new_btn))
        time.sleep(1)
        return self._wait_for_chat_window(timeout=5)

    def reopen_current_chat(self) -> bool:
        """Refocus/reopen the current Qira chat without starting a new session."""
        float_btn = self._find("float_button.png")
        if float_btn is not None:
            pyautogui.click(pyautogui.center(float_btn))
            time.sleep(1)
        if self._chat_window_open():
            return True

        float_btn = self._find("float_button.png")
        if float_btn is not None:
            pyautogui.click(pyautogui.center(float_btn))
            time.sleep(1)
        if self._chat_window_open():
            return True

        try:
            return self.ensure_app_ready()
        except RuntimeError:
            return False

    def recover_after_failure(self, reset_first: bool) -> bool:
        if reset_first:
            return self.start_new_chat()
        return self.reopen_current_chat()

    def _chat_window_open(self) -> bool:
        return self._find_chat_send_button() is not None

    def _chat_search_region(self, reset_btn: Box) -> tuple[int, int, int, int]:
        left = max(0, reset_btn.left - 20)
        top = max(0, reset_btn.top - 20)
        screen_w, screen_h = pyautogui.size()
        width = min(screen_w - left, max(900, self.config.ui.chat_window_width + 900))
        height = min(screen_h - top, max(420, self.config.ui.chat_window_max_height + 260))
        return (left, top, width, height)

    def _button_search_region(self, button: Box) -> tuple[int, int, int, int]:
        screen_w, screen_h = pyautogui.size()
        left = max(0, button.left - 120)
        top = max(0, button.top - 80)
        width = min(screen_w - left, button.width + 240)
        height = min(screen_h - top, button.height + 160)
        return (left, top, width, height)

    def _find_chat_button(
        self,
        template_name: str,
        reset_btn: Box | None = None,
        anchor: Box | None = None,
        confidence: float | None = None,
    ) -> Box | None:
        regions = []
        if anchor is not None:
            regions.append(self._button_search_region(anchor))
        reset = reset_btn or self._find("reset_chat.png")
        if reset is not None:
            regions.append(self._chat_search_region(reset))

        for region in regions:
            found = self._find(template_name, confidence=confidence, region=region)
            if found is not None:
                return found
        return self._find(template_name, confidence=confidence)

    def _find_purple_send_button_by_color(
        self,
        anchor: Box | None = None,
        reset_btn: Box | None = None,
    ) -> Box | None:
        import cv2
        import numpy as np

        regions: list[tuple[int, int, int, int] | None] = []
        if anchor is not None:
            regions.append(self._button_search_region(anchor))
        reset = reset_btn or self._find("reset_chat.png")
        if reset is not None:
            regions.append(self._chat_search_region(reset))
        regions.append(None)

        best: tuple[float, Box] | None = None
        for region in regions:
            screen = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
            img = np.array(screen)  # RGB
            red = img[:, :, 0].astype(np.int16)
            green = img[:, :, 1].astype(np.int16)
            blue = img[:, :, 2].astype(np.int16)

            mask = (
                (red > 120)
                & (green > 70)
                & (green < 235)
                & (blue > 145)
                & ((blue - green) > 12)
                & ((red - green) > -35)
            ).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            offset_x = region[0] if region else 0
            offset_y = region[1] if region else 0
            img_h, img_w = img.shape[:2]
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 600:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                if not (35 <= w <= 130 and 35 <= h <= 130):
                    continue
                ratio = w / max(h, 1)
                if not (0.65 <= ratio <= 1.55):
                    continue

                cx = offset_x + x + w / 2
                cy = offset_y + y + h / 2
                # Prefer large, right-side circular purple controls. This filters out text/highlights.
                score = area + (cx / max(pyautogui.size().width, 1)) * 300
                box = Box(offset_x + x, offset_y + y, w, h)
                if best is None or score > best[0]:
                    best = (score, box)

            if best is not None and region is not None:
                return best[1]

        return best[1] if best is not None else None

    def _find_active_send_arrow_template(self, anchor: Box | None = None) -> Box | None:
        return self._find_chat_button("send_button_purple.png", anchor=anchor, confidence=0.62)

    def _find_active_send_button(self, anchor: Box | None = None) -> Box | None:
        return (
            self._find_purple_send_button_by_color(anchor=anchor)
            or self._find_active_send_arrow_template(anchor=anchor)
        )

    def _find_inactive_send_button(self, anchor: Box | None = None) -> Box | None:
        return self._find_chat_button("send_button.png", anchor=anchor)

    def _find_chat_send_button(self, reset_btn: Box | None = None) -> Box | None:
        reset = reset_btn or self._find("reset_chat.png")
        return (
            self._find_chat_button("send_button.png", reset_btn=reset)
            or self._find_purple_send_button_by_color(reset_btn=reset)
            or self._find_chat_button("send_button_purple.png", reset_btn=reset)
        )

    def _wait_for_chat_window(self, timeout: float, interval: float = 0.5) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._chat_window_open():
                return True
            time.sleep(interval)
        return False

    def _wait_for_chat_send_button(self, timeout: float, interval: float = 0.5) -> Box | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self._find_chat_send_button()
            if result is not None:
                return result
            time.sleep(interval)
        return None

    def _wait_for_active_send_button(
        self,
        anchor: Box | None = None,
        timeout: float = 2,
        interval: float = 0.2,
    ) -> Box | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self._find_active_send_button(anchor)
            if result is not None:
                return result
            time.sleep(interval)
        return None

    def _wait_for_inactive_chat_send_button(
        self,
        anchor: Box | None = None,
        timeout: float = 2,
        interval: float = 0.2,
    ) -> Box | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self._find_inactive_send_button(anchor)
            if result is not None:
                return result
            time.sleep(interval)
        return None

    def _click_send_until_submitted(self, send_btn: Box, attempts: int = 4) -> bool:
        active = self._wait_for_active_send_button(
            anchor=send_btn,
            timeout=2,
            interval=0.15,
        )
        target = active or send_btn
        is_active_target = active is not None or target.height < 40
        cx, cy = self._send_button_click_point(target, active=is_active_target)
        pyautogui.click(cx, cy)
        logger.debug(
            "Clicked send button at (%s, %s), box=(%s,%s,%s,%s)",
            cx,
            cy,
            target.left,
            target.top,
            target.width,
            target.height,
        )
        time.sleep(0.8)

        inactive = self._wait_for_inactive_chat_send_button(
            anchor=target,
            timeout=1,
            interval=0.15,
        )
        if inactive is not None:
            return True

        # During generation Qira can replace send with a purple stop button.
        # Do not click any purple control after the first submit click; it may stop output.
        logger.debug("No inactive send button after click; assuming Qira is generating")
        return True

    def _send_button_click_point(self, button: Box, active: bool = False) -> tuple[int, int]:
        cx = button.left + button.width // 2
        if active and button.height < 40:
            # The purple template can match only the upper/icon part of the full round button.
            # Click lower than the template box so the actual click lands near the circle center.
            cy = button.top + max(button.height // 2, 38)
        else:
            cy = button.top + button.height // 2
        return cx, cy

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _focus_and_type(self, text: str, send_btn: Box):
        import pyperclip

        send_cx, send_cy = pyautogui.center(send_btn)
        input_offset = max(260, min(500, self.config.ui.chat_window_width - 80))
        input_x = max(10, send_btn.left - input_offset)
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

    def _find(
        self,
        template_name: str,
        confidence: float | None = None,
        region: tuple[int, int, int, int] | None = None,
    ) -> Box | None:
        import cv2
        import numpy as np

        path = TEMPLATES_DIR / template_name
        if not path.exists():
            return None

        cf = confidence or max(self.confidence, TEMPLATE_CONFIDENCE_FLOORS.get(template_name, 0))
        needle = _read_image(path)
        if needle is None:
            return None

        screen = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
        haystack = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)

        h, w = needle.shape[:2]
        if haystack.shape[0] < h or haystack.shape[1] < w:
            return None

        if len(needle.shape) == 2:
            haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(haystack_gray, needle, cv2.TM_CCOEFF_NORMED)
        elif needle.shape[2] == 4:
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
            offset_x = region[0] if region else 0
            offset_y = region[1] if region else 0
            return Box(max_loc[0] + offset_x, max_loc[1] + offset_y, w, h)
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
