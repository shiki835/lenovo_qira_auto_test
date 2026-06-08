"""Coordinate capture tool — helps identify UI element positions.

Usage:
    python capture_coords.py

Instructions:
    1. Make sure Lenovo Qira window is visible (not minimized)
    2. Hover mouse over each position and press Enter to capture:
       - Top-left corner of response area
       - Bottom-right corner of response area
       - Top-left corner of input box
       - Bottom-right corner of input box
       - Send button center
    3. Copy the printed config into config.yaml
"""

import pyautogui

print("=" * 60)
print("Coordinate Capture Tool for Lenovo Qira")
print("=" * 60)
print()
print("Make sure the Lenovo Qira window is fully visible.")
print("For each prompt, move your mouse to the position and press Enter.")
print()

coords = {}

# 1. Response area top-left
input("1. Move mouse to TOP-LEFT of RESPONSE AREA, press Enter...")
pos = pyautogui.position()
coords["response_tl"] = (pos.x, pos.y)
print(f"   Captured: ({pos.x}, {pos.y})")

# 2. Response area bottom-right
input("2. Move mouse to BOTTOM-RIGHT of RESPONSE AREA, press Enter...")
pos = pyautogui.position()
coords["response_br"] = (pos.x, pos.y)
print(f"   Captured: ({pos.x}, {pos.y})")

# 3. Input area top-left
input("3. Move mouse to TOP-LEFT of INPUT BOX, press Enter...")
pos = pyautogui.position()
coords["input_tl"] = (pos.x, pos.y)
print(f"   Captured: ({pos.x}, {pos.y})")

# 4. Input area bottom-right
input("4. Move mouse to BOTTOM-RIGHT of INPUT BOX, press Enter...")
pos = pyautogui.position()
coords["input_br"] = (pos.x, pos.y)
print(f"   Captured: ({pos.x}, {pos.y})")

# 5. Send button
input("5. Move mouse to SEND BUTTON, press Enter...")
pos = pyautogui.position()
coords["send_btn"] = (pos.x, pos.y)
print(f"   Captured: ({pos.x}, {pos.y})")

print()
print("=" * 60)
print("Copy this into config.yaml:")
print("=" * 60)
print(f"""
ui:
  response_region: [{coords['response_tl'][0]}, {coords['response_tl'][1]}, {coords['response_br'][0]}, {coords['response_br'][1]}]
  input_region: [{coords['input_tl'][0]}, {coords['input_tl'][1]}, {coords['input_br'][0]}, {coords['input_br'][1]}]
  send_button: [{coords['send_btn'][0]}, {coords['send_btn'][1]}]
""")
