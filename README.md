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
  xsetwacom (`0`); a daemon reads the raw press/release events instead, and
  splits by press duration (judged once, on release):
  - **short press** (< 0.2s): toggles **eraser on/off** for whichever
    writer tool is currently selected (pencil `p` ↔ eraser `e`, or
    highlighter `h` ↔ eraser `e`). No-op while laser is selected — erasing
    a laser pointer doesn't mean anything.
  - **long press** (≥ 0.2s): swaps directly between pencil and highlighter
    (skipping laser), landing on the plain writer key — does not preserve
    or toggle eraser state. If laser is currently selected, jumps to
    whichever of pencil/highlighter was last active.
- **Button 3** = upper barrel button → still bound to `pan` in xsetwacom
  (click+drag to pan/scroll, unchanged), **and** watched by the same daemon
  to classify each press as pan or tap: it's a pan if the pen touched the
  tablet at any point during the hold, or if the cursor moved past a small
  threshold (this tablet also supports hover-only panning); otherwise it's
  a tap, which **toggles the laser pointer** — jumps straight to laser
  (`l`) if it isn't already active, or back to whichever of
  pencil/highlighter was last active if it is. Each writer category
  remembers its own eraser state independently, preserved across the round
  trip through laser. **Holding Button 3 and tapping the pen tip on the
  tablet 3 times** in quick succession instead takes a screenshot of the
  secondary monitor and pastes it into whatever has focus — see below —
  without toggling laser or panning.

Both buttons carry tool switching now (previously only one did), so neither
is overloaded: Button 2 = eraser toggle (short) / pencil↔highlighter swap
(long), Button 3 = laser toggle (tap) + pan (drag). See below for full
mechanics.

Two more pieces round out the setup, both to reduce friction from having
mouse/keyboard and tablet fighting over focus and monitors:
- **Auto-focus-follow-writing**: any tablet activity (hover, touch, either
  barrel button) after being idle sends one Alt+Tab, swapping focus to the
  window you were in right before you last tabbed away to draw (presumed
  to be GoodNotes). After 3s of no further tablet activity, it sends
  Alt+Tab again, swapping back. See below for why this doesn't try to
  match a window by title.
- **Monitor-switch shortcuts**: `Ctrl+Alt+1` / `Ctrl+Alt+2` remap the
  tablet's active area to the laptop screen / secondary monitor
  respectively, `Ctrl+Alt+W` toggles between them, and all three also
  focus the GoodNotes window on activation.

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
| Button 2 short press toggles eraser, long press swaps pencil/highlighter; Button 3 tap (hover, no touch/movement) toggles laser, pan (touch or movement) untouched; also runs the auto-focus-follow-writing alt+tab logic | `~/.local/bin/wacom-button3-toggle.py` (user systemd service, always running; filename kept from the original Button-3 version) | `wacom-button3-toggle.py` |
| Runs the toggle daemon automatically | `~/.config/systemd/user/wacom-button3-toggle.service` | `wacom-button3-toggle.service` |
| Remaps tablet active area to a monitor + focuses GoodNotes; invoked by the `Ctrl+Alt+1`/`Ctrl+Alt+2`/`Ctrl+Alt+W` GNOME custom shortcuts | `~/.local/bin/wacom-switch-monitor.sh` | `wacom-switch-monitor.sh` |

Superseded (kept for reference only, **not installed/used**): `wacom-apply-buttons.sh` +
`70-wacom-buttons.rules`, a udev-RUN+= approach that needed a sudo-installed rule file.
Replaced by `wacom-watch.service` below, which needs no root at all.

## How it works

1. **Login/reboot**: `.xprofile` runs `xsetwacom --set ... Button 2 0` and `xsetwacom --set ... Button 3 "pan"` directly — X is already up by the time it runs.
2. **Hot-plug** (tablet unplugged/replugged mid-session — this actually happened and is why the button briefly stopped panning): `wacom-watch.service` runs continuously as a user systemd service, reading `udevadm monitor` (no root needed — udev events are readable by any user). On every `add` event it waits for the device to enumerate and reapplies both Button 2 and Button 3. It also applies once immediately on service start/login.
3. **Button 2 + Button 3 tool switching**: `xsetwacom` has no concept of stateful or duration-dependent bindings — only fixed, stateless ones. So Button 2 is disabled in xsetwacom entirely, and `wacom-button3-toggle.py` reads the tablet's raw evdev press/release events for `BTN_STYLUS` (Button 2), `BTN_STYLUS2` (Button 3), `BTN_TOUCH`, and `ABS_X`/`ABS_Y` directly via `python-evdev`. State is a `cat_idx` (which of `CATEGORIES = ["pencil", "highlighter", "laser"]` is active), a per-writer-category `erase` flag, and `last_writer` (whichever of pencil/highlighter was most recently active — used to know where to land when leaving laser). **Button 2** is judged once on release, by how long it was held: a **short press** (< `LONG_PRESS_THRESHOLD_S`, 0.2s) flips the `erase` flag for the current category and sends the resulting key (`p`/`h` when off, `e` when on) — a no-op while `laser` is the active category, since there's no eraser variant of it. A **long press** (≥ `LONG_PRESS_THRESHOLD_S`) instead swaps directly between pencil and highlighter via `WRITER_SWAP`, always sending the plain writer key (never touches the `erase` flags) — if laser is currently active, it jumps to `last_writer` instead. The 0.2s cutoff was picked by checking real eraser-toggle press durations via `journalctl`, which cluster well under 0.15s, leaving margin either side.

   **Button 3**: xsetwacom keeps its native `pan` binding on this button (drag still pans, untouched), and the daemon separately classifies each press as pan or tap on release. It's a **pan** if any of these are true: the pen touched the tablet (`BTN_TOUCH`) at any point during the hold — checked across the whole hold, not just the press instant, since the real gesture is button-down *then* touch-down, not the other way around; the cursor moved past `MOVE_THRESHOLD_UNITS` (device units, `ABS_X`/`ABS_Y` deltas) during the hold — this tablet also supports panning purely by hovering and dragging without ever touching down, so touch state alone misses those; or the press started within `PAN_DEBOUNCE_S` of the previous press being classified as pan — a single continuous pan gesture is chopped by the driver into repeated short stroke segments, each with its own real button release+re-press, and in that tens-of-ms gap the pen is briefly and genuinely hovering before the next stroke's touch-down, which is indistinguishable from a real tap by state alone. Anything not classified as pan is a **tap**, which toggles laser: if the current category isn't `laser`, jump to it; if it already is, jump back to `last_writer`. Duration alone was tried first and dropped — a fast short pan looks just like a tap by duration.

   Keys are sent via `xdotool key` on release. The device is resolved through `/dev/input/by-id/usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse`, stable across replugs even though the underlying `/dev/input/eventN` number changes. Runs as its own user systemd service (no root needed — `/dev/input/event*` for this device is group `input`, which the user is a member of). To change the keys/thresholds, edit `CATEGORIES`/`WRITER_KEYS`/`WRITER_SWAP`/`LONG_PRESS_THRESHOLD_S`/`PAN_DEBOUNCE_S`/`MOVE_THRESHOLD_UNITS` in the script and run `systemctl --user restart wacom-button3-toggle.service`.

4. **Triple-tap screenshot**: while Button 3 is held down, each `BTN_TOUCH` down/up pulse on the tablet surface is checked — if it's short (`TAP_TOUCH_MAX_DURATION_S`, 0.3s) and doesn't move far (`TAP_TOUCH_MAX_MOVE_UNITS`, 100 device units), it counts as a tap pulse rather than the start of a drag. Once 3 such pulses land within `TRIPLE_TOUCH_WINDOW_S` (0.6s) of each other, it fires immediately (no need to release Button 3 first): the daemon shells out to `import -window root -crop <geometry>` (ImageMagick) to capture just the secondary monitor (`SCREENSHOT_MONITOR_GEOMETRY`, currently `1920x1080+0+0` for `HDMI-0` — update this if the monitor layout changes), saves it to `SCREENSHOT_DIR` (`~/Pictures/wacom-screenshots/`) as `screenshot-<timestamp>.png`, pipes it to `xclip -selection clipboard -t image/png` to put it on the clipboard, then sends `Ctrl+V` via `xdotool` to paste it into whatever has focus. A real touch-drag pan is one continuous touch (down once, move, up once), so it never produces 3 discrete pulses and isn't confused with this gesture. Once the triple-tap fires, that Button 3 press is fully consumed — its eventual release is not also evaluated as a pan/tap.

5. **Auto-focus-follow-writing**: the daemon calls `note_writing_activity()` on every raw event from the tablet (`EV_KEY` or `EV_ABS` — hover movement, touch, either barrel button all count). The first such call after being idle sends a single `xdotool key alt+Tab` and sets `state["writing_active"] = True`; every call after that is a no-op until a background thread (`idle_watcher`, started once in `main()`) clears the flag. That thread polls every 0.5s and, once `WRITING_IDLE_TIMEOUT_S` (3s) has passed since the last activity, sends `alt+Tab` again and resets. This relies entirely on Alt+Tab's own MRU (most-recently-used) window ordering to swap forward then back — it does **not** try to identify the GoodNotes window by title or ID. An earlier version did (`xdotool search --name "GoodNotes"` + `windowactivate`), but broke as soon as the actual open tab/window title didn't contain the literal string "GoodNotes" (e.g. it's just not open, or the tab title is something else), silently no-op'ing the whole feature. Symmetric single Alt+Tab in, single Alt+Tab out avoids needing to identify any window at all.

6. **Monitor-switch shortcuts**: `wacom-switch-monitor.sh <output|toggle>` remaps the stylus/eraser's active area to a single monitor and focuses GoodNotes. It uses `xinput --set-prop <id> "Coordinate Transformation Matrix" ..." directly rather than `xsetwacom --set ... MapToOutput` — on this machine's hybrid NVIDIA+AMD PRIME setup, xsetwacom can't resolve either output by name at all (`Unable to find an output`), because its RandR lookup doesn't span GPU providers. The script instead reads geometry straight from `xrandr --query` (which sees both outputs fine) and computes the same per-output scale/offset matrix `MapToOutput` would have applied. Called with `toggle` (no explicit output), it inspects the stylus's current Y-offset in the matrix to infer which monitor it's currently mapped to and flips to the other. Wired to three GNOME custom keybindings (`org.gnome.settings-daemon.plugins.media-keys.custom-keybinding`, `gsettings`-managed, not part of this repo's install script): `Ctrl+Alt+1` → `eDP-1-0` (laptop), `Ctrl+Alt+2` → `HDMI-0` (secondary), `Ctrl+Alt+W` → `toggle`.

## Status

- `.xprofile` edit: **applied** (Button 2 → disabled, Button 3 → pan).
- `wacom-watch.service`: **enabled and running**. Starts automatically on every login, no manual step needed, no sudo required.
- `wacom-button3-toggle.service`: **enabled and running**. Verified live via journalctl and hands-on testing: Button 2 short press toggles eraser (ignored on laser) and long press swaps pencil ↔ highlighter (landing on `last_writer` from laser), Button 3 hover-taps toggle laser ↔ `last_writer`, both touch-drag and hover-drag pans are correctly left alone (touch, movement, and debounce all confirmed working across real usage), and auto-focus-follow-writing alt+tabs in/out correctly on real tablet activity/idle cycles.
- `wacom-switch-monitor.sh` + GNOME shortcuts: **working**. Verified both explicit outputs and toggle recompute and apply the correct `Coordinate Transformation Matrix` for `eDP-1-0`/`HDMI-0`.

## Unrelated prior-session artifact (don't confuse with the above)

`~/.local/bin/wacom-mode-daemon.py` + `~/.config/systemd/user/wacom-mode-daemon.service`
— a pen-pressure daemon that switches acceleration/deceleration settings based on
whether the pen is touching the tablet (mimics Wacom's Mac driver). Currently
**disabled**. Nothing to do with button mapping.
