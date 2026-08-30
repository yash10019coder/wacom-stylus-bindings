#!/usr/bin/env python3
# Cycles the Wacom stylus upper barrel button (BTN_STYLUS2, xsetwacom "Button 3")
# through KEY_CYCLE on each press. xsetwacom itself can't do stateful
# cycling, so this reads the raw evdev button events directly and sends the
# keystroke via xdotool. xsetwacom Button 3 must stay disabled (set to 0) so the
# tablet driver doesn't also fire its own right-click on the same press.
import os
import subprocess
import time

import evdev

DEVICE_GLOB_NAME = "usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse"
BY_ID_PATH = f"/dev/input/by-id/{DEVICE_GLOB_NAME}"

KEY_CYCLE = ["e", "p", "h", "l"]  # eraser, pen, highlight, laser


def find_device_path():
    if os.path.exists(BY_ID_PATH):
        return os.path.realpath(BY_ID_PATH)
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if dev.name == "Wacom One by Wacom M Pen":
            return path
    return None


def send_key(key):
    os.environ.setdefault("DISPLAY", ":1")
    os.environ.setdefault("XAUTHORITY", "/run/user/1000/gdm/Xauthority")
    subprocess.run(["xdotool", "key", key], check=False)


def watch(path, index):
    dev = evdev.InputDevice(path)
    for event in dev.read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_STYLUS2:
            if event.value == 1:  # press only, ignore release
                key = KEY_CYCLE[index[0]]
                send_key(key)
                print(f"{time.strftime('%FT%T')} Button 3 pressed -> sent '{key}'", flush=True)
                index[0] = (index[0] + 1) % len(KEY_CYCLE)


def main():
    index = [0]
    while True:
        path = find_device_path()
        if path is None:
            time.sleep(2)
            continue
        try:
            watch(path, index)
        except (OSError, evdev.uinput.UInputError):
            time.sleep(2)


if __name__ == "__main__":
    main()
