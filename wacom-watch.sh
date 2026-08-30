#!/bin/bash
# Watches udev for the Wacom tablet reconnecting and reapplies button bindings.
# Runs as a user systemd service — no root/sudo needed (udevadm monitor is
# readable by any user). Supersedes the udev-rule+RUN+= approach, which
# needed a sudo-installed rule file.
set -u

DEVICE_NAME="Wacom One by Wacom M Pen stylus"
DISPLAY_VAL="${DISPLAY:-:1}"
XAUTH_VAL="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"
export DISPLAY="$DISPLAY_VAL" XAUTHORITY="$XAUTH_VAL"

apply() {
    for i in $(seq 1 10); do
        if xsetwacom --list devices 2>/dev/null | grep -q "$DEVICE_NAME"; then
            xsetwacom --set "$DEVICE_NAME" Button 2 0
            xsetwacom --set "$DEVICE_NAME" Button 3 "pan"
            echo "$(date -Is) reapplied Button 2 -> disabled (toggle daemon handles it), Button 3 -> pan"
            return
        fi
        sleep 1
    done
}

# Apply once at startup (covers login/service restart case too)
apply

udevadm monitor --udev --subsystem-match=input 2>/dev/null | while read -r line; do
    case "$line" in
        *UDEV*add*) apply ;;
    esac
done
