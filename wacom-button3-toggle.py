#!/usr/bin/env python3
# Wacom stylus lower barrel button (BTN_STYLUS, xsetwacom "Button 2") drives a
# 2x2 grid of tools: TYPE (pen-family vs highlight-family) x CLASS (normal vs
# eraser-analog). Short press flips CLASS only (p<->e, h<->l) regardless of
# which type is active. Long press flips TYPE only (p<->h, e<->l), keeping
# the current class. So e.g. from "p": short -> e, long -> h; from "h":
# short -> l, long -> p.
# xsetwacom can't do stateful or duration-based bindings, so this reads the raw
# evdev press/release events directly and sends the keystroke via xdotool.
# xsetwacom Button 2 must stay disabled (set to 0) so the tablet driver doesn't
# also fire its own click on the same press. Button 3 (upper barrel) now holds
# pan instead - swapped from the original layout because the lower barrel
# button is easier to reach for tool switching.
import os
import subprocess
import time

import evdev

DEVICE_GLOB_NAME = "usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse"
BY_ID_PATH = f"/dev/input/by-id/{DEVICE_GLOB_NAME}"

# (type, class) -> key. type 0 = pen-family, 1 = highlight-family.
# class 0 = normal (p/h), 1 = alt (e/l).
TOOL_GRID = {
    (0, 0): "p",
    (0, 1): "e",
    (1, 0): "h",
    (1, 1): "l",
}
LONG_PRESS_THRESHOLD_S = 0.35


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


def watch(path, state):
    dev = evdev.InputDevice(path)
    press_time = None
    for event in dev.read_loop():
        if event.type != evdev.ecodes.EV_KEY or event.code != evdev.ecodes.BTN_STYLUS:
            continue
        if event.value == 1:  # press
            press_time = event.timestamp()
        elif event.value == 0 and press_time is not None:  # release
            duration = event.timestamp() - press_time
            press_time = None
            label = "short" if duration < LONG_PRESS_THRESHOLD_S else "long"

            if label == "short":
                state["class"] ^= 1
            else:
                state["type"] ^= 1

            key = TOOL_GRID[(state["type"], state["class"])]
            send_key(key)
            print(
                f"{time.strftime('%FT%T')} Button 2 {label} press ({duration:.2f}s) -> sent '{key}'",
                flush=True,
            )


def main():
    state = {"type": 0, "class": 0}
    while True:
        path = find_device_path()
        if path is None:
            time.sleep(2)
            continue
        try:
            watch(path, state)
        except (OSError, evdev.uinput.UInputError):
            time.sleep(2)


if __name__ == "__main__":
    main()
