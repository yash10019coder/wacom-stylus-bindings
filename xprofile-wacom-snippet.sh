# Wacom snippet appended to ~/.xprofile — applied at every login/reboot.
# Full ~/.xprofile also has commented-out absolute-mode/screen-mapping lines
# from an earlier session (device ids 14/15, currently disabled).

# Stylus lower barrel button -> disabled (0), so it doesn't also fire its
# default click; wacom-button3-toggle.service handles tool switching on this
# button by reading the raw evdev events instead (short/long press).
xsetwacom --set "Wacom One by Wacom M Pen stylus" Button 2 0

# Stylus upper barrel button -> pan (persist across reboot/login)
xsetwacom --set "Wacom One by Wacom M Pen stylus" Button 3 "pan"
