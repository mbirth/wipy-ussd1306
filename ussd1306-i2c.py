# -*- coding: utf-8 -*- 
"""
MicroPython SSD1306 I2C driver
"""

__author__     = "Markus Birth"
__copyright__  = "Copyright 2016, Markus Birth"
__credits__    = ["Markus Birth"]
__license__    = "MIT"
__version__    = "1.0"
__maintainer__ = "Markus Birth"
__email__      = "markus@birth-online.de"
__status__     = "Production"

# Datasheet: https://www.adafruit.com/datasheets/SSD1306.pdf
# Inspiration from:
#   - https://github.com/khenderick/micropython-drivers/tree/master/ssd1306
#
# PINOUT
# WiPy/pyBoard      display   function
#
# 3V3 or any Pin => VCC       3.3V logic voltage (0=off, 1=on)
# SDA            => SDM       data
# SCL            => SCL       clock
# GND            => GND
#
# WiPy (on Exp board, SD and User-LED jumper have to be removed!)
# PWR    = directly from 3V3 pin of the WiPy

try:
    import pyb as machine
except:
    # WiPy
    import machine

import struct
import time

class SSD1306:
    ADDRESSING_HORIZ = 0x00
    ADDRESSING_VERT  = 0x01
    ADDRESSING_PAGE  = 0x02
    POWER_UP   = 0xaf
    POWER_DOWN = 0xae
    DISPLAY_BLANK   = 0xae
    DISPLAY_ALL     = 0xa5
    DISPLAY_NORMAL  = [0xaf, 0xa4, 0xa6]
    DISPLAY_INVERSE = 0xa7
    DC_CMD  = 0x80
    DC_DATA = 0x40

    def __init__(self, i2c, pwr=None, devid=0x3c):
        self.width  = 128
        self.height = 64
        self.devid      = devid
        self.power      = self.POWER_DOWN
        self.addressing = self.ADDRESSING_HORIZ
        self.display_mode = self.DISPLAY_NORMAL

        # init the I2C bus and pins
        i2c.init(i2c.MASTER, baudrate=400000)   # 400 kHz
        if pwr:
            if "OUT_PP" in dir(pwr):
                # pyBoard style
                pwr.init(pwr.OUT_PP, pwr_PULL_NONE)
            else:
                # WiPy style
                pwr.init(pwr.OUT, None)

        self.i2c = i2c
        self.pwr = pwr

        self.power_on()   # enable power to the display
        self.set_power(self.POWER_DOWN)   # set display to sleep mode
        self.command([0xd5, 0x80])   # set clock divider
        self.command([0xa8, 0x3f])   # set multiplex to 0x3f (for 32px: 0x1f)
        self.command([0xd3, 0x00])   # set disp offset to 0
        self.command(0x40|0x00)   # set start line to 0
        self.command([0x8d, 0x14])   # chargepump on (ext. VCC - off: 0x10)
        self.set_addressing(self.ADDRESSING_HORIZ)
        self.command(0xa0|0x10)   # segment remap (invalid value: 0xb0, maybe 0x01?)
        self.command(0xc8)   # com scan dir decreasing (inc.: 0xc0)
        self.command([0xda, 0x12])   # com pins (for 32px: 0x02)
        self.set_contrast(255)
        self.command([0xd9, 0xf1])   # precharge (ext. VCC: 0x22 = RESET)
        self.command([0xdb, 0x40])   # Vcom deselect
        self.set_display(DISPLAY_NORMAL)   # enables and sets disp to show RAM contents, not inversed
        self.clear()

    def set_power(self, power, set=True):
        """ Sets the power mode of the LCD controller """
        assert power in [self.POWER_UP, self.POWER_DOWN], "Power must be POWER_UP or POWER_DOWN."
        self.power = power
        self.command(power)

    def set_adressing(self, addr):
        """ Sets the adressing mode """
        assert addr in [self.ADDRESSING_HORIZ, self.ADDRESSING_VERT, self.ADDRESSING_PAGE], "Addressing must be ADDRESSING_HORIZ, ADDRESSING_VERT or ADDRESSING_PAGE."
        self.addressing = addr
        self.command([0x20, addr])

    def set_display(self, display_mode):
        """ Sets display mode (blank, black, normal, inverse) """
        assert display_mode in [self.DISPLAY_BLANK, self.DISPLAY_ALL, self.DISPLAY_NORMAL, self.DISPLAY_INVERSE], "Mode must be one of DISPLAY_BLANK, DISPLAY_ALL, DISPLAY_NORMAL or DISPLAY_INVERSE."
        self.display_mode = display_mode
        self.command([display_mode])

    def set_contrast(self, value):
        """ set OLED contrast """
        assert 0x00 <= value <= 0xff, "Contrast value must be between 0 and 255"
        self.command([0x81, value])

    def position(self, x, y):
        """ set cursor to page y, column x """
        assert 0 <= x < self.width, "x must be between 0 and 127"
        assert 0 <= y < self.height // 8, "y must be between 0 and 7"
        self.command([0x20, 0x00, x, 0x21, 0x00, y])

    def clear(self):
        """ clear screen """
        self.position(0, 0)
        self.data([0] * (self.height * self.width // 8))
        self.position(0, 0)

    def sleep_ms(self, mseconds):
        try:
            time.sleep_ms(mseconds)
        except AttributeError:
            machine.delay(mseconds)

    def sleep_us(self, useconds):
        try:
            time.sleep_us(useconds)
        except AttributeError:
            machine.udelay(useconds)

    def power_on(self):
        if self.pwr:
            self.pwr.value(1)
        self.reset()

    def reset(self):
        """ issue reset impulse to reset the display """
        self.rst.value(0)  # RST on
        self.sleep_us(100) # reset impulse has to be >100 ns and <100 ms
        self.rst.value(1)  # RST off
        # Defaults after reset:
#        1. Display is OFF
#        2. 128 x 64 Display Mode
#        3. Normal segment and display data column address and row address mapping (SEG0 mapped to
#                address 00h and COM0 mapped to address 00h)
#        4. Shift register data clear in serial interface
#        5. Display start line is set at display RAM address 0
#        6. Column address counter is set at 0
#        7. Normal scan direction of the COM outputs
#        8. Contrast control register is set at 7Fh
#        9. Normal display mode (Equivalent to A4h command) 
        self.power      = self.POWER_DOWN
        self.addressing = self.ADDRESSING_HORIZ
        self.display_mode = self.DISPLAY_NORMAL

    def power_off(self):
        self.clear()
        self.set_power(self.POWER_DOWN)
        self.sleep_ms(10)
        if self.pwr:
            self.pwr.value(0) # turn off power

    def command(self, arr):
        """ send bytes in command mode """
        self.bitmap(arr, self.DC_CMD)

    def data(self, arr):
        """ send bytes in data mode """
        self.bitmap(arr, self.DC_DATA)

    def bitmap(self, arr, dc):
        arr = [dc] + arr
        buf = struct.pack('B'*len(arr), *arr)
        self.i2c.send(buf, addr=self.devid, timeout=5000)

