# Wacom One M — button bindings & persistence

Device: `Wacom One by Wacom M Pen stylus` (2 barrel buttons + tip).

Actual button layout on this device (confirmed via `xsetwacom --get`/`xinput`):
- **Button 1** = pen tip (draw/click) — never remapped.
- **Button 2** = lower barrel button → `pan` (click+drag to pan/scroll).
- **Button 3** = upper barrel button → disabled in xsetwacom (`0`); a daemon
  reads the raw press/release events instead and runs two independent cycles
  based on press duration: a **short press** alternates `p` (pen) ↔ `e`
  (eraser), a **long press** (≥0.35s) alternates `h` (highlight) ↔ `l`
  (laser) (see below).

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
| Short/long press on Button 3: toggles pen/eraser, or highlight/laser | `~/.local/bin/wacom-button3-toggle.py` (user systemd service, always running) | `wacom-button3-toggle.py` |
| Runs the toggle daemon automatically | `~/.config/systemd/user/wacom-button3-toggle.service` | `wacom-button3-toggle.service` |

Superseded (kept for reference only, **not installed/used**): `wacom-apply-buttons.sh` +
`70-wacom-buttons.rules`, a udev-RUN+= approach that needed a sudo-installed rule file.
Replaced by `wacom-watch.service` below, which needs no root at all.

## How it works

1. **Login/reboot**: `.xprofile` runs `xsetwacom --set ... Button 2 "pan"` and `xsetwacom --set ... Button 3 0` directly — X is already up by the time it runs.
2. **Hot-plug** (tablet unplugged/replugged mid-session — this actually happened and is why the button briefly stopped panning): `wacom-watch.service` runs continuously as a user systemd service, reading `udevadm monitor` (no root needed — udev events are readable by any user). On every `add` event it waits for the device to enumerate and reapplies both Button 2 and Button 3. It also applies once immediately on service start/login.
3. **Button 3 short/long press**: `xsetwacom` has no concept of press-duration-dependent bindings — it only does fixed, stateless bindings. So Button 3 is disabled in xsetwacom entirely, and `wacom-button3-toggle.py` reads the tablet's raw evdev press (`value == 1`) and release (`value == 0`) events for `BTN_STYLUS2` directly via `python-evdev`, and measures the time between them. Under `LONG_PRESS_THRESHOLD_S` (0.35s) it's a **short press**: advances an independent index into `SHORT_CYCLE = ["p", "e"]` (pen, eraser). At or above the threshold it's a **long press**: advances a separate index into `LONG_CYCLE = ["h", "l"]` (highlight, laser). Each cycle keeps its own position, so switching pen/eraser doesn't disturb where you left off in highlight/laser. The key is sent via `xdotool key` on release. It resolves the device through `/dev/input/by-id/usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse`, which stays stable across replugs even though the underlying `/dev/input/eventN` number changes. Runs as its own user systemd service (no root needed — `/dev/input/event*` for this device is group `input`, which the user is a member of). To change the keys/order/threshold, edit `SHORT_CYCLE`/`LONG_CYCLE`/`LONG_PRESS_THRESHOLD_S` in the script and run `systemctl --user restart wacom-button3-toggle.service`.

## Status

- `.xprofile` edit: **applied** (Button 2 → pan, Button 3 → disabled).
- `wacom-watch.service`: **enabled and running**. Starts automatically on every login, no manual step needed, no sudo required.
- `wacom-button3-toggle.service`: **enabled and running**. Verified live via journalctl: short presses (~0.1s) toggle `p`/`e`, long presses (~0.4-0.8s) toggle `h`/`l`.

## Unrelated prior-session artifact (don't confuse with the above)

`~/.local/bin/wacom-mode-daemon.py` + `~/.config/systemd/user/wacom-mode-daemon.service`
— a pen-pressure daemon that switches acceleration/deceleration settings based on
whether the pen is touching the tablet (mimics Wacom's Mac driver). Currently
**disabled**. Nothing to do with button mapping.
