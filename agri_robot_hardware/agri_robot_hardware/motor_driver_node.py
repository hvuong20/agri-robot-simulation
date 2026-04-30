#!/usr/bin/env python3
"""
motor_driver_node — Twist → GPIO PWM + ESTOP guardian.

Subscribes to /cmd_vel_mux (output of twist_mux) and converts Twist to
differential (skid-steer) left/right motor duty cycles via the configured
PWM driver (L298N or mock).

ESTOP is enforced HERE — at the last software layer before GPIO — not
at twist_mux.  Even if twist_mux malfunctions, ESTOP still locks the
motors to zero.

Topics subscribed:
  /cmd_vel_mux    (geometry_msgs/Twist)  — velocity commands from twist_mux
  /estop_trigger  (std_msgs/Empty)       — ESTOP active  (motors → 0 immediately)
  /estop_clear    (std_msgs/Empty)       — ESTOP released

Topics published:
  /odom           (nav_msgs/Odometry)    — dead-reckoning from cmd + time
  /motor/status   (std_msgs/String)      — JSON: {left, right, estop, mode}

Parameters (hardware_params.yaml):
  motor.driver          string   'l298n' | 'mock'
  motor.left_en         int      GPIO BCM pin (PWM enable left)
  motor.left_in1        int      GPIO BCM pin
  motor.left_in2        int      GPIO BCM pin
  motor.right_en        int      GPIO BCM pin (PWM enable right)
  motor.right_in1       int      GPIO BCM pin
  motor.right_in2       int      GPIO BCM pin
  motor.wheel_base      float    0.35    metres between left/right contact patches
  motor.wheel_radius    float    0.07    metres
  motor.max_speed       float    1.5     m/s (clips linear.x)
  motor.max_angular     float    1.0     rad/s (clips angular.z)
  motor.cmd_timeout_s   float    0.5     stop if no /cmd_vel_mux within this interval
  motor.status_rate_hz  float    5.0     publish /motor/status at this rate
"""

import json
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Empty, String
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from agri_robot_hardware.drivers.pwm_motor import create_motor_driver

# QoS for ESTOP topics — best-effort but very small queue (latency > reliability)
_ESTOP_QOS = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
)


class MotorDriverNode(Node):

    def __init__(self):
        super().__init__('motor_driver_node')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('motor.driver',         'mock')
        self.declare_parameter('motor.left_en',        12)
        self.declare_parameter('motor.left_in1',       23)
        self.declare_parameter('motor.left_in2',       24)
        self.declare_parameter('motor.right_en',       13)
        self.declare_parameter('motor.right_in1',      27)
        self.declare_parameter('motor.right_in2',      22)
        self.declare_parameter('motor.wheel_base',     0.35)
        self.declare_parameter('motor.wheel_radius',   0.07)
        self.declare_parameter('motor.max_speed',      1.5)
        self.declare_parameter('motor.max_angular',    1.0)
        self.declare_parameter('motor.cmd_timeout_s',  0.5)
        self.declare_parameter('motor.status_rate_hz', 5.0)

        driver_type = self.get_parameter('motor.driver').value
        self._wheel_base   = self.get_parameter('motor.wheel_base').value
        self._wheel_radius = self.get_parameter('motor.wheel_radius').value
        self._max_speed    = self.get_parameter('motor.max_speed').value
        self._max_angular  = self.get_parameter('motor.max_angular').value
        self._cmd_timeout  = self.get_parameter('motor.cmd_timeout_s').value
        status_hz          = self.get_parameter('motor.status_rate_hz').value

        motor_cfg = {
            'driver':    driver_type,
            'left_en':   self.get_parameter('motor.left_en').value,
            'left_in1':  self.get_parameter('motor.left_in1').value,
            'left_in2':  self.get_parameter('motor.left_in2').value,
            'right_en':  self.get_parameter('motor.right_en').value,
            'right_in1': self.get_parameter('motor.right_in1').value,
            'right_in2': self.get_parameter('motor.right_in2').value,
        }

        # ── Motor driver ──────────────────────────────────────────────────────
        self._motor = create_motor_driver(motor_cfg)
        try:
            self._motor.setup()
            self.get_logger().info(
                f'Motor driver ready: type={driver_type}'
            )
        except RuntimeError as exc:
            self.get_logger().error(f'Motor driver setup failed: {exc}')
            self.get_logger().warn('Falling back to MockPWMMotor')
            from agri_robot_hardware.drivers.pwm_motor import MockPWMMotor
            self._motor = MockPWMMotor()
            self._motor.setup()

        # ── State ─────────────────────────────────────────────────────────────
        self._estop_active  = False
        self._left_speed    = 0.0   # normalised [-1, 1]
        self._right_speed   = 0.0
        self._last_cmd_time = time.time()

        # Dead-reckoning odometry accumulators
        self._odom_x   = 0.0
        self._odom_y   = 0.0
        self._odom_yaw = 0.0
        self._prev_odom_time = time.time()

        # ── Subscribers ───────────────────────────────────────────────────────
        self.create_subscription(
            Twist, '/cmd_vel_mux', self._cmd_cb, 10
        )
        self.create_subscription(
            Empty, '/estop_trigger', self._estop_on_cb, _ESTOP_QOS
        )
        self.create_subscription(
            Empty, '/estop_clear', self._estop_off_cb, _ESTOP_QOS
        )

        # ── Publishers ────────────────────────────────────────────────────────
        self._pub_odom   = self.create_publisher(Odometry, '/odom', 10)
        self._pub_status = self.create_publisher(String, '/motor/status', 10)

        # ── Timers ────────────────────────────────────────────────────────────
        # Watchdog: stop motors if no cmd received within timeout
        self._watchdog = self.create_timer(0.1, self._watchdog_cb)
        # Status publisher
        self.create_timer(1.0 / status_hz, self._status_cb)

        self.get_logger().info('motor_driver_node ready')

    # ── ESTOP callbacks ───────────────────────────────────────────────────────

    def _estop_on_cb(self, _msg: Empty):
        if not self._estop_active:
            self._estop_active = True
            self._motor.brake()
            self._left_speed  = 0.0
            self._right_speed = 0.0
            self.get_logger().error('ESTOP ACTIVE — motors braked')

    def _estop_off_cb(self, _msg: Empty):
        if self._estop_active:
            self._estop_active = False
            self._motor.stop()
            self.get_logger().info('ESTOP cleared — motors released')

    # ── Velocity command callback ─────────────────────────────────────────────

    def _cmd_cb(self, msg: Twist):
        self._last_cmd_time = time.time()

        if self._estop_active:
            return

        linear  = max(-self._max_speed,   min(self._max_speed,   msg.linear.x))
        angular = max(-self._max_angular, min(self._max_angular, msg.angular.z))

        # Differential drive mixing: v_left = v - ω*L/2, v_right = v + ω*L/2
        v_left  = linear - angular * self._wheel_base / 2.0
        v_right = linear + angular * self._wheel_base / 2.0

        # Normalise to [-1, 1] using max_speed
        left_norm  = max(-1.0, min(1.0, v_left  / self._max_speed))
        right_norm = max(-1.0, min(1.0, v_right / self._max_speed))

        self._left_speed  = left_norm
        self._right_speed = right_norm
        self._motor.set_speeds(left_norm, right_norm)

        self._update_odometry(v_left, v_right)

    # ── Watchdog: stop if no command received ─────────────────────────────────

    def _watchdog_cb(self):
        if self._estop_active:
            return
        elapsed = time.time() - self._last_cmd_time
        if elapsed > self._cmd_timeout:
            if self._left_speed != 0.0 or self._right_speed != 0.0:
                self.get_logger().warn(
                    f'cmd_vel timeout ({elapsed:.2f}s) — stopping motors'
                )
            self._left_speed  = 0.0
            self._right_speed = 0.0
            self._motor.stop()

    # ── Dead-reckoning odometry ───────────────────────────────────────────────

    def _update_odometry(self, v_left: float, v_right: float) -> None:
        now = time.time()
        dt  = now - self._prev_odom_time
        self._prev_odom_time = now

        if dt <= 0 or dt > 1.0:
            return

        v_centre = (v_left + v_right) / 2.0
        omega    = (v_right - v_left) / self._wheel_base

        d_yaw = omega * dt
        d_x   = v_centre * math.cos(self._odom_yaw + d_yaw / 2.0) * dt
        d_y   = v_centre * math.sin(self._odom_yaw + d_yaw / 2.0) * dt

        self._odom_x   += d_x
        self._odom_y   += d_y
        self._odom_yaw += d_yaw

        # Publish odometry
        odom = Odometry()
        odom.header.stamp    = self.get_clock().now().to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id  = 'base_link'

        odom.pose.pose.position.x = self._odom_x
        odom.pose.pose.position.y = self._odom_y
        odom.pose.pose.position.z = 0.0

        half_yaw = self._odom_yaw / 2.0
        odom.pose.pose.orientation.z = math.sin(half_yaw)
        odom.pose.pose.orientation.w = math.cos(half_yaw)

        odom.twist.twist.linear.x  = v_centre
        odom.twist.twist.angular.z = omega

        # Diagonal covariance — modest uncertainty for dead-reckoning
        odom.pose.covariance[0]  = 0.1
        odom.pose.covariance[7]  = 0.1
        odom.pose.covariance[35] = 0.2
        odom.twist.covariance[0]  = 0.05
        odom.twist.covariance[35] = 0.1

        self._pub_odom.publish(odom)

    # ── Status publisher ──────────────────────────────────────────────────────

    def _status_cb(self):
        status = {
            'left':  round(self._left_speed,  3),
            'right': round(self._right_speed, 3),
            'estop': self._estop_active,
        }
        msg = String()
        msg.data = json.dumps(status)
        self._pub_status.publish(msg)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def destroy_node(self):
        self._motor.brake()
        self._motor.cleanup()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MotorDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
