# Wacom snippet appended to ~/.xprofile — applied at every login/reboot.
# Full ~/.xprofile also has commented-out absolute-mode/screen-mapping lines
# from an earlier session (device ids 14/15, currently disabled).

# Stylus lower barrel button -> pan (persist across reboot/login)
xsetwacom --set "Wacom One by Wacom M Pen stylus" Button 2 "pan"

# Stylus upper barrel button -> disabled (0), so it doesn't also fire its
# default right-click; wacom-button3-toggle.service cycles e/w/l on this
# button by reading the raw evdev events instead.
xsetwacom --set "Wacom One by Wacom M Pen stylus" Button 3 0
