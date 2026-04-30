#!/usr/bin/env python3
"""
rc_interface_node — Read RC receiver and publish to ROS 2 topics.

Reads raw channel data via the configured protocol driver (iBUS/SBUS/PPM/mock),
maps channels to velocity commands and mode signals, then publishes:

  /cmd_vel_teleop      (geometry_msgs/Twist)     — manual drive commands
  /rc/mode_switch      (std_msgs/Int8)            — 0=MANUAL 1=AUTO 2=FOLLOW
  /estop_trigger       (std_msgs/Empty)           — fire when CH_ESTOP goes LOW
  /estop_clear         (std_msgs/Empty)           — fire when CH_ESTOP returns HIGH
  /rc/boundary_btn     (std_msgs/Empty)           — rising-edge on CH_BOUNDARY_BTN

Parameters (hardware_params.yaml):
  rc.protocol          string   'mock' | 'ibus' | 'sbus' | 'ppm'
  rc.port              string   '/dev/serial0'
  rc.baud              int      115200
  rc.gpio_pin          int      4            (PPM only)
  rc.poll_rate_hz      float    50.0
  rc.ch_throttle       int      2            channel → linear.x
  rc.ch_steering       int      1            channel → angular.z
  rc.ch_mode           int      5            3-position switch
  rc.ch_estop          int      6            2-position switch (LOW = ESTOP)
  rc.ch_boundary_btn   int      7            momentary push button
  rc.deadband_us       int      30           ignore drift within ±deadband µs
  rc.max_linear_vel    float    1.5          m/s
  rc.max_angular_vel   float    1.0          rad/s
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int8, Empty

from agri_robot_hardware.drivers.rc_protocol import create_driver

# CH_MODE threshold: channel value > HIGH_THRESH → position "high"
MODE_LOW_THRESH  = 1300   # < 1300 µs = position 0 (MANUAL)
MODE_HIGH_THRESH = 1700   # > 1700 µs = position 2 (FOLLOW), middle = AUTO
ESTOP_LOW_THRESH = 1300   # < 1300 µs = ESTOP active


class RCInterfaceNode(Node):

    def __init__(self):
        super().__init__('rc_interface_node')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('rc.protocol',         'mock')
        self.declare_parameter('rc.port',             '/dev/serial0')
        self.declare_parameter('rc.baud',             115200)
        self.declare_parameter('rc.gpio_pin',         4)
        self.declare_parameter('rc.poll_rate_hz',     50.0)
        self.declare_parameter('rc.ch_throttle',      2)
        self.declare_parameter('rc.ch_steering',      1)
        self.declare_parameter('rc.ch_mode',          5)
        self.declare_parameter('rc.ch_estop',         6)
        self.declare_parameter('rc.ch_boundary_btn',  7)
        self.declare_parameter('rc.deadband_us',      30)
        self.declare_parameter('rc.max_linear_vel',   1.5)
        self.declare_parameter('rc.max_angular_vel',  1.0)

        protocol   = self.get_parameter('rc.protocol').value
        port       = self.get_parameter('rc.port').value
        baud       = self.get_parameter('rc.baud').value
        gpio_pin   = self.get_parameter('rc.gpio_pin').value
        poll_hz    = self.get_parameter('rc.poll_rate_hz').value

        self._ch_throttle     = self.get_parameter('rc.ch_throttle').value
        self._ch_steering     = self.get_parameter('rc.ch_steering').value
        self._ch_mode         = self.get_parameter('rc.ch_mode').value
        self._ch_estop        = self.get_parameter('rc.ch_estop').value
        self._ch_boundary     = self.get_parameter('rc.ch_boundary_btn').value
        self._deadband        = self.get_parameter('rc.deadband_us').value
        self._max_linear      = self.get_parameter('rc.max_linear_vel').value
        self._max_angular     = self.get_parameter('rc.max_angular_vel').value

        # ── RC Driver ─────────────────────────────────────────────────────────
        driver_kwargs = {}
        if protocol in ('ibus', 'sbus'):
            driver_kwargs = {'port': port, 'baud': baud}
        elif protocol == 'ppm':
            driver_kwargs = {'gpio_pin': gpio_pin}

        self._driver = create_driver(protocol, **driver_kwargs)
        try:
            self._driver.open()
            self.get_logger().info(
                f'RC driver opened: protocol={protocol}'
                + (f'  port={port}' if protocol in ('ibus', 'sbus') else '')
                + (f'  gpio={gpio_pin}' if protocol == 'ppm' else '')
            )
        except RuntimeError as exc:
            self.get_logger().error(f'RC driver open failed: {exc}')
            self.get_logger().warn('Falling back to MockRCDriver')
            from agri_robot_hardware.drivers.rc_protocol import MockRCDriver
            self._driver = MockRCDriver()
            self._driver.open()

        # ── Publishers ────────────────────────────────────────────────────────
        self._pub_cmd    = self.create_publisher(Twist, '/cmd_vel_teleop', 10)
        self._pub_mode   = self.create_publisher(Int8,  '/rc/mode_switch', 10)
        self._pub_estop  = self.create_publisher(Empty, '/estop_trigger',  1)
        self._pub_eclr   = self.create_publisher(Empty, '/estop_clear',    1)
        self._pub_bnd    = self.create_publisher(Empty, '/rc/boundary_btn', 1)

        # ── State for edge detection ──────────────────────────────────────────
        self._prev_estop_active  = False
        self._prev_boundary_high = False

        # ── Poll timer ────────────────────────────────────────────────────────
        self._timer = self.create_timer(1.0 / poll_hz, self._poll)

        self.get_logger().info(
            f'rc_interface_node ready — polling at {poll_hz:.0f} Hz'
        )

    # ── Main poll callback ────────────────────────────────────────────────────

    def _poll(self):
        channels = self._driver.read_channels()
        if channels is None:
            return

        # ── Twist from throttle + steering channels ────────────────────────
        throttle_us = channels.get(self._ch_throttle, 1500)
        steering_us = channels.get(self._ch_steering, 1500)

        linear_x  = self._us_to_vel(throttle_us, self._max_linear)
        angular_z = self._us_to_vel(steering_us, self._max_angular)

        # Apply deadband
        if abs(throttle_us - 1500) < self._deadband:
            linear_x = 0.0
        if abs(steering_us - 1500) < self._deadband:
            angular_z = 0.0

        cmd = Twist()
        cmd.linear.x  = linear_x
        cmd.angular.z = -angular_z  # invert: right stick right = turn right
        self._pub_cmd.publish(cmd)

        # ── Mode switch (3-position, rising/falling not needed — publish always)
        mode_us = channels.get(self._ch_mode, 1500)
        if mode_us < MODE_LOW_THRESH:
            mode_val = 0   # MANUAL
        elif mode_us > MODE_HIGH_THRESH:
            mode_val = 2   # FOLLOW
        else:
            mode_val = 1   # AUTO
        msg = Int8()
        msg.data = mode_val
        self._pub_mode.publish(msg)

        # ── ESTOP — edge detection ─────────────────────────────────────────
        estop_us     = channels.get(self._ch_estop, 2000)
        estop_active = estop_us < ESTOP_LOW_THRESH

        if estop_active and not self._prev_estop_active:
            self.get_logger().warn('RC ESTOP activated!')
            self._pub_estop.publish(Empty())
        elif not estop_active and self._prev_estop_active:
            self.get_logger().info('RC ESTOP cleared.')
            self._pub_eclr.publish(Empty())
        self._prev_estop_active = estop_active

        # ── Boundary button — rising-edge only ────────────────────────────
        bnd_us   = channels.get(self._ch_boundary, 1000)
        bnd_high = bnd_us > 1700   # button pressed = high
        if bnd_high and not self._prev_boundary_high:
            self._pub_bnd.publish(Empty())
            self.get_logger().info('Boundary waypoint recorded (RC button).')
        self._prev_boundary_high = bnd_high

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _us_to_vel(us: int, max_vel: float) -> float:
        """Map [1000, 2000] µs centred at 1500 → [-max_vel, +max_vel]."""
        return ((us - 1500) / 500.0) * max_vel

    def destroy_node(self):
        self._driver.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = RCInterfaceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
