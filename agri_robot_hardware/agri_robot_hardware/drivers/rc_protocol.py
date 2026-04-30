"""
RC Receiver Protocol Drivers
Supports iBUS, SBUS, PPM — selected via config.

Channel values are normalised to pulse-width microseconds [1000 .. 2000].
Centre = 1500, min = 1000, max = 2000.

Usage:
    driver = IBUSDriver('/dev/serial0', baud=115200)
    driver.open()
    channels = driver.read_channels()   # {1: 1500, 2: 1523, ...}
    driver.close()

To add a new protocol, subclass RCProtocolDriver and implement
`open()`, `read_channels()`, `is_connected()`, `close()`.
"""

from __future__ import annotations
import struct
import time
from abc import ABC, abstractmethod


# ── Abstract base ──────────────────────────────────────────────────────────────

class RCProtocolDriver(ABC):
    """Common interface for all RC receiver protocols."""

    NUM_CHANNELS = 10  # we use channels 1-10

    @abstractmethod
    def open(self) -> None:
        """Open serial port / GPIO resource."""

    @abstractmethod
    def read_channels(self) -> dict[int, int] | None:
        """
        Return {channel_number: pulse_us} for all channels, or None if no
        fresh frame is available yet.  Channel numbers are 1-based.
        Pulse values are clamped to [1000, 2000].
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """True if the driver has received a valid frame recently."""

    @abstractmethod
    def close(self) -> None:
        """Release serial / GPIO resources."""

    # ── helpers shared by all protocols ───────────────────────────────────────

    @staticmethod
    def _clamp(value: int, lo: int = 1000, hi: int = 2000) -> int:
        return max(lo, min(hi, value))

    @staticmethod
    def _normalise_to_us(raw: int, raw_min: int, raw_max: int) -> int:
        """Map raw value from [raw_min, raw_max] → [1000, 2000] µs."""
        ratio = (raw - raw_min) / (raw_max - raw_min)
        return int(1000 + ratio * 1000)


# ── iBUS Driver ────────────────────────────────────────────────────────────────

class IBUSDriver(RCProtocolDriver):
    """
    FlySky iBUS protocol — 115200 baud, non-inverted UART.

    Frame format (32 bytes):
        0x20 0x40  [ch1_lo ch1_hi] ... [ch14_lo ch14_hi]  [checksum_lo checksum_hi]
    Channel value range: 1000–2000 µs (raw values are the µs directly).

    Typical Pi 3 connection:
        RC receiver iBUS TX → Pi GPIO 15 (UART RX, /dev/serial0)
        NOTE: disable Bluetooth first (dtoverlay=disable-bt in /boot/config.txt)
    """

    FRAME_LEN    = 32
    HEADER       = bytes([0x20, 0x40])
    TIMEOUT_SECS = 0.5  # consider disconnected after this many seconds with no valid frame

    def __init__(self, port: str = '/dev/serial0', baud: int = 115200):
        self._port  = port
        self._baud  = baud
        self._ser   = None
        self._last_channels: dict[int, int] = {i: 1500 for i in range(1, 15)}
        self._last_frame_time = 0.0

    def open(self) -> None:
        try:
            import serial
            self._ser = serial.Serial(self._port, self._baud, timeout=0.1)
        except ImportError:
            raise RuntimeError(
                'pyserial not installed — run: pip3 install pyserial'
            )
        except Exception as exc:
            raise RuntimeError(f'Cannot open {self._port}: {exc}')

    def read_channels(self) -> dict[int, int] | None:
        if self._ser is None:
            return None

        # Read until we find frame header
        buf = self._ser.read(self.FRAME_LEN * 2)  # drain extra bytes
        idx = buf.find(self.HEADER)
        if idx < 0 or idx + self.FRAME_LEN > len(buf):
            return None

        frame = buf[idx: idx + self.FRAME_LEN]

        # Verify checksum: sum of bytes 0..29 == bytes 30..31 (little-endian uint16)
        expected_checksum = 0xFFFF - sum(frame[:30]) & 0xFFFF
        actual_checksum   = struct.unpack_from('<H', frame, 30)[0]
        if expected_checksum != actual_checksum:
            return None

        # Parse 14 channels (only return first NUM_CHANNELS)
        channels: dict[int, int] = {}
        for i in range(self.NUM_CHANNELS):
            offset = 2 + i * 2
            raw = struct.unpack_from('<H', frame, offset)[0]
            channels[i + 1] = self._clamp(raw)

        self._last_channels = channels
        self._last_frame_time = time.time()
        return channels

    def is_connected(self) -> bool:
        return time.time() - self._last_frame_time < self.TIMEOUT_SECS

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None


# ── SBUS Driver ────────────────────────────────────────────────────────────────

class SBUSDriver(RCProtocolDriver):
    """
    FrSky / Futaba SBUS protocol — 100000 baud, inverted UART, 8E2.

    Frame format (25 bytes):
        0x0F  [22 bytes channel data]  flags  0x00
    Channel range: 172–1811 (mapped to 1000–2000 µs).

    Pi 3 hardware note:
        SBUS signal is inverted (active-low).  Raspberry Pi UART does NOT
        support hardware inversion natively.  Options:
          a) Use a hardware inverter (single NPN transistor or SN74HC04).
          b) Use a USB-UART adapter that supports custom baud + inversion.
        Without inversion, frames will appear corrupt (all bytes bitflipped).
    """

    FRAME_LEN    = 25
    HEADER       = 0x0F
    FOOTER       = 0x00
    RAW_MIN      = 172
    RAW_MAX      = 1811
    TIMEOUT_SECS = 0.5

    def __init__(self, port: str = '/dev/serial0', baud: int = 100000):
        self._port  = port
        self._baud  = baud
        self._ser   = None
        self._last_frame_time = 0.0

    def open(self) -> None:
        try:
            import serial
            # 8E2 parity, 2 stop bits — required for SBUS
            self._ser = serial.Serial(
                self._port, self._baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_TWO,
                timeout=0.1,
            )
        except ImportError:
            raise RuntimeError('pyserial not installed — run: pip3 install pyserial')
        except Exception as exc:
            raise RuntimeError(f'Cannot open {self._port}: {exc}')

    def read_channels(self) -> dict[int, int] | None:
        if self._ser is None:
            return None

        buf = self._ser.read(self.FRAME_LEN * 2)
        idx = -1
        for i in range(len(buf) - self.FRAME_LEN + 1):
            if buf[i] == self.HEADER and buf[i + self.FRAME_LEN - 1] == self.FOOTER:
                idx = i
                break
        if idx < 0:
            return None

        frame = buf[idx: idx + self.FRAME_LEN]
        payload = frame[1:23]

        # Unpack 16 channels × 11 bits packed into 176 bits (22 bytes)
        raw_channels: list[int] = []
        bit_offset = 0
        for _ in range(16):
            byte_idx  = bit_offset // 8
            bit_shift = bit_offset % 8
            raw = (
                (payload[byte_idx] >> bit_shift)
                | (payload[byte_idx + 1] << (8 - bit_shift))
                | (payload[byte_idx + 2] << (16 - bit_shift))
            ) & 0x07FF
            raw_channels.append(raw)
            bit_offset += 11

        channels: dict[int, int] = {}
        for i in range(self.NUM_CHANNELS):
            channels[i + 1] = self._normalise_to_us(
                raw_channels[i], self.RAW_MIN, self.RAW_MAX
            )

        self._last_frame_time = time.time()
        return channels

    def is_connected(self) -> bool:
        return time.time() - self._last_frame_time < self.TIMEOUT_SECS

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None


# ── PPM Driver ─────────────────────────────────────────────────────────────────

class PPMDriver(RCProtocolDriver):
    """
    PPM Sum protocol — all channels encoded on one GPIO pin via pulse widths.

    Requires `pigpio` daemon running on the Pi (sudo pigpiod).
    PPM frame: sync gap (>2.5 ms) followed by N channel pulses (1.0–2.0 ms).

    Pi 3 connection: RC receiver PPM output → any GPIO (default GPIO 4 / pin 7).
    """

    SYNC_PULSE_US  = 2500   # pulses longer than this are frame separators
    MIN_PULSE_US   = 800
    MAX_PULSE_US   = 2200
    TIMEOUT_SECS   = 0.5

    def __init__(self, gpio_pin: int = 4):
        self._pin     = gpio_pin
        self._pi      = None
        self._cb      = None
        self._pulses: list[int] = []
        self._channels: dict[int, int] = {i: 1500 for i in range(1, 11)}
        self._last_tick  = 0
        self._last_frame_time = 0.0

    def open(self) -> None:
        try:
            import pigpio
            self._pi = pigpio.pi()
            if not self._pi.connected:
                raise RuntimeError(
                    'pigpio daemon not running — start with: sudo pigpiod'
                )
            self._pi.set_mode(self._pin, pigpio.INPUT)
            self._cb = self._pi.callback(
                self._pin, pigpio.EITHER_EDGE, self._pulse_cb
            )
        except ImportError:
            raise RuntimeError('pigpio not installed — run: pip3 install pigpio')

    def _pulse_cb(self, gpio, level, tick) -> None:
        import pigpio
        if self._last_tick == 0:
            self._last_tick = tick
            return

        pulse_us = pigpio.tickDiff(self._last_tick, tick)
        self._last_tick = tick

        if level == 0:  # falling edge = end of pulse
            if pulse_us > self.SYNC_PULSE_US:
                # Frame separator: process accumulated pulses
                if len(self._pulses) >= self.NUM_CHANNELS:
                    for i in range(self.NUM_CHANNELS):
                        self._channels[i + 1] = self._clamp(self._pulses[i])
                    self._last_frame_time = time.time()
                self._pulses = []
            elif self.MIN_PULSE_US <= pulse_us <= self.MAX_PULSE_US:
                self._pulses.append(pulse_us)

    def read_channels(self) -> dict[int, int] | None:
        if not self.is_connected():
            return None
        return dict(self._channels)

    def is_connected(self) -> bool:
        return time.time() - self._last_frame_time < self.TIMEOUT_SECS

    def close(self) -> None:
        if self._cb is not None:
            self._cb.cancel()
        if self._pi is not None:
            self._pi.stop()


# ── Mock Driver (for simulation / testing without hardware) ────────────────────

class MockRCDriver(RCProtocolDriver):
    """
    Stub driver for testing without physical RC hardware.
    Returns centred channels (1500 µs) permanently.
    Can be driven programmatically via set_channel().
    """

    def __init__(self):
        self._channels = {i: 1500 for i in range(1, 11)}
        self._connected = True

    def open(self) -> None:
        pass

    def read_channels(self) -> dict[int, int] | None:
        return dict(self._channels)

    def set_channel(self, ch: int, value: int) -> None:
        self._channels[ch] = self._clamp(value)

    def is_connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False


# ── Factory ────────────────────────────────────────────────────────────────────

def create_driver(protocol: str, **kwargs) -> RCProtocolDriver:
    """
    Factory function used by rc_interface_node.

    protocol: 'ibus' | 'sbus' | 'ppm' | 'mock'
    kwargs  : forwarded to the selected driver's __init__
    """
    mapping = {
        'ibus': IBUSDriver,
        'sbus': SBUSDriver,
        'ppm':  PPMDriver,
        'mock': MockRCDriver,
    }
    cls = mapping.get(protocol.lower())
    if cls is None:
        raise ValueError(
            f"Unknown RC protocol '{protocol}'. Choose from: {list(mapping)}"
        )
    return cls(**kwargs)
