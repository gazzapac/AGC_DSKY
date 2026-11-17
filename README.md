# AGC_DSKY

Apollo LM DSKY replica: Raspberry Pi 3B (Bookworm) running Virtual AGC's `yaAGC`
with **Luminary099**, a Nextion display on `/dev/ttyS0` (9600 baud), NeoPixel
status lamps on GPIO 18, and a Pico 2 keypad acting as a USB keyboard.
Based on Ron Burkey's piDSKY (Virtual AGC project).

## Files
- `piDSKY-gp.py` – DSKY front end. It reads the Pico directly from `/dev/input`
  (python3-evdev), so it doesn't need a terminal or window focus.
- `systemd/yaagc.service`, `systemd/dsky.service` – autostart.
- `runAGC.sh` – manual bench run in a terminal.
- `pico/code.py` – CircuitPython keypad firmware for the Pico 2.

## Install (on the Pi)
    sudo apt install python3-evdev
    cp piDSKY-gp.py ~/
    sudo cp systemd/*.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now yaagc dsky
    journalctl -u dsky -f        # logs

Expects Virtual AGC to be built in `~/virtualagc`. Close the VirtualAGC GUI,
because it can take port 19797.

## Notes
- yaAGC runs with `--no-resume` from tmpfs (`/run/yaagc`). A truncated `core`
  resume file (for example after a brown-out) makes yaAGC fail with the
  misleading "Core-rope image file read error".
- At idle the display shows a clock. The first keypress clears it and
  connects to the AGC.
