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

## Countdown timer
Key `V88E` (V88 is a spare verb in Luminary099). VERB/NOUN flash; load R1 =
hours, R2 = minutes, R3 = seconds to 2 decimal places (`+03000` = 30.00 s),
each as `+` and 5 digits then ENTR. The last ENTR starts the countdown, shown
like N36. At zero the lamps chase down the panel, then PROG stays on while
STBY flashes; PRO or RSET returns to the AGC display. `V34E` cancels and
`V94E` goes to the clock. Handled on the Pi; nothing is sent to the AGC.

## Shutting down
- **Keypad:** key `V98E`. All lamps blink for 5 s; press `PRO` to power off.
  Any other key, or waiting, cancels.
- **Button:** GPIO17 (pin 11) to GND (`dtoverlay=gpio-shutdown,gpio_pin=17`).
- **SSH:** `sudo poweroff`.

Unplug once the activity LED stays dark. To start again, cycle the power.

## Notes
- yaAGC runs with `--no-resume` from tmpfs (`/run/yaagc`). A truncated `core`
  resume file (for example after a brown-out) makes yaAGC fail with the
  misleading "Core-rope image file read error".
- At idle the display shows a clock. The first keypress clears it and
  connects to the AGC.
- `V94E`, or 10 minutes without a keypress (`--idle-minutes`), returns to the
  clock. The AGC keeps running, and the next key restores its display.
- `V94E`, `V98E` and `V88E` are handled on the Pi and never sent to the AGC. A VERB
  press is therefore held until the next keys show it isn't one of them.
