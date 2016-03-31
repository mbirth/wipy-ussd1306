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
    DISPLAY_BLANK   = [0xae]
    DISPLAY_ALL     = [0xa5]
    DISPLAY_NORMAL  = [0xa4, 0xa6, 0xaf]
    DISPLAY_INVERSE = [0xa7]
    DC_CMD  = 0x80
    DC_DATA = 0x40

    def __init__(self, i2c, pins=('GP15', 'GP10'), pwr=None, devid=0x3c):
        self.width  = 128
        self.height = 64
        self.devid      = devid
        self.power      = self.POWER_DOWN
        self.addressing = self.ADDRESSING_HORIZ
        self.display_mode = self.DISPLAY_NORMAL

        # init the I2C bus and pins
        i2c.init(i2c.MASTER, baudrate=400000, pins=pins)   # 400 kHz
        if pwr:
            if "OUT_PP" in dir(pwr):
                # pyBoard style
                pwr.init(pwr.OUT_PP, pwr_PULL_NONE)
            else:
                # WiPy style
                pwr.init(pwr.OUT, None)

        self.i2c = i2c
        self.pwr = pwr
        self.osc_freq  = 8
        self.clock_div = 1

        self.power_on()   # enable power to the display
        self.set_power(self.POWER_DOWN)   # set display to sleep mode
        self.set_mux_ratio(self.height)   # set multiplex ratio to 64 (default), for 32px: 32
        self.set_disp_offset(0)           # set display offset to 0
        self.set_disp_start_line(0)       # set display start line to 0
        self.set_segment_remap_enabled(False)
        self.set_com_output_scan_dir_remap_enabled(False)
        self.set_com_pins_hw_config(True, False)    # COM pins (for 32px: False, False)
        self.set_contrast(255)
        self.set_osc_freq(8, False)       # set oscillator freq., but don't send to LCD yet
        self.set_clock_div(1)             # set clock div and send osc_freq+clock_div to LCD
        self.set_chargepump_enabled(True) # chargepump on (ext. VCC: off)
        self.set_addressing(self.ADDRESSING_HORIZ)
        self.set_precharge_period(1, 15)   # with ext. VCC: 2, 2 (RESET)
        self.set_vcomh_deselect_level(4)
        self.set_display(self.DISPLAY_NORMAL)   # enables and sets disp to show RAM contents, not inversed
        self.clear()

    def set_power(self, power):
        """ Sets the power mode of the LCD controller """
        assert power in [self.POWER_UP, self.POWER_DOWN], "Power must be POWER_UP or POWER_DOWN."
        self.power = power
        self.command([power])

    def set_vcomh_deselect_level(self, level):
        """ Sets the Vcomh deselect level. """
        assert 0 <= level < 8, "Level must be between 0 (0.65*Vcc) and 7 (1.07*Vcc)"
        value = (level << 4)
        self.command([0xdb, value])

    def set_precharge_period(self, phase1_dclk, phase2_dclk):
        """ Sets the pre-charge period for both phases. """
        assert 0 < phase1_dclk < 16, "phase1_dclk must be between 1 and 15. (2 = RESET)"
        assert 0 < phase2_dclk < 16, "phase2_dclk must be between 1 and 15. (2 = RESET)"
        value = (phase2_dclk << 4)
        value |= phase1_dclk
        self.command([0xd9, value])

    def set_com_pins_hw_config(self, enable_alt_config, enable_lr_remap):
        """ Sets the COM pins hardware configuration. """
        assert isinstance(enable_alt_config, bool), "enable_alt_config must be True or False."
        assert isinstance(enable_lr_remap, bool), "enable_lr_remap must be True or False."
        value = 0x02
        if enable_alt_config:
            value |= 0x10
        if enable_lr_remap:
            value |= 0x20
        self.command([0xda, value])

    def set_com_output_scan_dir_remap_enabled(self, status):
        """ Enables or disables COM output scan direction remapping. """
        assert isinstance(status, bool), "Status must be True or False."
        self.command([(0xc8 if status else 0xc0)])

    def set_segment_remap_enabled(self, status):
        """ Enables or disables segment remapping. """
        assert isinstance(status, bool), "Status must be True or False."
        self.command([(0xa1 if status else 0xa0)])

    def set_chargepump_enabled(self, status):
        """ Enables or disables the charge pump. """
        assert isinstance(status, bool), "Status must be True or False."
        self.command([0x8d, (0x14 if status else 0x10)])

    def _set_oscfreqclockdiv(self):
        """ Sets the oscillator frequency and clock divider value """
        value = (self.osc_freq << 4) | (self.clock_div-1)
        self.command([0xd5, value])

    def set_osc_freq(self, osc_freq, set=True):
        """ Stores and sets the oscillator frequency """
        assert 0 <= osc_freq < 16, "Oscillator frequency must be between 0 and 15."
        self.osc_freq = osc_freq
        if set:
            self._set_oscfreqclockdiv()

    def set_clock_div(self, clock_div, set=True):
        """ Stores and sets clock divider """
        assert 0 < clock_div <= 16, "Clock divider must be between 1 and 16."
        self.clock_div = clock_div
        if set:
            self._set_oscfreqclockdiv()

    def set_mux_ratio(self, mux_ratio):
        """ Sets the multiplex ratio. """
        assert 16 <= mux_ratio <= 64, "Mux ratio must be between 16 and 64."
        self.command([0xa8, (mux_ratio-1)])

    def set_disp_offset(self, offset):
        """ Sets the display offset (vertical shift). """
        assert 0 <= offset < 63, "Offset must be between 0 and 63."
        self.command([0xd3, offset])

    def set_disp_start_line(self, start_line):
        """ Sets the display RAM start line register. """
        assert 0 <= start_line < 63, "Start line must be between 0 and 63."
        self.command([0x40 | start_line])

    def set_addressing(self, addr):
        """ Sets the adressing mode """
        assert addr in [self.ADDRESSING_HORIZ, self.ADDRESSING_VERT, self.ADDRESSING_PAGE], "Addressing must be ADDRESSING_HORIZ, ADDRESSING_VERT or ADDRESSING_PAGE."
        self.addressing = addr
        self.command([0x20, addr])

    def set_display(self, display_mode):
        """ Sets display mode (blank, black, normal, inverse) """
        assert display_mode in [self.DISPLAY_BLANK, self.DISPLAY_ALL, self.DISPLAY_NORMAL, self.DISPLAY_INVERSE], "Mode must be one of DISPLAY_BLANK, DISPLAY_ALL, DISPLAY_NORMAL or DISPLAY_INVERSE."
        self.display_mode = display_mode
        self.command(display_mode)

    def set_contrast(self, value):
        """ set OLED contrast """
        assert 0x00 <= value <= 0xff, "Contrast value must be between 0 and 255"
        self.command([0x81, value])

    def position(self, x, y):
        """ set cursor to page y, column x """
        assert 0 <= x < self.width, "x must be between 0 and 127"
        assert 0 <= y < self.height // 8, "y must be between 0 and 7"
        self.command([0x21, x, 0x7f, 0x22, y, 0x07])

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
        #self.reset()

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
        arr2 = []
        for i in arr:
            arr2.append(self.DC_CMD)
            arr2.append(i)
        self.bitmap(arr2[1::], self.DC_CMD)

    def data(self, arr):
        """ send bytes in data mode """
        self.bitmap(arr, self.DC_DATA)

    def bitmap(self, arr, dc):
        arr = [dc] + arr
        #print(repr(arr))
        buf = struct.pack('B'*len(arr), *arr)
        print(repr(buf))
        self.i2c.writeto(self.devid, buf)

