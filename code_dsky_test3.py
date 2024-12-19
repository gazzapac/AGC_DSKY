import keypad
import board
from digitalio import DigitalInOut, Pull
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_debouncer import Debouncer
import adafruit_ticks as ticks

# Initialize the keyboard
kbd = Keyboard(usb_hid.devices)

# Define the keymap
keymap = [
    Keycode.V, Keycode.KEYPAD_PLUS, Keycode.SEVEN, Keycode.EIGHT, Keycode.NINE, Keycode.C, Keycode.E,
    Keycode.N, Keycode.KEYPAD_MINUS, Keycode.FOUR, Keycode.FIVE, Keycode.SIX, Keycode.P, Keycode.R,
    None, Keycode.ZERO, Keycode.ONE, Keycode.TWO, Keycode.THREE, Keycode.K, None
]

# Setup the key matrix
km = keypad.KeyMatrix(
    row_pins=(board.GP17, board.GP16, board.GP15),
    column_pins=(board.GP6, board.GP5, board.GP4, board.GP3, board.GP2, board.GP1, board.GP0),
    columns_to_anodes=True,
)

# Initialize debouncers for each key
debouncers = [Debouncer(km.events.get, interval=0.01) for _ in range(len(keymap))]

while True:
    for i, debouncer in enumerate(debouncers):
        debouncer.update()
        if debouncer.fell:
            keycode = keymap[i]
            if keycode:
                kbd.press(keycode)
                print(f"Key pressed: {keycode}")
        if debouncer.rose:
            keycode = keymap[i]
            if keycode:
                kbd.release(keycode)
                print(f"Key released: {keycode}")
