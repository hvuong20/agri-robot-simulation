#!/usr/bin/env python3
"""
battery_monitor_node — Monitor LiPo battery voltage and publish status.

Reads cell voltage via an ADS1115 I2C ADC (through a voltage divider) or uses
a mock driver for development/simulation.

Publications:
  /battery/status  (std_msgs/String)  JSON every 5 s:
    { voltage: float,   # measured volts (e.g. 11.8)
      percent: float,   # 0–100 based on cell count + chemistry
      low: bool,        # true when percent <= warn_percent
      critical: bool }  # true when percent <= critical_percent

Parameters:
  battery.driver          string  'mock'   'mock' | 'ads1115'
  battery.cell_count      int     3        3S LiPo: 12.6 V full, 10.5 V cutoff
  battery.warn_percent    float   20.0
  battery.critical_percent float  10.0
  battery.publish_hz      float   0.2      every 5 s

Hardware wiring (ADS1115 driver):
  Battery + ──► R1(30kΩ) ──► ADS1115 A0 ──► R2(10kΩ) ──► GND
  Divider ratio = R2/(R1+R2) = 0.25  →  max 16.8 V (4S headroom)
  ADS1115 Vmax = 4.096 V (PGA ±4.096 V)

Install on Pi (ads1115 driver):
  pip3 install adafruit-circuitpython-ads1x15
"""

import json
import math
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# ── Chemistry constants (3S LiPo) ────────────────────────────────────────────
_CELL_FULL_V     = 4.20   # V per cell, fully charged
_CELL_EMPTY_V    = 3.50   # V per cell, safe cutoff (not hard cutoff)
_CELL_CUTOFF_V   = 3.50   # == empty for percent calc


def _voltage_to_percent(voltage: float, cell_count: int) -> float:
    """Approximate SoC from resting voltage (linear between empty and full)."""
    full  = _CELL_FULL_V  * cell_count
    empty = _CELL_EMPTY_V * cell_count
    pct   = (voltage - empty) / (full - empty) * 100.0
    return max(0.0, min(100.0, pct))


# ── ADC driver abstractions ───────────────────────────────────────────────────

class _MockADC:
    """Simulates a slowly-draining 3S LiPo starting at 85%."""
    def __init__(self):
        self._start = time.time()

    def read_voltage(self) -> float:
        elapsed_min = (time.time() - self._start) / 60.0
        # Drain ~1% per minute in simulation
        pct = max(5.0, 85.0 - elapsed_min)
        cells = 3
        v = _CELL_EMPTY_V * cells + pct / 100.0 * (_CELL_FULL_V - _CELL_EMPTY_V) * cells
        return round(v + 0.02 * math.sin(elapsed_min), 2)  # small ripple


class _ADS1115ADC:
    """Reads battery voltage via ADS1115 I2C ADC on Raspberry Pi."""
    DIVIDER_RATIO = 10_000 / (30_000 + 10_000)   # R2/(R1+R2) voltage divider

    def __init__(self):
        import board
        import busio
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn

        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ads.gain = 1          # ±4.096 V range
        self._chan = AnalogIn(ads, ADS.P0)

    def read_voltage(self) -> float:
        raw_v  = self._chan.voltage
        batt_v = raw_v / self.DIVIDER_RATIO
        return round(batt_v, 2)


def _create_adc(driver: str):
    if driver == 'ads1115':
        try:
            return _ADS1115ADC()
        except Exception as exc:
            import logging
            logging.warning(f'ADS1115 init failed ({exc}), falling back to mock')
    return _MockADC()


# ── ROS 2 node ────────────────────────────────────────────────────────────────

class BatteryMonitorNode(Node):

    def __init__(self):
        super().__init__('battery_monitor_node')

        self.declare_parameter('battery.driver',           'mock')
        self.declare_parameter('battery.cell_count',       3)
        self.declare_parameter('battery.warn_percent',     20.0)
        self.declare_parameter('battery.critical_percent', 10.0)
        self.declare_parameter('battery.publish_hz',       0.2)

        driver      = self.get_parameter('battery.driver').value
        self._cells = self.get_parameter('battery.cell_count').value
        self._warn  = self.get_parameter('battery.warn_percent').value
        self._crit  = self.get_parameter('battery.critical_percent').value
        pub_hz      = self.get_parameter('battery.publish_hz').value

        self._adc = _create_adc(driver)
        self._pub = self.create_publisher(String, '/battery/status', 10)
        self.create_timer(1.0 / pub_hz, self._publish)

        self.get_logger().info(
            f'battery_monitor_node ready — driver={driver}, cells={self._cells}'
        )

    def _publish(self):
        try:
            voltage = self._adc.read_voltage()
        except Exception as exc:
            self.get_logger().warn(f'ADC read error: {exc}')
            return

        percent  = _voltage_to_percent(voltage, self._cells)
        low      = percent <= self._warn
        critical = percent <= self._crit

        if critical:
            self.get_logger().error(
                f'CRITICAL battery: {voltage:.2f}V ({percent:.0f}%)'
            )
        elif low:
            self.get_logger().warn(
                f'Low battery: {voltage:.2f}V ({percent:.0f}%)'
            )

        data = {
            'voltage':  voltage,
            'percent':  round(percent, 1),
            'low':      low,
            'critical': critical,
        }
        msg = String()
        msg.data = json.dumps(data)
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = BatteryMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
