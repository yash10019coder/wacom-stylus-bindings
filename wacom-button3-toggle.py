#!/usr/bin/env python3
# Wacom stylus: both barrel buttons now carry tool-switching, split so no
# single button is overloaded.
#
# Button 2 (BTN_STYLUS, lower barrel) - eraser toggle: every press flips
# between the current writer tool (pencil `p` or highlighter `h`) and the
# shared eraser `e`. No-op while the laser is selected - erasing a laser
# pointer doesn't mean anything.
#
# Button 3 (BTN_STYLUS2, upper barrel) - dual purpose, kept working
# alongside xsetwacom's native `pan` binding:
#   - hold + drag -> pan/scroll (handled natively by xsetwacom, untouched).
#   - quick tap (press+release under LONG_PRESS_THRESHOLD_S, no meaningful
#     drag) -> cycle the tool CATEGORY: pencil -> highlighter -> laser ->
#     pencil ... Each writer category (pencil/highlighter) remembers its own
#     eraser state across category switches.
#
# xsetwacom can't do stateful or duration-based bindings, so this reads the
# raw evdev press/release events directly and sends the keystroke via
# xdotool. xsetwacom Button 2 must stay disabled (set to 0) so the tablet
# driver doesn't also fire its own click on the same press. Button 3 is left
# bound to `pan` in xsetwacom - this daemon only listens alongside it to
# detect taps, it doesn't disable or replace the native pan behavior.
import os
import subprocess
import time

import evdev

DEVICE_GLOB_NAME = "usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse"
BY_ID_PATH = f"/dev/input/by-id/{DEVICE_GLOB_NAME}"

# Category order for Button 3 taps. "pencil" and "highlighter" are writer
# categories (each has its own eraser toggle via Button 2); "laser" has no
# eraser pair.
CATEGORIES = ["pencil", "highlighter", "laser"]
WRITER_KEYS = {"pencil": "p", "highlighter": "h"}
LONG_PRESS_THRESHOLD_S = 0.35


def key_for_state(state):
    cat = CATEGORIES[state["cat_idx"]]
    if cat == "laser":
        return "l"
    return "e" if state["erase"][cat] else WRITER_KEYS[cat]


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
    press_times = {}
    for event in dev.read_loop():
        if event.type != evdev.ecodes.EV_KEY:
            continue
        if event.code not in (evdev.ecodes.BTN_STYLUS, evdev.ecodes.BTN_STYLUS2):
            continue

        if event.value == 1:  # press
            press_times[event.code] = event.timestamp()
            continue
        if event.value != 0 or event.code not in press_times:  # release, unmatched
            continue

        duration = event.timestamp() - press_times.pop(event.code)

        if event.code == evdev.ecodes.BTN_STYLUS:
            cat = CATEGORIES[state["cat_idx"]]
            if cat == "laser":
                print(
                    f"{time.strftime('%FT%T')} Button 2 press ({duration:.2f}s) -> ignored (laser has no eraser)",
                    flush=True,
                )
                continue
            state["erase"][cat] ^= True
            key = key_for_state(state)
            send_key(key)
            print(
                f"{time.strftime('%FT%T')} Button 2 press ({duration:.2f}s) -> sent '{key}'",
                flush=True,
            )
        else:  # BTN_STYLUS2
            if duration >= LONG_PRESS_THRESHOLD_S:
                # Hold+drag: xsetwacom's native `pan` binding already handled it.
                continue
            state["cat_idx"] = (state["cat_idx"] + 1) % len(CATEGORIES)
            key = key_for_state(state)
            send_key(key)
            print(
                f"{time.strftime('%FT%T')} Button 3 tap ({duration:.2f}s) -> "
                f"category '{CATEGORIES[state['cat_idx']]}', sent '{key}'",
                flush=True,
            )


def main():
    state = {"cat_idx": 0, "erase": {"pencil": False, "highlighter": False}}
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
