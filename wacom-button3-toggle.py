#!/usr/bin/env python3
# Wacom stylus upper barrel button (BTN_STYLUS2, xsetwacom "Button 3") drives two
# independent tool families based on press duration: short press = pen/eraser,
# long press = highlight/laser. Switching families (e.g. short after a long)
# resumes whichever tool that family was last on; alternating within a family
# (p<->e or h<->l) only happens on consecutive presses of the same length.
# xsetwacom can't do stateful or duration-based bindings, so this reads the raw
# evdev press/release events directly and sends the keystroke via xdotool.
# xsetwacom Button 3 must stay disabled (set to 0) so the tablet driver doesn't
# also fire its own right-click on the same press.
import os
import subprocess
import time

import evdev

DEVICE_GLOB_NAME = "usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse"
BY_ID_PATH = f"/dev/input/by-id/{DEVICE_GLOB_NAME}"

SHORT_CYCLE = ["p", "e"]  # pen, eraser
LONG_CYCLE = ["h", "l"]  # highlight, laser
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
        if event.type != evdev.ecodes.EV_KEY or event.code != evdev.ecodes.BTN_STYLUS2:
            continue
        if event.value == 1:  # press
            press_time = event.timestamp()
        elif event.value == 0 and press_time is not None:  # release
            duration = event.timestamp() - press_time
            press_time = None
            label = "short" if duration < LONG_PRESS_THRESHOLD_S else "long"
            cycle = SHORT_CYCLE if label == "short" else LONG_CYCLE

            if state["last_family"] == label:
                # Same family as the previous press: alternate within it.
                state[label] = (state[label] + 1) % len(cycle)
            # else: switching families - resume this family's current tool
            # (its index is untouched since the last time it was used).

            key = cycle[state[label]]
            send_key(key)
            print(
                f"{time.strftime('%FT%T')} Button 3 {label} press ({duration:.2f}s) -> sent '{key}'",
                flush=True,
            )
            state["last_family"] = label


def main():
    state = {"short": 0, "long": 0, "last_family": None}
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
