import time
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

debounce_time = 0.05  # 50 milliseconds
last_event_time = {}

while True:
    event = km.events.get()
    if event:
        current_time = time.monotonic()
        key_number = event.key_number

        if key_number not in last_event_time or (current_time - last_event_time[key_number]) > debounce_time:
            last_event_time[key_number] = current_time
            if event.pressed:
                keycode = keymap[key_number]
                if keycode:
                    kbd.send(keycode)
            print(event)
