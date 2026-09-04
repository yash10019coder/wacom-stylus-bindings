# Wacom One M — button bindings & persistence for GoodNotes Web

Built and tuned specifically for **[GoodNotes Web](https://www.goodnotes.com/)**
on Linux (Chrome/Chromium), where `p`/`e`/`h`/`l` are GoodNotes' own
keyboard shortcuts for Pen, Eraser, Highlighter, and Laser pointer. The
approach (raw evdev + `xdotool`) is not GoodNotes-specific and will send
these same keys to whatever app has focus, so it should adapt to any app
with keyboard shortcuts for its tools — just change `SHORT_CYCLE`/
`LONG_CYCLE` in `wacom-button3-toggle.py` to that app's shortcut keys.

Device: `Wacom One by Wacom M Pen stylus` (2 barrel buttons + tip).

Actual button layout on this device (confirmed via `xsetwacom --get`/`xinput`):
- **Button 1** = pen tip (draw/click) — never remapped.
- **Button 2** = lower barrel button (easier to reach) → disabled in
  xsetwacom (`0`); a daemon reads the raw press/release events instead.
  Every press toggles **eraser on/off** for whichever writer tool is
  currently selected (pencil `p` ↔ eraser `e`, or highlighter `h` ↔ eraser
  `e`). No-op while laser is selected — erasing a laser pointer doesn't mean
  anything.
- **Button 3** = upper barrel button → still bound to `pan` in xsetwacom
  (click+drag to pan/scroll, unchanged), **and** watched by the same daemon
  to classify each press as pan or tap: it's a pan if the pen touched the
  tablet at any point during the hold, or if the cursor moved past a small
  threshold (this tablet also supports hover-only panning); otherwise it's
  a tap, which cycles the tool **category** — pencil → highlighter → laser
  → pencil ... Each writer category remembers its own eraser state
  independently. **Holding Button 3 and tapping the pen tip on the tablet
  3 times** in quick succession instead takes a screenshot of the
  secondary monitor and pastes it into whatever has focus — see below —
  without cycling the category or panning.

Both buttons carry tool switching now (previously only one did), so neither
is overloaded: Button 2 = eraser toggle, Button 3 = category cycle (tap) +
pan (drag). See below for full mechanics.

Goal: both bindings survive reboots and tablet unplug/replug.

## Install (fresh machine)

Requires `python3-evdev` and `xdotool`, and the user in the `input` group
(`sudo usermod -aG input $USER`, then re-login).

```bash
./install.sh
```

This copies the scripts/units into `~/.local/bin` and
`~/.config/systemd/user`, appends the `.xprofile` snippet if not already
present, and enables both systemd user services. Safe to re-run after
pulling changes to this repo.

## Live files (these are what actually run — copies here are for reference)

| Purpose | Live path | Copy in this dir |
|---|---|---|
| Runs on every login/reboot | `~/.xprofile` (sourced by GDM) | `xprofile-wacom-snippet.sh` (snippet only, not the whole file) |
| Watches for tablet reconnect, reapplies Button 2/3 bindings | `~/.local/bin/wacom-watch.sh` (user systemd service, always running) | `wacom-watch.sh` |
| Runs the watcher automatically | `~/.config/systemd/user/wacom-watch.service` | `wacom-watch.service` |
| Button 2 toggles eraser; Button 3 tap (hover, no touch/movement) cycles pencil/highlighter/laser, pan (touch or movement) untouched | `~/.local/bin/wacom-button3-toggle.py` (user systemd service, always running; filename kept from the original Button-3 version) | `wacom-button3-toggle.py` |
| Runs the toggle daemon automatically | `~/.config/systemd/user/wacom-button3-toggle.service` | `wacom-button3-toggle.service` |

Superseded (kept for reference only, **not installed/used**): `wacom-apply-buttons.sh` +
`70-wacom-buttons.rules`, a udev-RUN+= approach that needed a sudo-installed rule file.
Replaced by `wacom-watch.service` below, which needs no root at all.

## How it works

1. **Login/reboot**: `.xprofile` runs `xsetwacom --set ... Button 2 0` and `xsetwacom --set ... Button 3 "pan"` directly — X is already up by the time it runs.
2. **Hot-plug** (tablet unplugged/replugged mid-session — this actually happened and is why the button briefly stopped panning): `wacom-watch.service` runs continuously as a user systemd service, reading `udevadm monitor` (no root needed — udev events are readable by any user). On every `add` event it waits for the device to enumerate and reapplies both Button 2 and Button 3. It also applies once immediately on service start/login.
3. **Button 2 + Button 3 tool switching**: `xsetwacom` has no concept of stateful or duration-dependent bindings — only fixed, stateless ones. So Button 2 is disabled in xsetwacom entirely, and `wacom-button3-toggle.py` reads the tablet's raw evdev press/release events for `BTN_STYLUS` (Button 2), `BTN_STYLUS2` (Button 3), `BTN_TOUCH`, and `ABS_X`/`ABS_Y` directly via `python-evdev`. State is a `cat_idx` (which of `CATEGORIES = ["pencil", "highlighter", "laser"]` is active) plus a per-writer-category `erase` flag. **Button 2**: every press flips the `erase` flag for the current category and sends the resulting key (`p`/`h` when off, `e` when on) — a no-op while `laser` is the active category, since there's no eraser variant of it.

   **Button 3**: xsetwacom keeps its native `pan` binding on this button (drag still pans, untouched), and the daemon separately classifies each press as pan or tap on release. It's a **pan** if any of these are true: the pen touched the tablet (`BTN_TOUCH`) at any point during the hold — checked across the whole hold, not just the press instant, since the real gesture is button-down *then* touch-down, not the other way around; the cursor moved past `MOVE_THRESHOLD_UNITS` (device units, `ABS_X`/`ABS_Y` deltas) during the hold — this tablet also supports panning purely by hovering and dragging without ever touching down, so touch state alone misses those; or the press started within `PAN_DEBOUNCE_S` of the previous press being classified as pan — a single continuous pan gesture is chopped by the driver into repeated short stroke segments, each with its own real button release+re-press, and in that tens-of-ms gap the pen is briefly and genuinely hovering before the next stroke's touch-down, which is indistinguishable from a real tap by state alone. Anything not classified as pan is a **tap**, which advances `cat_idx` to the next category (wrapping) and sends that category's key. Duration alone was tried first and dropped — a fast short pan looks just like a tap by duration.

   Keys are sent via `xdotool key` on release. The device is resolved through `/dev/input/by-id/usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse`, stable across replugs even though the underlying `/dev/input/eventN` number changes. Runs as its own user systemd service (no root needed — `/dev/input/event*` for this device is group `input`, which the user is a member of). To change the keys/order/thresholds, edit `CATEGORIES`/`WRITER_KEYS`/`PAN_DEBOUNCE_S`/`MOVE_THRESHOLD_UNITS` in the script and run `systemctl --user restart wacom-button3-toggle.service`.

4. **Triple-tap screenshot**: while Button 3 is held down, each `BTN_TOUCH` down/up pulse on the tablet surface is checked — if it's short (`TAP_TOUCH_MAX_DURATION_S`, 0.3s) and doesn't move far (`TAP_TOUCH_MAX_MOVE_UNITS`, 100 device units), it counts as a tap pulse rather than the start of a drag. Once 3 such pulses land within `TRIPLE_TOUCH_WINDOW_S` (0.6s) of each other, it fires immediately (no need to release Button 3 first): the daemon shells out to `import -window root -crop <geometry>` (ImageMagick) to capture just the secondary monitor (`SCREENSHOT_MONITOR_GEOMETRY`, currently `1920x1080+0+0` for `HDMI-0` — update this if the monitor layout changes), saves it to `SCREENSHOT_DIR` (`~/Pictures/wacom-screenshots/`) as `screenshot-<timestamp>.png`, pipes it to `xclip -selection clipboard -t image/png` to put it on the clipboard, then sends `Ctrl+V` via `xdotool` to paste it into whatever has focus. A real touch-drag pan is one continuous touch (down once, move, up once), so it never produces 3 discrete pulses and isn't confused with this gesture. Once the triple-tap fires, that Button 3 press is fully consumed — its eventual release is not also evaluated as a pan/tap.

## Status

- `.xprofile` edit: **applied** (Button 2 → disabled, Button 3 → pan).
- `wacom-watch.service`: **enabled and running**. Starts automatically on every login, no manual step needed, no sudo required.
- `wacom-button3-toggle.service`: **enabled and running**. Verified live via journalctl and hands-on testing: Button 2 toggles eraser (ignored on laser), Button 3 hover-taps cycle pencil → highlighter → laser, and both touch-drag and hover-drag pans are correctly left alone (touch, movement, and debounce all confirmed working across real usage).

## Unrelated prior-session artifact (don't confuse with the above)

`~/.local/bin/wacom-mode-daemon.py` + `~/.config/systemd/user/wacom-mode-daemon.service`
— a pen-pressure daemon that switches acceleration/deceleration settings based on
whether the pen is touching the tablet (mimics Wacom's Mac driver). Currently
**disabled**. Nothing to do with button mapping.
