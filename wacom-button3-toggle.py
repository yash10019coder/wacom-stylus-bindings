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
# alongside xsetwacom's native `pan` binding. Classified as pan if EITHER
# of two things happened during the button hold, else it's a tap:
#   - the pen tip touched the tablet (BTN_TOUCH) at any point during the
#     hold - not just at the press instant, since the real gesture is
#     button down FIRST, then touch down/drag/up, then button up; or
#   - the cursor position (ABS_X/ABS_Y) moved past MOVE_THRESHOLD_UNITS
#     during the hold - this tablet also supports panning purely by
#     hovering and dragging without ever touching down, which touch state
#     alone can't see.
#   A tap -> cycle the tool CATEGORY: pencil -> highlighter -> laser ->
#   pencil ... Each writer category (pencil/highlighter) remembers its own
#   eraser state across category switches.
#
#   While Button 3 is HELD, tapping the pen tip on the tablet surface 3
#   times in quick succession (3 distinct BTN_TOUCH down/up pulses, each
#   short and with minimal movement - not a drag) instead screenshots the
#   secondary monitor to SCREENSHOT_DIR, copies it to the clipboard, and
#   pastes it (Ctrl+V) into whatever has focus. This fires as soon as the
#   3rd tap-up happens, without waiting for Button 3 to be released, and
#   suppresses the pan/tap classification for that Button 3 press. A single
#   continuous touch-drag (real panning) never produces 3 discrete pulses,
#   so it's not confused with this gesture.
#   Duration alone was tried first and proved unreliable - a fast short
#   pan looks just like a tap by duration. Touch-only was tried next and
#   missed hover-pans (see git history for both).
#
#   One more wrinkle: a single continuous pan gesture is actually chopped
#   by the driver into repeated short stroke segments, each with its own
#   BTN_STYLUS2 up/down - there's a real button release+re-press between
#   strokes, mid-pan. In that gap (tens of ms) the pen genuinely is
#   hovering for a moment before the next stroke's touch-down, so a press
#   starting there looks identical to a real hover tap - it can't be
#   resolved from state alone. PAN_DEBOUNCE_S papers over this: any press
#   starting soon after a press we just classified as pan is treated as a
#   continuation of that same pan, not evaluated fresh.
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

# Secondary monitor geometry for triple-tap screenshots (xrandr WxH+X+Y).
SCREENSHOT_MONITOR_GEOMETRY = "1920x1080+0+0"
SCREENSHOT_DIR = os.path.expanduser("~/Pictures/wacom-screenshots")
# A pen-tip touch counts as a "tap pulse" (not a drag) if it lasts no
# longer than this and moves no more than TAP_TOUCH_MAX_MOVE_UNITS.
TAP_TOUCH_MAX_DURATION_S = 0.3
TAP_TOUCH_MAX_MOVE_UNITS = 100
# 3 tap pulses while Button 3 is held count as a triple-tap if the first
# and last are within this long of each other.
TRIPLE_TOUCH_WINDOW_S = 0.6

# Category order for Button 3 taps. "pencil" and "highlighter" are writer
# categories (each has its own eraser toggle via Button 2); "laser" has no
# eraser pair.
CATEGORIES = ["pencil", "highlighter", "laser"]
WRITER_KEYS = {"pencil": "p", "highlighter": "h"}
# A Button 3 press starting within this long of the previous press being
# classified as pan is treated as a continuation of that same pan gesture.
PAN_DEBOUNCE_S = 0.2
# Tablet reports ABS_X/ABS_Y in device units at 100 units/mm (21600x13500
# range), not screen pixels - 300 units is ~3mm of stylus movement.
MOVE_THRESHOLD_UNITS = 300


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


def screenshot_and_paste():
    os.environ.setdefault("DISPLAY", ":1")
    os.environ.setdefault("XAUTHORITY", "/run/user/1000/gdm/Xauthority")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    filename = time.strftime("screenshot-%Y-%m-%dT%H-%M-%S.png")
    path = os.path.join(SCREENSHOT_DIR, filename)
    subprocess.run(
        ["import", "-window", "root", "-crop", SCREENSHOT_MONITOR_GEOMETRY, path],
        check=False,
    )
    with open(path, "rb") as f:
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png"],
            stdin=f,
            check=False,
        )
    subprocess.run(["xdotool", "key", "ctrl+v"], check=False)
    return path


def watch(path, state):
    dev = evdev.InputDevice(path)
    press_times = {}
    stylus2_held = False
    stylus2_touched = False
    stylus2_press_ts = None
    stylus2_start_pos = {}
    stylus2_move_units = 0.0
    last_pan_end_ts = None
    last_abs_pos = {evdev.ecodes.ABS_X: None, evdev.ecodes.ABS_Y: None}
    touch_down_ts = None
    touch_down_pos = {}
    touch_move_units = 0.0
    tap_pulses = []  # timestamps of recent short taps while Button 3 held
    triple_touch_fired = False
    for event in dev.read_loop():
        if event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
            if event.value == 1:
                if stylus2_held:
                    stylus2_touched = True
                    touch_down_ts = event.timestamp()
                    touch_down_pos = dict(last_abs_pos)
                    touch_move_units = 0.0
            elif stylus2_held and touch_down_ts is not None:
                touch_duration = event.timestamp() - touch_down_ts
                touch_down_ts = None
                if (
                    touch_duration <= TAP_TOUCH_MAX_DURATION_S
                    and touch_move_units <= TAP_TOUCH_MAX_MOVE_UNITS
                ):
                    tap_pulses.append(event.timestamp())
                    tap_pulses[:] = tap_pulses[-3:]
                    if (
                        len(tap_pulses) == 3
                        and tap_pulses[-1] - tap_pulses[0] <= TRIPLE_TOUCH_WINDOW_S
                    ):
                        tap_pulses.clear()
                        triple_touch_fired = True
                        shot_path = screenshot_and_paste()
                        print(
                            f"{time.strftime('%FT%T')} Button 3 held, triple tap-touch "
                            f"-> screenshot saved and pasted from {shot_path}",
                            flush=True,
                        )
                else:
                    tap_pulses.clear()
            continue

        if event.type == evdev.ecodes.EV_ABS:
            if event.code in (evdev.ecodes.ABS_X, evdev.ecodes.ABS_Y):
                last_abs_pos[event.code] = event.value
                if stylus2_held:
                    start = stylus2_start_pos.get(event.code)
                    if start is None:
                        stylus2_start_pos[event.code] = event.value
                    else:
                        stylus2_move_units = max(
                            stylus2_move_units, abs(event.value - start)
                        )
                    if touch_down_ts is not None:
                        touch_start = touch_down_pos.get(event.code)
                        if touch_start is not None:
                            touch_move_units = max(
                                touch_move_units, abs(event.value - touch_start)
                            )
            continue

        if event.type != evdev.ecodes.EV_KEY:
            continue
        if event.code not in (evdev.ecodes.BTN_STYLUS, evdev.ecodes.BTN_STYLUS2):
            continue

        if event.value == 1:  # press
            press_ts = event.timestamp()
            press_times[event.code] = press_ts
            if event.code == evdev.ecodes.BTN_STYLUS2:
                stylus2_held = True
                stylus2_press_ts = press_ts
                stylus2_start_pos = {}
                stylus2_move_units = 0.0
                tap_pulses = []
                triple_touch_fired = False
                # A press landing right after a pan gets seeded as already
                # "touched" - it's the same pan continuing across a stroke
                # boundary, not a fresh hover tap.
                stylus2_touched = (
                    last_pan_end_ts is not None
                    and press_ts - last_pan_end_ts < PAN_DEBOUNCE_S
                )
            continue
        if event.value != 0 or event.code not in press_times:  # release, unmatched
            continue

        duration = event.timestamp() - press_times.pop(event.code)

        if event.code == evdev.ecodes.BTN_STYLUS2:
            stylus2_held = False
            if triple_touch_fired:
                print(
                    f"{time.strftime('%FT%T')} Button 3 press ({duration:.2f}s) "
                    f"-> already handled as triple-tap screenshot",
                    flush=True,
                )
                continue
            was_debounced = (
                last_pan_end_ts is not None
                and stylus2_press_ts - last_pan_end_ts < PAN_DEBOUNCE_S
            )
            moved = stylus2_move_units
            was_touching = stylus2_touched or moved >= MOVE_THRESHOLD_UNITS

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
            if was_touching:
                # Touched, moved past the threshold, or debounced as a
                # continuation of the previous pan: xsetwacom's native
                # `pan` binding already handled it.
                last_pan_end_ts = event.timestamp()
                if was_debounced:
                    reason = "debounced continuation"
                elif stylus2_touched:
                    reason = "touching"
                else:
                    reason = f"moved {moved:.0f}u"
                print(
                    f"{time.strftime('%FT%T')} Button 3 press ({duration:.2f}s, {reason}) "
                    f"-> treated as pan, ignored",
                    flush=True,
                )
                continue
            state["cat_idx"] = (state["cat_idx"] + 1) % len(CATEGORIES)
            key = key_for_state(state)
            send_key(key)
            print(
                f"{time.strftime('%FT%T')} Button 3 press ({duration:.2f}s, hovering, "
                f"moved {moved:.0f}u) -> category '{CATEGORIES[state['cat_idx']]}', sent '{key}'",
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
