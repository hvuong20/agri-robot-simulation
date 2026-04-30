#!/usr/bin/env python3
"""
stuck_detector_node — Detect when the robot is physically stuck.

Two-layer detection:
  Layer 1 (fast, 2 Hz): /cmd_vel_mux velocity is non-zero but
    /odometry/local (wheel-encoder / dead-reckoning) velocity ≈ 0.
    Triggers mismatch flag after mismatch_duration_s.

  Layer 2 (confirm, GPS): After layer-1 mismatch, check that GPS position
    has not changed more than gps_confirm_m over gps_confirm_s seconds.
    This prevents false alarms from GPS drift or odom slip on rough terrain.

Publishes:
  /stuck_alert   (std_msgs/Empty) — fires once when stuck is confirmed
  /stuck/status  (std_msgs/String) JSON {stuck, mismatch_s, gps_drift_m}

Parameters:
  stuck.mismatch_duration_s  float  3.0   cmd vs odom velocity mismatch time
  stuck.cmd_vel_threshold    float  0.05  m/s — below this = "robot not commanded"
  stuck.odom_vel_threshold   float  0.03  m/s — below this = "robot not moving"
  stuck.gps_confirm_s        float  3.0   how long to track GPS after mismatch
  stuck.gps_confirm_m        float  0.5   GPS must not have moved more than this
  stuck.check_rate_hz        float  2.0
"""

import json
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Empty, String

EARTH_R = 6_371_000.0


def _haversine(lat1, lon1, lat2, lon2) -> float:
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


class StuckDetectorNode(Node):

    def __init__(self):
        super().__init__('stuck_detector_node')

        self.declare_parameter('stuck.mismatch_duration_s', 3.0)
        self.declare_parameter('stuck.cmd_vel_threshold',   0.05)
        self.declare_parameter('stuck.odom_vel_threshold',  0.03)
        self.declare_parameter('stuck.gps_confirm_s',       3.0)
        self.declare_parameter('stuck.gps_confirm_m',       0.5)
        self.declare_parameter('stuck.check_rate_hz',       2.0)

        self._mismatch_dur  = self.get_parameter('stuck.mismatch_duration_s').value
        self._cmd_thresh    = self.get_parameter('stuck.cmd_vel_threshold').value
        self._odom_thresh   = self.get_parameter('stuck.odom_vel_threshold').value
        self._gps_confirm_s = self.get_parameter('stuck.gps_confirm_s').value
        self._gps_confirm_m = self.get_parameter('stuck.gps_confirm_m').value
        check_hz            = self.get_parameter('stuck.check_rate_hz').value

        # State
        self._cmd_vel_speed  = 0.0
        self._odom_speed     = 0.0
        self._mismatch_start: float | None = None

        # GPS confirmation state
        self._lat = None
        self._lon = None
        self._gps_snapshot_lat = None
        self._gps_snapshot_lon = None
        self._gps_snapshot_time: float | None = None

        self._stuck_reported = False  # avoid repeat alerts for same stuck event

        self.create_subscription(Twist,    '/cmd_vel_mux',    self._cmd_cb,    10)
        self.create_subscription(Odometry, '/odom',           self._odom_cb,   10)
        self.create_subscription(NavSatFix, '/gps/fix',       self._gps_cb,    10)

        self._pub_alert  = self.create_publisher(Empty,  '/stuck_alert',  1)
        self._pub_status = self.create_publisher(String, '/stuck/status', 10)

        self.create_timer(1.0 / check_hz, self._check_cb)

        self.get_logger().info('stuck_detector_node ready')

    # ── Subscribers ───────────────────────────────────────────────────────────

    def _cmd_cb(self, msg: Twist):
        self._cmd_vel_speed = math.hypot(msg.linear.x, msg.linear.y)

    def _odom_cb(self, msg: Odometry):
        self._odom_speed = math.hypot(
            msg.twist.twist.linear.x,
            msg.twist.twist.linear.y,
        )

    def _gps_cb(self, msg: NavSatFix):
        if msg.status.status >= 0:
            self._lat = msg.latitude
            self._lon = msg.longitude

    # ── Detection logic ───────────────────────────────────────────────────────

    def _check_cb(self):
        now = time.time()

        commanded = self._cmd_vel_speed > self._cmd_thresh
        moving    = self._odom_speed    > self._odom_thresh

        # ── Layer 1: velocity mismatch ────────────────────────────────────────
        if commanded and not moving:
            if self._mismatch_start is None:
                self._mismatch_start = now
        else:
            # Clear mismatch if robot stopped or started moving
            self._mismatch_start   = None
            self._gps_snapshot_lat  = None
            self._gps_snapshot_lon  = None
            self._gps_snapshot_time = None
            self._stuck_reported    = False
            self._publish_status(stuck=False, mismatch_s=0.0, gps_drift_m=0.0)
            return

        mismatch_s = now - self._mismatch_start

        # ── Layer 2: GPS confirmation ─────────────────────────────────────────
        gps_drift_m = 0.0
        if mismatch_s >= self._mismatch_dur and self._lat is not None:
            if self._gps_snapshot_lat is None:
                # Take GPS snapshot at the moment of layer-1 confirmation
                self._gps_snapshot_lat  = self._lat
                self._gps_snapshot_lon  = self._lon
                self._gps_snapshot_time = now

            gps_elapsed = now - self._gps_snapshot_time
            gps_drift_m = _haversine(
                self._gps_snapshot_lat, self._gps_snapshot_lon,
                self._lat, self._lon,
            )

            if gps_elapsed >= self._gps_confirm_s:
                if gps_drift_m < self._gps_confirm_m and not self._stuck_reported:
                    self._stuck_reported = True
                    self._pub_alert.publish(Empty())
                    self.get_logger().warn(
                        f'STUCK CONFIRMED — mismatch {mismatch_s:.1f}s, '
                        f'GPS drift {gps_drift_m:.2f}m over {gps_elapsed:.1f}s'
                    )

        self._publish_status(
            stuck=self._stuck_reported,
            mismatch_s=round(mismatch_s, 1),
            gps_drift_m=round(gps_drift_m, 2),
        )

    def _publish_status(self, stuck: bool, mismatch_s: float, gps_drift_m: float):
        data = {
            'stuck':       stuck,
            'mismatch_s':  mismatch_s,
            'gps_drift_m': gps_drift_m,
        }
        msg = String()
        msg.data = json.dumps(data)
        self._pub_status.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = StuckDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
