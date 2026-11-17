#!/usr/bin/python3
# Copyright:	None, placed in the PUBLIC DOMAIN by its author (Ron Burkey)
# Filename: 	piDSKY.py
# Purpose:	This is an illustration of how to use the skeleton peripheral program 
#		piPeripheral.py to create a simple simulated DSKY.
# Reference:	http://www.ibiblio.org/apollo/developer.html
# Mod history:	2017-11-17 RSB	Began.
#               2017-11-21 RSB	Updated with some fixes to the PRO and NOUN
#				keys that had been identified for piDSKY2.py.
#		2017-12-02 RSB	Replaced the entire program with a stripped form
#				of piDSKY2.py (in which all hardware-specific stuff
#				has been removed), because it was easier than 
#				back-porting bug-fixes.
#		2018-01-06 MAS	Switched the TEMP light to use channel 163 instead
#				of channel 11.
#
# Note that certain functionality (I think the code for get_char_keyboard_nonblock)
# might not work under Windows, but everything should
# presumably work in Linux, Raspbian, Mac OS X, etc.
#
# In this skeleton form, the script acts as kind of a console-based DSKY, in which
# you can use keyboard keys (0 1 2 3 4 5 6 7 8 9 + - V N C P K R Enter) as surrogates
# for DSKY pushbuttons, and all DSKY-related outputs from yaAGC are simply parsed and
# displayed in textual form, though the idea is that in general, you'd rip out all of 
# that DSKY-specific stuff and replace it with whatever you wanted.
#
# The parts which need to be modified to be target-system specific are the 
# outputFromAGC() and inputsForAGC() functions, which are in the section *after* the following
# section.  The immediately following section, on the other hand, has some utility functions I use
# for the default outputFromAGC() and inputsForAGC() functions I provide, and
# can be deleted if they're not useful for the specific implementation desired.
#
# To run the program in its present form, you have to use yaAGC, and optionally
# yaDSKY2 (if you want to see the graphical DSKY and piPeripheral.py working in
# parallel).  To do that, assuming you had a directory setup in which all of the
# appropriate files could be found, you could run (presumably from different consoles)
#
#	yaDSKY2 --cfg=LM.ini --port=19797
#	yaAGC --core=Luminary099.bin --port=19797 --cfg=LM.ini
#	piDSKY.py
#
# If you didn't want to use yaDSKY2, then this stuff could all be run in a pure
# command-line environment without a GUI desktop.

import time
import os
import subprocess
import signal
import sys
import argparse
import threading
import termios
import fcntl
import socket
import select
import glob
import collections
import serial
try:
    import evdev
except ImportError:
    evdev = None
from time import sleep, strftime
from datetime import datetime
import board
import neopixel

#import PySimpleGUI as sg
import struct
import RPi.GPIO as GPIO

# Parse command-line arguments.
cli = argparse.ArgumentParser()
cli.add_argument("--host", help="Host address of yaAGC, defaulting to localhost.")
cli.add_argument("--port", help="Port for yaAGC, defaulting to 19797.", type=int)
cli.add_argument("--slow", help="For use on really slow host systems.")
cli.add_argument("--keyboard", choices=["auto", "pico", "stdin"], default="auto",
                 help="Key source: 'pico' reads the Pico 2 keypad directly via /dev/input (works "
                      "without a terminal, e.g. under systemd); 'stdin' reads the controlling "
                      "terminal; 'auto' (default) uses both when available.")
cli.add_argument("--pico-glob", default="/dev/input/by-id/usb-Raspberry_Pi_Pico*-event-kbd",
                 help="Glob used to find the Pico keypad input device.")
cli.add_argument("--idle-minutes", type=float, default=10,
                 help="Return to the clock after this many minutes without a keypress "
                      "(0 disables). V94E also returns to the clock.")
args = cli.parse_args()

# Only one copy may drive the Nextion/NeoPixels/keypad at a time; a second copy
# (e.g. a leftover desktop autostart) would fight over the display.
lockFile = open("/run/lock/piDSKY.lock", "w")
try:
    fcntl.flock(lockFile, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("Another piDSKY-gp.py is already running; exiting. "
          "(If it's the service: sudo systemctl stop dsky)")
    sys.exit(1)

# Reset the raspberry pi pico
GPIO.setmode(GPIO.BCM)             
GPIO.setup(23, GPIO.OUT) 	# set GPIO 23 to output  
GPIO.output(23, GPIO.LOW)   # set pin LOW, to pull the RUN pin on the Pico low
time.sleep(1)	   			# wait one sec
GPIO.output(23, GPIO.HIGH)  # set port/pin value to HIGH 

# initialize the Status Indicator Panel with the Neopixels
# NeoPixels must be connected to D10, D12, D18 or D21 to work.
board.D18
pixel_pin = board.D18

# set indicator colours
yellow =	(255,180,0)
white =		(255,255,255)
black =		(0,0,0)

# set named 2 pixel arrays for each of the lamps containing the pixel location
# on the neopixel string, with corresponding colour
lamps = {
    "UPLINK ACTY" : {
        "pos" : [2,3],
        "col" : white},
    "TEMP" : {
        "pos" : [0,1],
        "col" : yellow},
    "NO ATT" : {
        "pos" : [4,5],
        "col" : white},
    "GIMBAL LOCK" : {
        "pos" : [6,7],
        "col" : yellow},       
    "DSKY STANDBY" : {
        "pos" : [10,11],
        "col" : white},
    "PROG" : {
        "pos" : [8,9],
        "col" : yellow},
    "KEY REL" : {
        "pos" : [12,13],
        "col" : white},
    "RESTART" : {
        "pos" : [14,15],
        "col" : yellow},
    "OPR ERR" : {
        "pos" : [18,19],
        "col" : white},
    "TRACKER" : {
        "pos" : [16,17],
        "col" : yellow},
    "PRIO DSP" : {
        "pos" : [20,21],
        "col" : white},
    "ALT" : {
        "pos" : [22,23],
        "col" : yellow},
    "NO DAP" : {
        "pos" : [26,27],
        "col" : white},
    "VEL" : {
        "pos" : [24,25],
        "col" : yellow}
        }

# The number of NeoPixels
num_pixels = 28
ORDER = neopixel.GRB

pixels = neopixel.NeoPixel(
    pixel_pin, num_pixels, brightness=0.8, auto_write=False, pixel_order=ORDER
)

# define serial comms to Nextion - port may need changing if different on your Pi.
# The port is opened once and kept open (opening/closing it for every write was slow).
ser = serial.Serial(port='/dev/ttyS0', baudrate=9600, timeout=0.1, write_timeout=2)
NEXTION_EOF = b'\xff\xff\xff'

# Last value sent to each Nextion object, so that repeated identical updates from
# the AGC (which are very common) don't cost serial bandwidth.
nextionCache = {}

def nextion_send(cmd, cacheKey=None, cacheValue=None):
    if cacheKey is not None:
        if nextionCache.get(cacheKey) == cacheValue:
            return
        nextionCache[cacheKey] = cacheValue
    ser.write(cmd.encode() + NEXTION_EOF)

# subroutine to send something to nextion
def nextion(command, arg):
    nextion_send(command + '.txt="' + arg + '"', command, arg)

#  subroutine to dim the nextion
def nextion_dim(arg):
    nextion_send('dim=' + str(arg))

# subroutine to update the 'comp acty' light on nextion
def nextion_compacty(status):
    if str(status) == "0":
        nextion_send("comp_acty.pic=2", "comp_acty", 0)
    elif str(status) == "1":
        nextion_send("comp_acty.pic=3", "comp_acty", 1)

# subroutine to blink the verb / noun digits
def nextion_vn_blink(status):
    if status in (0, 1):
        nextion_send("vn_blink_true.val=" + str(status), "vn_blink", status)

DIGIT_FIELDS = ["VERB1", "VERB2", "NOUN1", "NOUN2", "PROG1", "PROG2"]
SIGN_FIELDS = ["R1_1", "R2_1", "R3_1"]
REGISTER_FIELDS = ["R%d_%d" % (r, d) for r in (1, 2, 3) for d in range(1, 7)]

#  subroutine to clear down the nextion
def nextion_clearscreen():
    nextion_compacty(0)
    for f in DIGIT_FIELDS + REGISTER_FIELDS:
        nextion(f, " ")
    ser.flush()

# subroutine to test nextion (light up all digits / lights)
def nextion_testscreen():
    for f in DIGIT_FIELDS + REGISTER_FIELDS:
        nextion(f, "+" if f in SIGN_FIELDS else "8")
    ser.flush()

print("Display will be dimmned")
nextion_dim(20)
sleep(0.1)

print("Display will be tested")
nextion_testscreen()
sleep(0.1)

print("Display will be cleared")
nextion_clearscreen()

# IDLE at start, show time
# set variable to check if a key has been pressed, if yes, stop the idle clock process and start behaving like a proper DSKY
keypressed = 0
# should the idle clock run? On Program Start and until a key has been pressed
idleclock = 1

idleclock_hour = "00"
idleclock_hour_old = "00"
idleclock_minute = "00"
idleclock_minute_old = "00"
idleclock_second = "00"
idleclock_second_old = "00"
temp_minute = "00"
temp_minute_old = "00"
temp_minute_ntp = "00"
temp_minute_old_ntp = "00"

#print (f'keypressed {keypressed} {type(keypressed)} idleclock {idleclock} {type(idleclock)}')

vnFlashing = False

# Responsiveness settings.
if args.slow:
    PULSE = 0.25
    lampDeadtime = 0.25
else:
    PULSE = 0.05
    lampDeadtime = 0.1

# Characteristics of the host and port being used for yaAGC communications.  
if args.host:
    TCP_IP = args.host
else:
    TCP_IP = 'localhost'
if args.port:
    TCP_PORT = args.port
else:
    TCP_PORT = 19797

###################################################################################
# Some utilities I happen to use in my sample hardware abstraction functions, but
# not of value outside of that, unless you happen to be implementing DSKY functionality
# in a similar way.

# Given a 3-tuple (channel,value,mask), creates packet data and sends it to yaAGC.
def packetize(tuple):
    outputBuffer = bytearray(4)
    # First, create and output the mask command.
    outputBuffer[0] = 0x20 | ((tuple[0] >> 3) & 0x0F)
    outputBuffer[1] = 0x40 | ((tuple[0] << 3) & 0x38) | ((tuple[2] >> 12) & 0x07)
    outputBuffer[2] = 0x80 | ((tuple[2] >> 6) & 0x3F)
    outputBuffer[3] = 0xC0 | (tuple[2] & 0x3F)
    s.sendall(outputBuffer)
    # Now, the actual data for the channel.
    outputBuffer[0] = 0x00 | ((tuple[0] >> 3) & 0x0F)
    outputBuffer[1] = 0x40 | ((tuple[0] << 3) & 0x38) | ((tuple[1] >> 12) & 0x07)
    outputBuffer[2] = 0x80 | ((tuple[1] >> 6) & 0x3F)
    outputBuffer[3] = 0xC0 | (tuple[1] & 0x3F)
    s.sendall(outputBuffer)

# This particular function parses various keystrokes, like '0' or 'V' and creates
# packets as if they were DSKY keypresses.  It should be called occasionally as
# parseDskyKey(0) if there are no keystrokes, in order to make sure that the PRO
# key gets released.  

# The return value of this function is
# a list ([...]), of which each element is a 3-tuple consisting of an AGC channel
# number, a value for that channel, and a bitmask that tells which bit-positions
# of the value are valid.  The returned list can be empty.  For example, a
# return value of 
#	[ ( 0o15, 0o31, 0o37 ) ]
# would indicate that the lowest 5 bits of channel 15 (octal) were valid, and that
# the value of those bits were 11001 (binary), which collectively indicate that
# the KEY REL key on a DSKY is pressed.
# (The original "press RSET 5 times to exit" behaviour has been removed: on a
# standalone DSKY it just killed the program when RSET was pressed repeatedly.)
def parseDskyKey(ch):
    returnValue = []
    if ch == '0':
        returnValue.append( (0o15, 0o20, 0o37) )
    elif ch == '1':
        returnValue.append( (0o15, 0o1, 0o37) )
    elif ch == '2':
            returnValue.append( (0o15, 0o2, 0o37) )
    elif ch == '3':
            returnValue.append( (0o15, 0o3, 0o37) )
    elif ch == '4':
            returnValue.append( (0o15, 0o4, 0o37) )
    elif ch == '5':
            returnValue.append( (0o15, 0o5, 0o37) )
    elif ch == '6':
            returnValue.append( (0o15, 0o6, 0o37) )
    elif ch == '7':
            returnValue.append( (0o15, 0o7, 0o37) )
    elif ch == '8':
            returnValue.append( (0o15, 0o10, 0o37) )
    elif ch == '9':
            returnValue.append( (0o15, 0o11, 0o37) )
    elif ch == '+':
            returnValue.append( (0o15, 0o32, 0o37) )
    elif ch == '-':
            returnValue.append( (0o15, 0o33, 0o37) )
    elif ch == 'V':
            returnValue.append( (0o15, 0o21, 0o37) )
    elif ch == 'N':
            returnValue.append( (0o15, 0o37, 0o37) )
    elif ch == 'R':
            returnValue.append( (0o15, 0o22, 0o37) )
    elif ch == 'C':
            returnValue.append( (0o15, 0o36, 0o37) )
    elif ch == 'P':
            returnValue.append( (0o32, 0o00000, 0o20000) )
    elif ch == 'p' or ch == 'PR':
            returnValue.append( (0o32, 0o20000, 0o20000) )
    elif ch == 'K':
            returnValue.append( (0o15, 0o31, 0o37) )
    elif ch == 'E':
        returnValue.append( (0o15, 0o34, 0o37) )
    return returnValue	

# Keyboard input.  Keys can come from two places:
#  * the Pico 2 keypad, read directly from its /dev/input event device with evdev
#    (no terminal or window focus needed, so this works under systemd), and
#  * the controlling terminal's stdin (handy for bench testing over SSH).
stdinIsTty = sys.stdin is not None and sys.stdin.isatty()
useStdin = args.keyboard in ("auto", "stdin") and stdinIsTty
usePico = args.keyboard in ("auto", "pico")
if usePico and evdev is None:
    print("python3-evdev is not installed; cannot read the Pico keypad directly")
    usePico = False

# This function turns keyboard echo on or off.
def echoOn(control):
    if not stdinIsTty:
        return
    fd = sys.stdin.fileno()
    new = termios.tcgetattr(fd)
    if control:
        print("Keyboard echo on")
        new[3] |= termios.ECHO
    else:
        print("Keyboard echo off")
        new[3] &= ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, new)
echoOn(False)

pressedPRO = False
timePRO = 0

# Map of Linux key codes (as sent by the Pico's CircuitPython keymap, or any USB
# keyboard) to the characters used by parseDskyKey().
PICO_KEYMAP = {}
if evdev is not None:
    ec = evdev.ecodes
    for d in range(10):
        PICO_KEYMAP[getattr(ec, "KEY_%d" % d)] = str(d)
        PICO_KEYMAP[getattr(ec, "KEY_KP%d" % d)] = str(d)
    for letter in "VNCEPRK":
        PICO_KEYMAP[getattr(ec, "KEY_" + letter)] = letter
    PICO_KEYMAP.update({
        ec.KEY_KPPLUS: '+', ec.KEY_EQUAL: '+',
        ec.KEY_KPMINUS: '-', ec.KEY_MINUS: '-',
        ec.KEY_ENTER: 'E', ec.KEY_KPENTER: 'E',
    })

picoDevice = None
picoNextScan = 0
keyQueue = collections.deque()

def pollPico():
    # Open the Pico keypad if necessary (it disappears for a moment when it is
    # reset via GPIO 23 at startup, or if it is unplugged), then queue any keys.
    global picoDevice, picoNextScan
    if picoDevice is None:
        if time.time() < picoNextScan:
            return
        picoNextScan = time.time() + 2
        paths = sorted(glob.glob(args.pico_glob))
        if not paths:
            return
        try:
            picoDevice = evdev.InputDevice(paths[0])
            try:
                # Exclusive access, so keypresses don't also go to the desktop/console.
                picoDevice.grab()
            except OSError:
                pass
            print("Reading keypad from " + paths[0] + " (" + picoDevice.name + ")")
        except OSError as e:
            print("Could not open keypad " + paths[0] + ": " + str(e))
            picoDevice = None
            return
    try:
        while True:
            event = picoDevice.read_one()
            if event is None:
                break
            if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                ch = PICO_KEYMAP.get(event.code)
                if ch is not None:
                    keyQueue.append(ch)
    except OSError as e:
        print("Lost keypad device: " + str(e))
        try:
            picoDevice.close()
        except Exception:
            pass
        picoDevice = None

def readStdinChar():
    fd = sys.stdin.fileno()
    oldterm = termios.tcgetattr(fd)
    newattr = termios.tcgetattr(fd)
    newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, newattr)
    oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)
    c = ""
    try:
            c = sys.stdin.read(1) or ""
    except IOError: pass
    termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
    fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
    return c

# This function is a non-blocking read of a single key.  Returns either the
# key value (such as '0' or 'V'), or else the value "" if no key was pressed.
# Note:  fakes a "key" 'PR' 0.75 seconds after a key 'p' or 'P'.  This is in
# lieu of PRO press and release events (the Pico sends press+release at once).
def get_char_keyboard_nonblock():
    global pressedPRO, timePRO, keypressed
    if usePico:
        pollPico()
    c = ""
    if keyQueue:
        c = keyQueue.popleft()
    elif useStdin:
        c = readStdinChar()
    if c == 'p' or c == 'P':
        pressedPRO = True
        timePRO = time.time()
    if c == "" and pressedPRO and time.time() > timePRO + 0.75:
        pressedPRO = False
        c = 'PR'
    if c != "" and c != 'PR':
        keypressed = 1
    return c

# The following dictionary gives, for each indicator lamp:
# Whether or not it is currently lit. This is used by the lamp update routine to determine what should be displayed
lampStatuses = {
    "UPLINK ACTY" 	: { "isLit" : False },
    "TEMP" 			: { "isLit" : False },
    "NO ATT" 		: { "isLit" : False },
    "GIMBAL LOCK" 	: { "isLit" : False },
    "DSKY STANDBY" 	: { "isLit" : False },
    "PROG" 			: { "isLit" : False },
    "KEY REL" 		: { "isLit" : False },
    "RESTART" 		: { "isLit" : False },
    "OPR ERR" 		: { "isLit" : False },
    "TRACKER" 		: { "isLit" : False },
    "PRIO DSP" 		: { "isLit" : False },
    "ALT" 			: { "isLit" : False },
    "NO DAP" 		: { "isLit" : False },
    "VEL" 			: { "isLit" : False }
}

# For modifying the lampStatuses[] array.
def updateLampStatuses(key, value):
    global lampStatuses
    if key in lampStatuses:
        lampStatuses[key]["isLit"] = value

# Converts a 5-bit code in channel 010 to " ", "0", ..., "9".
def codeToString(code):
    if code == 0:
        return " "
    elif code == 21:
        return "0"
    elif code == 3:
        return "1"
    elif code == 25:
        return "2"
    elif code == 27:
        return "3"
    elif code == 15:
        return "4"
    elif code == 30:
        return "5"
    elif code == 28:
        return "6"
    elif code == 19:
        return "7"
    elif code == 29:
        return "8"
    elif code == 31:
        return "9"
    return "?"

###################################################################################
# Hardware abstraction / User-defined functions.  Also, any other platform-specific
# initialization.

# This function is automatically called periodically by the event loop to check for 
# conditions that will result in sending messages to yaAGC that are interpreted
# as changes to bits on its input channels.  For test purposes, it simply polls the
# keyboard, and interprets various keystrokes as DSKY keys if present.  The return
# value is supposed to be a list of 3-tuples of the form
#	[ (channel0,value0,mask0), (channel1,value1,mask1), ...]
# and may be en empty list.  
# Local keypad commands.  These are caught here and never sent to the AGC:
#   V98E  arm shutdown - all lamps blink; press PRO within SHUTDOWN_WINDOW
#         seconds to power off.  Any other key, or the timeout, cancels.
#   V94E  return to the idle clock (as does --idle-minutes without a keypress).
# Sending them to the AGC would make it blank the display (it does that for
# every extended verb) and light OPR ERR, so a V is held back until the
# following keys show whether it starts one of these commands.  If not, the
# held keys are passed on in order.
LOCAL_COMMANDS = {"V98E": "shutdown", "V94E": "clock"}
IDLE_TIMEOUT = args.idle_minutes * 60
lastKeyTime = time.time()
SHUTDOWN_WINDOW = 5.0
heldKeys = []
# Keys waiting to go to yaAGC.  Only one is sent per pass of the event loop
# (about 50 ms apart): two keystrokes arriving at once can lose the first.
sendQueue = collections.deque()
shutdownArmedUntil = 0
shutdownBlink = False

def isCommandPrefix(keys):
    seq = "".join(keys)
    return any(cmd.startswith(seq) for cmd in LOCAL_COMMANDS)

def handleKey(ch):
    # Hold, pass on, or act on one keypress.
    global heldKeys, shutdownArmedUntil
    candidate = "".join(heldKeys) + ch
    if candidate in LOCAL_COMMANDS:
        heldKeys = []
        if LOCAL_COMMANDS[candidate] == "shutdown":
            print("V98E: press PRO within %g s to shut down, any other key cancels" % SHUTDOWN_WINDOW)
            shutdownArmedUntil = time.time() + SHUTDOWN_WINDOW
        else:
            enterClockMode("V94E")
        return
    if isCommandPrefix(heldKeys + [ch]):
        heldKeys.append(ch)
        return
    # Not a local command: pass the held keys on, then deal with this key
    # (which may itself start a new command, e.g. a second V).
    sendQueue.extend(heldKeys)
    heldKeys = []
    if isCommandPrefix([ch]):
        heldKeys = [ch]
    else:
        sendQueue.append(ch)

def shutdownNow():
    global shutdownArmedUntil, shutdownBlink
    print("Shutdown confirmed from keypad; powering off")
    shutdownArmedUntil = 0
    shutdownBlink = False
    for key in lampStatuses:
        lampStatuses[key]["isLit"] = False
    pixels.fill(black)
    pixels.show()
    nextion_vn_blink(0)
    nextion_clearscreen()
    subprocess.run(["systemctl", "poweroff"])

def shutdownTick():
    # Called every pass of the event loop: blink lamps while armed, handle timeout.
    global shutdownArmedUntil, shutdownBlink
    if shutdownArmedUntil == 0:
        return
    if time.time() > shutdownArmedUntil:
        print("Keypad shutdown cancelled (timeout)")
        shutdownArmedUntil = 0
        shutdownBlink = False
        updateLamps()
        return
    blink = int(time.time() * 4) % 2 == 0
    if blink != shutdownBlink:
        shutdownBlink = blink
        updateLamps()

def inputsForAGC():
    global shutdownArmedUntil, shutdownBlink, lastKeyTime, heldKeys
    shutdownTick()
    if IDLE_TIMEOUT > 0 and time.time() - lastKeyTime > IDLE_TIMEOUT:
        enterClockMode("no keypress for %g min" % args.idle_minutes)
        return []
    ch = get_char_keyboard_nonblock()
    ch = ch.upper()
    if ch == '_':
        ch = '-'
    elif ch == '=':
        ch = '+'
    if ch == 'PR':
        # Synthetic PRO release; keep it in order behind any queued keys.
        sendQueue.append(ch)
    elif ch != "":
        lastKeyTime = time.time()
        if shutdownArmedUntil != 0:
            if ch == 'P':
                shutdownNow()
                return []
            print("Keypad shutdown cancelled")
            shutdownArmedUntil = 0
            shutdownBlink = False
            updateLamps()
        handleKey(ch)
    if idleclock != 2 or not sendQueue:
        return []
    returnValue = parseDskyKey(sendQueue.popleft())
    if len(returnValue) > 0:
            print(f'Sending to yaAGC non-Oct: {returnValue[0][1]} mask  {returnValue[0][2]} -> channel {returnValue[0][0]}')
            print("Sending to yaAGC     Oct: " + oct(returnValue[0][1]) + "(mask " + oct(returnValue[0][2]) + ") -> channel " + oct(returnValue[0][0]))
    return returnValue

# Copy of what the AGC last put on the Nextion, so it can be redrawn after the
# clock has been shown.  While the clock is showing (idleclock != 2), AGC
# output is still read and recorded here but not drawn.
agcShadow = {}

def agcDisplayActive():
    return idleclock == 2

def agcNextion(field, value):
    agcShadow[field] = value
    if agcDisplayActive():
        nextion(field, value)

def agcCompActy(status):
    agcShadow["_compacty"] = str(status)
    if agcDisplayActive():
        nextion_compacty(status)

def agcVnBlink(status):
    agcShadow["_vnblink"] = status
    if agcDisplayActive():
        nextion_vn_blink(status)

def agcRedraw():
    for field, value in agcShadow.items():
        if not field.startswith("_"):
            nextion(field, value)
    nextion_compacty(agcShadow.get("_compacty", "0"))
    nextion_vn_blink(agcShadow.get("_vnblink", 0))
    updateLamps()

# True while the AGC has the DSKY lamp-test bit (channel 13, bit 10) set, e.g.
# during V35E.  All indicator lamps are lit while it is set.
dskyTest = False

def updateLamps():
    # set the neopixels in the inicator panel dependant on the
    # lamp status values.  The strip is written once per call (auto_write is off).
    for key in lampStatuses:
        if not agcDisplayActive():
            for x in lamps[key]["pos"]:
                pixels[x] = black
        elif lampStatuses[key]["isLit"] or dskyTest or shutdownBlink:
            for x in lamps[key]["pos"]:
                pixels[x] = lamps[key]["col"]
        else:
            for x in lamps[key]["pos"]:
                pixels[x] = black
    pixels.show()
    return

updateLamps()

last10 = 1234567
last11 = 1234567
last13 = 1234567
last163 = 1234567
plusMinusState1 = 0
plusMinusState2 = 0
plusMinusState3 = 0

# This function is called by the event loop only when yaAGC has written
# to an output channel.  The function should do whatever it is that needs to be done
# with this output data, which is not processed additionally in any way by the 
# generic portion of the program. As a test, I simply display the outputs for 
# those channels relevant to the DSKY.

def signChar(state):
    if state == 1:
        return "+"
    if state == 2:
        return "-"
    return " "

def outputFromAGC(channel, value):
    # These lastNN values are just used to cut down on the number of messages printed,
    # when the same value is output over and over again to the same channel, because
    # that makes debugging harder.  
    global last10, last11, last13, last163, plusMinusState1, plusMinusState2, plusMinusState3, vnFlashing, dskyTest
    if (channel == 0o13):
        value &= 0o3000
    if (channel == 0o10 and value != last10) or (channel == 0o11 and value != last11) or (channel == 0o13 and value != last13) or (channel == 0o163 and value != last163):
        if channel == 0o10:
            last10 = value
            aaaa = (value >> 11) & 0x0F
            b = (value >> 10) & 0x01
            ccccc = (value >> 5) & 0x1F
            ddddd = value & 0x1F
            if aaaa != 12:
                sc = codeToString(ccccc)
                sd = codeToString(ddddd)
            if aaaa == 11:
                print(sc + " -> M1   " + sd + " -> M2")
                agcNextion("PROG1", sc)
                agcNextion("PROG2", sd)
            elif aaaa == 10:
                print(sc + " -> V1   " + sd + " -> V2")
                agcNextion("VERB1", sc)
                agcNextion("VERB2", sd)
            elif aaaa == 9:
                print(sc + " -> N1   " + sd + " -> N2")
                agcNextion("NOUN1", sc)
                agcNextion("NOUN2", sd)
            elif aaaa == 8:
                print("          " + sd + " -> 11")
                agcNextion("R1_2", sd)
            elif aaaa == 7:
                plusMinus = "  "
                if b != 0:
                    plusMinus = "1+"
                    plusMinusState1 |= 1
                else:
                    plusMinusState1 &= ~1
                # 
                agcNextion("R1_1", signChar(plusMinusState1))
                print(sc + " -> 12   " + sd + " -> 13   " + plusMinus  + str(plusMinusState1))
                agcNextion("R1_3", sc)
                agcNextion("R1_4", sd)
            elif aaaa == 6:
                plusMinus = "  "
                if b != 0:
                    plusMinus = "1-"
                    plusMinusState1 |= 2
                else:
                    plusMinusState1 &= ~2

                agcNextion("R1_1", signChar(plusMinusState1))
                print(sc + " -> 14   " + sd + " -> 15   " + plusMinus + str(plusMinusState1))
                agcNextion("R1_5", sc)
                agcNextion("R1_6", sd)
            elif aaaa == 5:
                plusMinus = "  "
                if b != 0:
                    plusMinus = "2+"
                    plusMinusState2 |= 1
                else:
                    plusMinusState2 &= ~1
                agcNextion("R2_1", signChar(plusMinusState2))
                print(sc + " -> 21   " + sd + " -> 22   " + plusMinus + str(plusMinusState2))
                agcNextion("R2_2", sc)
                agcNextion("R2_3", sd)
            elif aaaa == 4:
                plusMinus = "  "
                if b != 0:
                    plusMinus = "2-"
                    plusMinusState2 |= 2
                else:
                    plusMinusState2 &= ~2
                agcNextion("R2_1", signChar(plusMinusState2))
                print(sc + " -> 23   " + sd + " -> 24   " + plusMinus + str(plusMinusState2))
                agcNextion("R2_4", sc)
                agcNextion("R2_5", sd)
            elif aaaa == 3:
                print(sc + " -> 25   " + sd + " -> 31")
                agcNextion("R2_6", sc)
                agcNextion("R3_2", sd)
            elif aaaa == 2:
                plusMinus = "  "
                if b != 0:
                    plusMinus = "3+"
                    plusMinusState3 |= 1
                else:
                    plusMinusState3 &= ~1
                agcNextion("R3_1", signChar(plusMinusState3))
                print(sc + " -> 32   " + sd + " -> 33   " + plusMinus + str(plusMinusState3))
                agcNextion("R3_3", sc)
                agcNextion("R3_4", sd)
            elif aaaa == 1:
                plusMinus = "  "
                if b != 0:
                    plusMinus = "3-"
                    plusMinusState3 |= 2
                    #agcNextion("R3_1", "-")
                else:
                    plusMinusState3 &= ~2
                    #agcNextion("R3_1", " ")
                agcNextion("R3_1", signChar(plusMinusState3))
                print(sc + " -> 34   " + sd + " -> 35   " + plusMinus + str(plusMinusState3))
                agcNextion("R3_5", sc)
                agcNextion("R3_6", sd)
            elif aaaa == 12:
                vel = "VEL OFF         "
                if (value & 0x04) != 0:
                    vel = "VEL ON          "
                    updateLampStatuses("VEL", True)
                else:
                    updateLampStatuses("VEL", False)

                noAtt = "NO ATT OFF      "
                if (value & 0x08) != 0:
                    noAtt = "NO ATT ON       "
                    updateLampStatuses("NO ATT", True)
                else:
                    updateLampStatuses("NO ATT", False)

                alt = "ALT OFF         "
                if (value & 0x10) != 0:
                    alt = "ALT ON          "
                    updateLampStatuses("ALT", True)
                else:
                    updateLampStatuses("ALT", False)

                gimbalLock = "GIMBAL LOCK OFF "
                if (value & 0x20) != 0:
                    gimbalLock = "GIMBAL LOCK ON  "
                    updateLampStatuses("GIMBAL LOCK", True)
                else:
                    updateLampStatuses("GIMBAL LOCK", False)

                tracker = "TRACKER OFF     "
                if (value & 0x80) != 0:
                    tracker = "TRACKER ON      "
                    updateLampStatuses("TRACKER", True)
                else:
                    updateLampStatuses("TRACKER", False)

                prog = "PROG OFF        "
                if (value & 0x100) != 0:
                    prog = "PROG ON         "
                    updateLampStatuses("PROG", True)
                else:
                    updateLampStatuses("PROG", False)

                updateLamps()
        elif channel == 0o11:
            last11 = value
            compActy = "COMP ACTY OFF   "
            if (value & 0x02) != 0:
                compActy = "COMP ACTY ON    "
                agcCompActy("1")
            else:
                agcCompActy("0")
                
            uplinkActy = "UPLINK ACTY OFF "
            if (value & 0x04) != 0:
                uplinkActy = "UPLINK ACTY ON  "
                updateLampStatuses("UPLINK ACTY", True)
            else:
                updateLampStatuses("UPLINK ACTY", False)
 
            flashing = "V/N NO FLASH    "
            if (value & 0x20) != 0:
                if not vnFlashing:
                    vnFlashing = True
                    flashing = "V/N FLASH       "
                    agcVnBlink(1)
            else:
                if vnFlashing != False:
                    vnFlashing = False
                    agcVnBlink(0)

            updateLamps()
        elif channel == 0o13:
            last13 = value
            test = "DSKY TEST       "
            dskyTest = (value & 0x200) != 0
            if not dskyTest:
                test = "DSKY NO TEST    "
            print(test)
            updateLamps()
        elif channel == 0o163:
            last163 = value
            if (value & 0x08) != 0:
                temp = "TEMP ON         "
                updateLampStatuses("TEMP", True)
            else:
                temp = "TEMP OFF        "
                updateLampStatuses("TEMP", False)

            if (value & 0o400) != 0:
                standby = "DSKY STANDBY ON "
                updateLampStatuses("DSKY STANDBY", True)
            else:
                standby = "DSKY STANDBY OFF"
                updateLampStatuses("DSKY STANDBY", False)

            if (value & 0o20) != 0:
                keyRel = "KEY REL ON      "
                updateLampStatuses("KEY REL", True)
            else:
                keyRel = "KEY REL OFF     "
                updateLampStatuses("KEY REL", False)

            if (value & 0o100) != 0:
                oprErr = "OPR ERR FLASH   "
                updateLampStatuses("OPR ERR", True)
            else:
                oprErr = "OPR ERR OFF     "
                updateLampStatuses("OPR ERR", False)

            if (value & 0o200) != 0:
                restart = "RESTART ON    "
                updateLampStatuses("RESTART", True)
            else:
                restart = "RESTART OFF     "
                updateLampStatuses("RESTART", False)
            updateLamps()

        else:
            print("Received from yaAGC: " + oct(value) + " -> channel " + oct(channel))
    return

###################################################################################
# Generic initialization (TCP socket setup).  Has no target-specific code, and 
# shouldn't need to be modified unless there are bugs.

s = None

def resetDisplayState():
    # Forget everything we think we know about the AGC's outputs, so that the
    # next values it sends are always written to the display.
    global last10, last11, last13, last163, plusMinusState1, plusMinusState2, plusMinusState3
    global vnFlashing, dskyTest
    last10 = last11 = last13 = last163 = 1234567
    plusMinusState1 = plusMinusState2 = plusMinusState3 = 0
    vnFlashing = False
    dskyTest = False

# Connects to yaAGC, retrying until it succeeds.  A brand-new socket is created for
# every attempt: a socket whose connect() has failed cannot be reused, which is why
# the old version never recovered once yaAGC wasn't there at the first attempt.
def connectToAGC():
    global s
    if s is not None:
        try:
            s.close()
        except OSError:
            pass
        s = None
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((TCP_IP, TCP_PORT))
        except OSError as msg:
            sock.close()
            print("Could not connect to yaAGC (" + TCP_IP + ":" + str(TCP_PORT) + "), retrying: " + str(msg))
            # Keep the keypad drained while waiting, but ignore what is pressed.
            deadline = time.time() + 1
            while time.time() < deadline:
                get_char_keyboard_nonblock()
                time.sleep(0.05)
            continue
        sock.setblocking(False)
        s = sock
        print("Connected to yaAGC (" + TCP_IP + ":" + str(TCP_PORT) + ")")
        resetDisplayState()
        nextion_vn_blink(0)
        updateLamps()
        return

connectToAGCneeded = 0
#connectToAGC()

###################################################################################
# Event loop.  Just check periodically for output from yaAGC (in which case the
# user-defined callback function outputFromAGC is executed) or data in the 
# user-defined function inputsForAGC (in which case a message is sent to yaAGC).
# But this section has no target-specific code, and shouldn't need to be modified
# unless there are bugs.
old_week = "00"
old_year = "0000"
old_month = "00"
old_day = "00"
old_hour = "00"
old_minute = "00"
old_second = "00"
old_millisecond = "0"
old_millisecond2 = "0"

def enterClockMode(reason):
    global keypressed, idleclock, shutdownArmedUntil, shutdownBlink, heldKeys
    global old_week, old_year, old_month, old_day, old_hour, old_minute, old_second
    global old_millisecond, old_millisecond2
    print("Returning to clock (" + reason + ")")
    keypressed = 0
    idleclock = 1
    shutdownArmedUntil = 0
    shutdownBlink = False
    heldKeys = []
    sendQueue.clear()
    # Force the clock to repaint every field.
    old_week = old_year = old_month = old_day = old_hour = old_minute = old_second = ""
    old_millisecond = old_millisecond2 = ""
    nextion_vn_blink(0)
    nextion_clearscreen()
    updateLamps()

def clock():
    global keypressed, idleclock, old_week, old_year, old_month, old_day, old_hour, old_minute, old_second, old_millisecond, old_millisecond2, lastKeyTime
    if keypressed == 0 and idleclock == 1:

        now = datetime.now() # current date and time
        week = now.strftime("%W")
        if (old_week != week):
            nextion("PROG1", week[0])
            nextion("PROG2", week[1])
            old_week = week
        year = now.strftime("%Y")
        if (old_year != year):
            nextion("VERB1", year[0])
            nextion("VERB2", year[1])
            nextion("NOUN1", year[2])
            nextion("NOUN2", year[3])
            old_year = year

        month = now.strftime("%m")
        if (old_month != month):
            nextion("R1_5", month[0])
            nextion("R1_6", month[1])
            old_month = month

        day = now.strftime("%d")
        if (old_day != day):
            nextion("R1_2", day[0])
            nextion("R1_3", day[1])
            old_day = day
        
        hour = now.strftime("%H")        
        if (old_hour != hour):
            nextion("R2_2", hour[0])
            nextion("R2_3", hour[1])
            old_hour = hour
        
        minute = now.strftime("%M")
        if (old_minute != minute):
            nextion("R2_5", minute[0])
            nextion("R2_6", minute[1])
            old_minute = minute

        second = now.strftime("%S")
        if (old_second != second):
            nextion("R3_2", second[0])
            nextion("R3_3", second[1])
            old_second = second
        
        millisecond = now.strftime("%f")
        if (old_millisecond != millisecond[0]):
            nextion("R3_5", millisecond[0])
            old_millisecond = millisecond[0]

        if (old_millisecond2 != millisecond[1]):
            nextion("R3_6", millisecond[1])
            old_millisecond2 = millisecond[1]


        get_char_keyboard_nonblock()
        time.sleep(0.1)

    elif keypressed == 1 and idleclock == 1:
        print (f'keypressed {keypressed} {type(keypressed)} idleclock {idleclock} {type(idleclock)}')
        print("Display will be cleared")
        nextion_clearscreen()
        get_char_keyboard_nonblock()
        idleclock = 2
        lastKeyTime = time.time()
        if s is not None:
            # Already connected (coming back from the clock): restore the AGC display.
            agcRedraw()

def gettemperature():
    global temp_minute, temp_minute_old
    now_temp = datetime.now() # current date and time
    temp_minute = now_temp.strftime("%M")
    if temp_minute[1] !=  temp_minute_old[1]:
        #print("temp 1 minute check")
        #
        temp_minute_old = temp_minute
        try:
            f = open("/sys/class/thermal/thermal_zone0/temp", "r")
            pitemp = f.read()
            #f2 = open("/sys/class/thermal/cooling_device0/cur_state", "r")
            #pifan = f2.read()
        except:
            print("could not open file")
        pifan0 ='0'
        pifan1 ='1'
#         if pifan[0] == pifan1:
#             pixels[p_temp] = yellow
#         elif pifan[0] == pifan0:
#             pixels[p_temp] = black
    #print(f'pifan {pifan} {type(pifan)}')
    #print(f'pitemp {pitemp} {type(pitemp)}')


# https://www.geeksforgeeks.org/python-execute-and-parse-linux-commands/
# https://www.cyberciti.biz/faq/linux-unix-bsd-is-ntp-client-working/
def check_ntp(args = '-c rv'):
    global temp_minute_ntp, temp_minute_old_ntp
    now_temp = datetime.now() # current date and time
    temp_minute_ntp = now_temp.strftime("%M")
    if temp_minute_ntp[1] !=  temp_minute_old_ntp[1]:
        temp_minute_old_ntp = temp_minute_ntp
    
        cmd = 'ntpq'
        temp = subprocess.Popen([cmd, args], stdout = subprocess.PIPE)
        output = str(temp.communicate())
        temp.kill()
        output = output.split('\n')
        output = output[0].split('\\')
        res = []
        for line in output:
            res.append(line)
        #print(res[0])
        sync = []
        sync = res[0].split(' ')
        #print(sync[2])
        sync2 = []
        sync2 = sync[2].split(',')
        #print(sync2[0])
#         if sync2[0] == "leap_alarm":
#             pixels[p_tracker] = yellow
#         elif sync2[0] == "leap_none":
#             pixels[p_tracker] = black


# Buffer for a packet received from yaAGC.
packetSize = 4
inputBuffer = bytearray(packetSize)
leftToRead = packetSize
view = memoryview(inputBuffer)

def resetPacketBuffer():
    global view, leftToRead
    view = memoryview(inputBuffer)
    leftToRead = packetSize

# Reads whatever yaAGC has sent and passes complete packets to outputFromAGC().
# Returns True if anything was read.  If the connection is lost: with
# reconnect=True, reconnects (blocking until yaAGC is back); otherwise just
# drops the socket so the next wake from the clock reconnects.
def pollAGC(reconnect=True):
    global view, leftToRead, s, connectToAGCneeded
    didSomething = False
    while True:
        # While these packets are always exactly 4 bytes long, since the socket
        # is non-blocking, any individual read operation may yield less bytes
        # than that, so the buffer may accumulate data over time until it fills.
        try:
            numNewBytes = s.recv_into(view, leftToRead)
            if numNewBytes == 0:
                raise ConnectionResetError("yaAGC closed the connection")
        except (BlockingIOError, InterruptedError):
            return didSomething
        except OSError as e:
            print("Lost connection to yaAGC: " + str(e))
            resetPacketBuffer()
            if reconnect:
                connectToAGC()
            else:
                try:
                    s.close()
                except OSError:
                    pass
                s = None
                connectToAGCneeded = 0
            return True
        didSomething = True
        view = view[numNewBytes:]
        leftToRead -= numNewBytes
        if leftToRead != 0:
            continue
        # Prepare for next read attempt.
        resetPacketBuffer()
        # Parse the packet just read, and call outputFromAGC().
        # Start with a sanity check.
        ok = 1
        if (inputBuffer[0] & 0xF0) != 0x00:
            ok = 0
        elif (inputBuffer[1] & 0xC0) != 0x40:
            ok = 0
        elif (inputBuffer[2] & 0xC0) != 0x80:
            ok = 0
        elif (inputBuffer[3] & 0xC0) != 0xC0:
            ok = 0
        # Packet has the various signatures we expect.
        if ok == 0:
            # Note that, depending on the yaAGC version, it occasionally
            # sends either a 1-byte packet (just 0xFF, older versions)
            # or a 4-byte packet (0xFF 0xFF 0xFF 0xFF, newer versions)
            # just for pinging the client.  These packets hold no
            # data and need to be ignored, but for other corrupted packets
            # we print a message. And try to realign past the corrupted
            # bytes.
            if inputBuffer[0] != 0xff or inputBuffer[1] != 0xff or inputBuffer[2] != 0xff or inputBuffer[3] != 0xff:
                if inputBuffer[0] != 0xff:
                    print("Illegal packet: " + hex(inputBuffer[0]) + " " + hex(inputBuffer[1]) + " " + hex(inputBuffer[2]) + " " + hex(inputBuffer[3]))
                for i in range(1,packetSize):
                    if (inputBuffer[i] & 0xF0) == 0:
                        j = 0
                        for k in range(i,4):
                            inputBuffer[j] = inputBuffer[k]
                            j += 1
                        view = view[j:]
                        leftToRead = packetSize - j
                        break
        else:
            channel = (inputBuffer[0] & 0x0F) << 3
            channel |= (inputBuffer[1] & 0x38) >> 3
            value = (inputBuffer[1] & 0x07) << 12
            value |= (inputBuffer[2] & 0x3F) << 6
            value |= (inputBuffer[3] & 0x3F)
            outputFromAGC(channel, value)

def eventLoop():
    global keypressed, idleclock, connectToAGCneeded
    didSomething = False
    while True:

        if idleclock == 1:
            # Showing the clock.  If we're already connected to yaAGC (i.e. we came
            # back to the clock from the AGC), keep reading its output so the AGC
            # display can be restored when a key is pressed.
            if s is not None:
                pollAGC(reconnect=False)
            gettemperature()
            check_ntp()
            clock()
        elif keypressed == 1 and idleclock == 2:
            # a key has been pressed, which means we want to play with the AGC.
            # we should connect to the AGC then
            if connectToAGCneeded == 0 or s is None:
                connectToAGC()
                connectToAGCneeded = 1

            if not didSomething:
                time.sleep(PULSE)
            didSomething = pollAGC()

            # Check for locally-generated data for which we must generate messages
            # to yaAGC over the socket.  In theory, the externalData list could contain
            # any number of channel operations, but in practice (at least for something
            # like a DSKY implementation) it will actually contain only 0 or 1 operations.
            externalData = inputsForAGC()
            if externalData == "":
                echoOn(True)
                return
            for i in range(0, len(externalData)):
                if s is None:
                    break
                try:
                    packetize(externalData[i])
                except OSError as e:
                    print("Lost connection to yaAGC while sending: " + str(e))
                    connectToAGC()
                    resetPacketBuffer()
                    break
                didSomething = True

eventLoop()

os._exit(0)
