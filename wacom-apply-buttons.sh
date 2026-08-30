#!/bin/bash
# Reapplies xsetwacom button bindings on tablet hot-plug (triggered by udev).
# .xprofile handles the login/reboot case; this covers unplug/replug mid-session.
# Live copy: ~/.local/bin/wacom-apply-buttons.sh (that's the one actually run)
set -u

USER_NAME=ubuntu
DEVICE_NAME="Wacom One by Wacom M Pen stylus"

XPID=$(pgrep -u "$USER_NAME" -f Xorg | head -n1)
[ -z "$XPID" ] && exit 0

DISPLAY_VAL=$(tr '\0' '\n' < "/proc/$XPID/environ" 2>/dev/null | grep -m1 '^DISPLAY=' | cut -d= -f2)
XAUTH_VAL=$(tr '\0' '\n' < "/proc/$XPID/environ" 2>/dev/null | grep -m1 '^XAUTHORITY=' | cut -d= -f2)
DISPLAY_VAL=${DISPLAY_VAL:-:1}
XAUTH_VAL=${XAUTH_VAL:-/run/user/1000/gdm/Xauthority}

for i in $(seq 1 10); do
    if runuser -u "$USER_NAME" -- env DISPLAY="$DISPLAY_VAL" XAUTHORITY="$XAUTH_VAL" xsetwacom --list devices 2>/dev/null | grep -q "$DEVICE_NAME"; then
        runuser -u "$USER_NAME" -- env DISPLAY="$DISPLAY_VAL" XAUTHORITY="$XAUTH_VAL" xsetwacom --set "$DEVICE_NAME" Button 2 "pan"
        exit 0
    fi
    sleep 1
done
