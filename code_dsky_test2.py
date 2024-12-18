# This sets up the GPIO pins for the rows and columns, scans the key matrix, and sends the corresponding key presses via USB

import board
import digitalio
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_debouncer import Debouncer

# Define the key matrix
rows = [board.GP17, board.GP16, board.GP15]
cols = [board.GP6, board.GP5, board.GP4, board.GP3, board.GP2, board.GP1, board.GP0]

# Define the key mapping
key_map = [
    Keycode.V, Keycode.KEYPAD_PLUS, Keycode.SEVEN, Keycode.EIGHT, Keycode.NINE, Keycode.C, Keycode.E,
    Keycode.N, Keycode.KEYPAD_MINUS, Keycode.FOUR, Keycode.FIVE, Keycode.SIX, Keycode.P, Keycode.R, 
    None, Keycode.ZERO, Keycode.ONE, Keycode.TWO, Keycode.THREE, Keycode.K, None
]

# Initialize the keyboard
kbd = Keyboard(usb_hid.devices)

# Initialize row and column pins
row_pins = [digitalio.DigitalInOut(pin) for pin in rows]
col_pins = [digitalio.DigitalInOut(pin) for pin in cols]

for row_pin in row_pins:
    row_pin.direction = digitalio.Direction.OUTPUT
    row_pin.value = False

for col_pin in col_pins:
    col_pin.direction = digitalio.Direction.INPUT
    col_pin.pull = digitalio.Pull.DOWN

# Specify columns_to_anodes is true
columns_to_anodes = True

# Initialize debouncers for each key
debouncers = [Debouncer(col_pin) for col_pin in col_pins]
row_debouncers = [Debouncer(row_pin) for row_pin in row_pins]

while True:
    for row_index, row_pin in enumerate(row_pins):
        row_debouncers[row_index].update()
        if row_debouncers[row_index].fell or row_debouncers[row_index].rose:
            row_pin.value = True
            for col_index, debouncer in enumerate(debouncers):
                debouncer.update()
                if debouncer.fell:
                    key_index = row_index * len(cols) + col_index
                    kbd.press(key_map[key_index])
                elif debouncer.rose:
                    key_index = row_index * len(cols) + col_index
                    kbd.release(key_map[key_index])
            row_pin.value = False