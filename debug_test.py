"""Debug test: single round with Chinese text."""
import logging
from pathlib import Path
from src.ui_automator import UIAutomator
from src.config import load_config

logging.basicConfig(level=logging.DEBUG)

debug_dir = Path("results/debug")
debug_dir.mkdir(parents=True, exist_ok=True)

config = load_config()
auto = UIAutomator(config, debug_dir)

print("Opening chat window...")
auto.ensure_app_ready()

print("\n=== Chinese text test ===")
resp = auto.ask_question("请帮我设计一个三天健康饮食计划，包括早中晚三餐，要详细具体", 1, reset_first=True)
print(f"Elapsed: {resp.elapsed_seconds:.1f}s, error: {resp.error or 'none'}")
print(f"Screenshot: {resp.screenshot_path}")
