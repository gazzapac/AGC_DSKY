#!/bin/bash
# Manual/bench run in a terminal (normal autostart is the systemd services in systemd/).
# Stops the DSKY service and runs the front end in the foreground so the console
# keyboard works as well as the Pico keypad. yaAGC keeps running as yaagc.service.

sudo systemctl stop dsky.service
sudo systemctl start yaagc.service

echo "Starting DSKY (Ctrl-C to quit; 'sudo systemctl start dsky' to go back to autostart)"
sudo python3 /home/gazzapac-dsky/piDSKY-gp.py --keyboard=auto
