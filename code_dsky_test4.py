import keypad
import board
from digitalio import DigitalInOut, Pull
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

kbd = Keyboard(usb_hid.devices)

km = keypad.KeyMatrix(
    row_pins=(board.GP17, board.GP16, board.GP15),
    column_pins=(board.GP6, board.GP5, board.GP4, board.GP3, board.GP2, board.GP1, board.GP0),
    columns_to_anodes=True,
)

keymap = [
    Keycode.V, Keycode.KEYPAD_PLUS, Keycode.SEVEN, Keycode.EIGHT, Keycode.NINE, Keycode.C, Keycode.E,
    Keycode.N, Keycode.KEYPAD_MINUS, Keycode.FOUR, Keycode.FIVE, Keycode.SIX, Keycode.P, Keycode.R,
    None, Keycode.ZERO, Keycode.ONE, Keycode.TWO, Keycode.THREE, Keycode.K, None
]

while True:
    event = km.events.get()
    if event:
        if event.pressed:
            keycode = keymap[event.key_number]
            if keycode:
                kbd.send(keycode)
        print(event)
