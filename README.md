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
  for quick taps (press+release under 0.35s, no drag): a tap cycles the tool
  **category** — pencil → highlighter → laser → pencil ... Each writer
  category remembers its own eraser state independently.

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
| Button 2 toggles eraser; Button 3 tap cycles pencil/highlighter/laser (drag still pans) | `~/.local/bin/wacom-button3-toggle.py` (user systemd service, always running; filename kept from the original Button-3 version) | `wacom-button3-toggle.py` |
| Runs the toggle daemon automatically | `~/.config/systemd/user/wacom-button3-toggle.service` | `wacom-button3-toggle.service` |

Superseded (kept for reference only, **not installed/used**): `wacom-apply-buttons.sh` +
`70-wacom-buttons.rules`, a udev-RUN+= approach that needed a sudo-installed rule file.
Replaced by `wacom-watch.service` below, which needs no root at all.

## How it works

1. **Login/reboot**: `.xprofile` runs `xsetwacom --set ... Button 2 0` and `xsetwacom --set ... Button 3 "pan"` directly — X is already up by the time it runs.
2. **Hot-plug** (tablet unplugged/replugged mid-session — this actually happened and is why the button briefly stopped panning): `wacom-watch.service` runs continuously as a user systemd service, reading `udevadm monitor` (no root needed — udev events are readable by any user). On every `add` event it waits for the device to enumerate and reapplies both Button 2 and Button 3. It also applies once immediately on service start/login.
3. **Button 2 + Button 3 tool switching**: `xsetwacom` has no concept of stateful or duration-dependent bindings — only fixed, stateless ones. So Button 2 is disabled in xsetwacom entirely, and `wacom-button3-toggle.py` reads the tablet's raw evdev press/release events for both `BTN_STYLUS` (Button 2) and `BTN_STYLUS2` (Button 3) directly via `python-evdev`. State is a `cat_idx` (which of `CATEGORIES = ["pencil", "highlighter", "laser"]` is active) plus a per-writer-category `erase` flag. **Button 2**: every press flips the `erase` flag for the current category and sends the resulting key (`p`/`h` when off, `e` when on) — a no-op while `laser` is the active category, since there's no eraser variant of it. **Button 3**: xsetwacom keeps its native `pan` binding on this button (drag still pans, untouched), and the daemon separately measures each press/release duration — under `LONG_PRESS_THRESHOLD_S` (0.35s) with no real drag, it's a **tap**, which advances `cat_idx` to the next category (wrapping) and sends that category's key; at/above the threshold it's treated as a drag and the daemon does nothing (xsetwacom's native pan already handled it). Keys are sent via `xdotool key` on release. The device is resolved through `/dev/input/by-id/usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse`, stable across replugs even though the underlying `/dev/input/eventN` number changes. Runs as its own user systemd service (no root needed — `/dev/input/event*` for this device is group `input`, which the user is a member of). To change the keys/order/threshold, edit `CATEGORIES`/`WRITER_KEYS`/`LONG_PRESS_THRESHOLD_S` in the script and run `systemctl --user restart wacom-button3-toggle.service`.

## Status

- `.xprofile` edit: **applied** (Button 2 → disabled, Button 3 → pan).
- `wacom-watch.service`: **enabled and running**. Starts automatically on every login, no manual step needed, no sudo required.
- `wacom-button3-toggle.service`: **enabled and running**. Verified live via journalctl: Button 2 toggles eraser (ignored on laser), Button 3 taps cycle pencil → highlighter → laser, Button 3 drag still pans.

## Unrelated prior-session artifact (don't confuse with the above)

`~/.local/bin/wacom-mode-daemon.py` + `~/.config/systemd/user/wacom-mode-daemon.service`
— a pen-pressure daemon that switches acceleration/deceleration settings based on
whether the pen is touching the tablet (mimics Wacom's Mac driver). Currently
**disabled**. Nothing to do with button mapping.
