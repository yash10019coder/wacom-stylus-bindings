# Learnings & design log

A chronological record of how this setup came together, why each decision
was made, and the dead ends along the way — kept so future changes don't
re-litigate settled questions.

## 1. Persisting Button 2 = pan across reboot/hotplug

The starting problem: `xsetwacom --set ... Button 2 pan` works immediately
but is not persistent — it resets on reboot, and separately, when the
tablet is unplugged and replugged mid-session the binding is lost even
without a reboot (it's a fresh device instance to X).

- **Reboot persistence**: solved trivially by putting the `xsetwacom`
  command in `~/.xprofile`, which GDM sources at every login. No root
  needed.
- **Hotplug persistence**: reboot-only persistence isn't enough because
  unplug/replug happens mid-session without a fresh login. First approach
  considered was a udev rule (`70-wacom-buttons.rules`) with `RUN+=` to
  fire a script on device add — this works but needs a rule file installed
  under `/etc/udev/rules.d/` with sudo, which is more fragile to keep in
  sync with a user-space repo. **Superseded** in favor of a small
  always-on user systemd service (`wacom-watch.service`) that runs
  `udevadm monitor` continuously (readable by any user, no root) and
  reapplies bindings on every `add` event. Simpler to reason about, and
  the whole thing lives in `~/.config/systemd/user` + `~/.local/bin` —
  no root touches at all. The udev-rule files are kept in this repo only
  for reference, not installed.

## 2. Figuring out the actual button layout

The user's first request described the buttons by number ("Button 1",
"Button 2") based on intuition, not on what `xsetwacom` actually reports.
Investigating with `xsetwacom --get` and `xinput list-props` before
touching anything revealed the real mapping on this device (`Wacom One by
Wacom M Pen stylus`):

- **Button 1** = the pen tip itself (`button +1`, left-click/draw). Not a
  barrel button at all — remapping it would break normal pen use.
- **Button 2** = the *lower* barrel button, raw evdev `BTN_STYLUS` (code
  331).
- **Button 3** = the *upper* barrel button, raw evdev `BTN_STYLUS2` (code
  332). Default binding was `button +3` (right-click).
- xsetwacom enumerates a "Button 8" too, but the device's actual evdev
  capabilities only expose `BTN_TOUCH`, `BTN_STYLUS`, `BTN_STYLUS2` — no
  third physical barrel button exists on this pen.

**Learning**: always verify a device's actual button/evdev mapping before
acting on a user's numbered description of "button 1/2/3" — the numbering
in casual speech and the numbering `xsetwacom` uses do not necessarily
match, and getting it wrong here would have silently disabled pen
drawing. When in doubt, surface the ambiguity back to the user instead of
guessing (this is what happened — confirmed "Button 1" in the request
actually meant the upper barrel button in `xsetwacom` terms).

## 3. Why Button 3 needed a custom daemon instead of xsetwacom

The user wanted Button 3 to alternate between two (later four) different
keystrokes on successive presses. `xsetwacom` bindings are fixed and
stateless — a button can be bound to one action, period. It cannot track
"this is the Nth press" or branch on press duration.

**Solution**: disable Button 3 in xsetwacom entirely (`Button 3 0`) so the
driver doesn't also fire its own right-click, and instead read the raw
evdev event stream directly via `python-evdev`
(`~/.local/bin/wacom-button3-toggle.py`), which sees `BTN_STYLUS2`
press/release events with real timestamps — the same way a keyboard
driver would see key events. State (which key is "next") is kept in
memory in the daemon, and the actual keystroke is injected into whatever
window has focus via `xdotool key`.

This runs as its own user systemd service, no root required — confirmed
`/dev/input/event*` for this device is group `input` and the user is
already a member, so raw reads work without sudo.

**Device path stability**: `/dev/input/eventN` renumbers across
unplug/replug. The daemon resolves the device through the stable
`/dev/input/by-id/usb-Wacom_Co._Ltd._CTL-672_5GA00M1000190-event-mouse`
symlink instead (falling back to scanning `evdev.list_devices()` by name
if that's ever missing), so it keeps working after a replug without
needing `wacom-watch.service` to tell it anything.

## 4. Iterating the Button 3 behavior: toggle → cycle → duration-gated cycles

The requirement evolved twice after the initial two-key toggle shipped:

1. **`e` / `w` toggle** (first version) — alternate two keys on each
   press. Simple in-memory boolean-ish index, worked immediately.
2. **`e → w → l` 3-key cycle** — extended to a rotating index over a list
   (`KEY_CYCLE`) instead of a 2-way flip, to support a third tool
   (laser). Trivial generalization: `index = (index + 1) % len(cycle)`.
3. **`e → p → h → l` 4-key cycle, then renamed `w`→`p`** — added a 4th
   tool (highlight) and renamed write→pen to `p` since the mnemonic was
   "pen" not "write". Still a single flat cycle at this point.
4. **Final: short-press vs long-press splits the cycle into two** — a
   flat 4-item cycle got unwieldy in practice (reaching pen from
   highlight could take 3 presses). Split into two *independent*,
   duration-gated 2-item cycles instead:
   - short press (`< 0.35s` between evdev press and release) → advances
     `SHORT_CYCLE = ["p", "e"]` (the two tools switched constantly)
   - long press (`>= 0.35s`) → advances `LONG_CYCLE = ["h", "l"]` (the
     two tools needed occasionally)
   - each cycle keeps its own index, so using one never disturbs the
     other's position.

**Learning**: this is the general pattern for a single physical
input needing more than ~2-3 stateful outputs — don't just keep growing
one flat cycle; split by an orthogonal signal (here, press duration) into
smaller, faster cycles for the common case, with the rare case behind a
deliberate, slightly slower gesture. Verified end-to-end via
`journalctl --user -u wacom-button3-toggle.service -f` while physically
pressing the button — this was done at every iteration, not just once,
since state-machine bugs (stuck index, off-by-one wraparound) don't show
up from reading the code alone.

## 5. Color switching — investigated and explicitly deferred

The user asked whether pen *color* (not tool) could be cycled the same
way. Checked: GoodNotes (the target app, used via the web version) has
**no keyboard shortcut for changing pen color** on any platform as of
this writing — it's a long-standing, frequently requested feature on
GoodNotes' own feedback forum, with at least one thread marked "Coming
Soon" by GoodNotes staff but nothing shipped. Since there's no shortcut
key to send, `xdotool key` has nothing to target.

The only other technical route considered — `xdotool` sending a mouse
click at a fixed screen coordinate where the color swatch lives — was
deliberately **not implemented**: it's brittle (breaks on window
move/resize or toolbar layout changes) and was judged not worth the
fragility for a "nice to have." Left as a known gap, revisit if GoodNotes
ships the shortcut, or if the user decides the coordinate-click hack is
worth the maintenance cost after all.

## 5.1 Family-switch memory vs blind advancing

After the short/long split shipped, a subtler bug surfaced: each family's
index was a pointer to "what to send *next*", which silently advanced
every time that family was used — including across an intervening press
of the *other* family. So if long-press last gave `h`, then you did a few
short presses (pen/eraser), the *next* long press gave `l` — not because
you'd asked to move on from `h`, but because the pointer had already
quietly advanced past it during the short-press activity.

The fix: track, per family, the tool it is *currently sitting on* (not
"next to send"), plus one shared `last_family` flag. On each press:
switching families (current press's family differs from `last_family`)
just re-sends that family's current tool, unchanged. Only a press of the
**same** family as the previous press advances that family's index. This
matches the intuitive mental model — "the highlighter tool doesn't move
around behind my back just because I used the eraser for a while."

Verified via `journalctl -f` against the literal sequence
`p e p e h l e l h l e l` requested during testing — traced by hand
against the state machine and confirmed to match exactly, output for
output.

## 5.2 Swapping which physical button does which job

After using the setup for a while, the user found the tool-switching
button (originally the upper barrel, Button 3) less comfortable to reach
than the lower barrel button (Button 2, originally bound to `pan`).
Swapped them: Button 2 → tool-switching daemon, Button 3 → `pan`.

This touched every layer that had a button-number baked in:
`wacom-button3-toggle.py` (evdev code `BTN_STYLUS2` → `BTN_STYLUS`, plus
log/comment text), `.xprofile` and `wacom-watch.sh` (which
xsetwacom-disables vs which gets `pan`), the systemd service
`Description=`, and the README. The Python file itself was **not**
renamed (`wacom-button3-toggle.py` still does the tool-switching, just on
Button 2 now) — renaming it would mean updating the systemd unit's
`ExecStart` path too, and `install.sh`'s copy step, for purely cosmetic
gain; the file's docstring/comments make the actual button clear instead.

**Learning**: a hardcoded button/evdev-code mapping like this benefits
from being named after *what it does* (`wacom-button3-toggle.py`) rather
than needing a rename every time the physical assignment changes — but
only up to a point; if this project grows more button reassignments, a
config constant at the top of the file (`WATCH_CODE = evdev.ecodes.BTN_STYLUS`)
would be a cleaner single point of truth than a name that's now
technically inaccurate. Not worth doing for a two-button swap; would be
worth doing before a third.

## 6. General workflow notes

- Every persistence layer (`.xprofile`, `wacom-watch.service`) was
  updated in lockstep whenever Button 3's behavior changed, even though
  Button 3's *toggle logic* itself doesn't live there — only the "disable
  Button 3 in xsetwacom" line does. Easy to forget one of the three
  places (live file, `~/scripts/wacom` reference copy, README) when
  iterating quickly; this repo's existence is partly to make that
  drift visible via `git diff` before committing.
- All changes were applied live and restarted (`systemctl --user restart
  wacom-button3-toggle.service`) immediately after each edit, rather than
  batching multiple behavior changes before testing — caught the
  stale-description bug in the `.service` file's `Description=` line
  this way (cosmetic, but would have been confusing in `systemctl
  status` output otherwise).
- Nothing in this whole setup requires root/sudo at any point — every
  piece deliberately stays in user-space (`~/.config/systemd/user`,
  `~/.local/bin`, `input` group membership for raw evdev reads). This was
  a conscious constraint, not an accident, and is worth preserving in any
  future extension.
