#!/usr/bin/env python3
"""
follow_mode_node — Follow-the-phone GPS mode (Phase 1).

Receives the Android app's GPS position at ~5 Hz via MQTT (republished as
/app/follow_position).  Drives the robot to maintain a configurable
follow distance behind the target.

Phase 4 upgrade: add camera-based person tracking (YOLOv8).  For now,
GPS-only.  Camera support stub is left at the bottom.

Subscriptions:
  /app/follow_position  (std_msgs/String)   JSON {lat, lon}  — phone GPS, 5 Hz
  /gps/fix              (sensor_msgs/NavSatFix) — robot GPS
  /odometry/global      (nav_msgs/Odometry) — robot heading (EKF)
  /current_mode         (std_msgs/String)   — active only in FOLLOW mode

Publications:
  /cmd_vel_auto         (geometry_msgs/Twist)
  /follow/status        (std_msgs/String)   JSON {active, dist_to_target, heading_err}

Parameters:
  follow.distance_m      float  5.0   target follow distance in metres
  follow.min_move_m      float  0.5   only react if target moved more than this
  follow.max_speed       float  0.6   m/s
  follow.max_angular     float  0.6   rad/s
  follow.kp_linear       float  0.4   proportional gain for distance error
  follow.kp_angular      float  1.0
  follow.position_timeout_s float 3.0  stop if no phone GPS for this duration
"""

import json
import math
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import String

EARTH_R = 6_371_000.0


def _haversine(lat1, lon1, lat2, lon2) -> float:
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def _bearing(lat1, lon1, lat2, lon2) -> float:
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = (math.cos(rlat1) * math.sin(rlat2)
         - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    return math.atan2(x, y)


def _yaw_from_q(q) -> float:
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


def _ros_yaw_to_bearing(yaw: float) -> float:
    return math.fmod(math.pi / 2.0 - yaw + 2 * math.pi, 2 * math.pi)


def _angle_diff(a: float, b: float) -> float:
    d = a - b
    while d >  math.pi: d -= 2 * math.pi
    while d < -math.pi: d += 2 * math.pi
    return d


class FollowModeNode(Node):

    def __init__(self):
        super().__init__('follow_mode_node')

        self.declare_parameter('follow.distance_m',       5.0)
        self.declare_parameter('follow.min_move_m',       0.5)
        self.declare_parameter('follow.max_speed',        0.6)
        self.declare_parameter('follow.max_angular',      0.6)
        self.declare_parameter('follow.kp_linear',        0.4)
        self.declare_parameter('follow.kp_angular',       1.0)
        self.declare_parameter('follow.position_timeout_s', 3.0)

        self._follow_dist  = self.get_parameter('follow.distance_m').value
        self._min_move     = self.get_parameter('follow.min_move_m').value
        self._max_v        = self.get_parameter('follow.max_speed').value
        self._max_w        = self.get_parameter('follow.max_angular').value
        self._kp_v         = self.get_parameter('follow.kp_linear').value
        self._kp_w         = self.get_parameter('follow.kp_angular').value
        self._pos_timeout  = self.get_parameter('follow.position_timeout_s').value

        # State
        self._target_lat  = None
        self._target_lon  = None
        self._prev_target_lat = None
        self._prev_target_lon = None
        self._last_target_time = 0.0

        self._robot_lat  = None
        self._robot_lon  = None
        self._robot_yaw  = 0.0

        self._current_mode = 'MANUAL'

        self.create_subscription(String,    '/app/follow_position', self._target_cb, 10)
        self.create_subscription(NavSatFix, '/gps/fix',             self._gps_cb,   10)
        self.create_subscription(Odometry,  '/odometry/global',     self._odom_cb,  10)
        self.create_subscription(String,    '/current_mode',        self._mode_cb,  10)

        self._pub_cmd    = self.create_publisher(Twist,  '/cmd_vel_auto',   10)
        self._pub_status = self.create_publisher(String, '/follow/status',  10)

        self.create_timer(0.1, self._control_loop)  # 10 Hz
        self.create_timer(1.0, self._publish_status)

        self.get_logger().info('follow_mode_node ready')

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _target_cb(self, msg: String):
        try:
            pos = json.loads(msg.data)
            lat, lon = float(pos['lat']), float(pos['lon'])
            # Hysteresis: ignore micro-movements
            if self._target_lat is not None:
                d = _haversine(self._target_lat, self._target_lon, lat, lon)
                if d < self._min_move:
                    return
            self._target_lat      = lat
            self._target_lon      = lon
            self._last_target_time = time.time()
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    def _gps_cb(self, msg: NavSatFix):
        if msg.status.status >= 0:
            self._robot_lat = msg.latitude
            self._robot_lon = msg.longitude

    def _odom_cb(self, msg: Odometry):
        self._robot_yaw = _yaw_from_q(msg.pose.pose.orientation)

    def _mode_cb(self, msg: String):
        prev = self._current_mode
        self._current_mode = msg.data
        if prev == 'FOLLOW' and self._current_mode != 'FOLLOW':
            self._stop()

    # ── Control loop ──────────────────────────────────────────────────────────

    def _control_loop(self):
        if self._current_mode != 'FOLLOW':
            return
        if self._target_lat is None or self._robot_lat is None:
            return

        # Stop if target position is stale
        if time.time() - self._last_target_time > self._pos_timeout:
            self._stop()
            return

        dist = _haversine(self._robot_lat, self._robot_lon,
                          self._target_lat, self._target_lon)
        dist_error = dist - self._follow_dist

        target_bearing = _bearing(self._robot_lat, self._robot_lon,
                                  self._target_lat, self._target_lon)
        robot_bearing  = _ros_yaw_to_bearing(self._robot_yaw)
        heading_error  = _angle_diff(target_bearing, robot_bearing)

        # Only move forward when target is ahead and distance > follow_distance
        if dist_error > 0:
            linear_v = min(self._max_v, self._kp_v * dist_error)
        else:
            linear_v = 0.0

        angular_v = max(-self._max_w,
                        min(self._max_w, self._kp_w * heading_error))

        cmd = Twist()
        cmd.linear.x  = linear_v
        cmd.angular.z = angular_v
        self._pub_cmd.publish(cmd)

    def _stop(self):
        self._pub_cmd.publish(Twist())

    def _publish_status(self):
        dist = 0.0
        h_err = 0.0
        if self._robot_lat is not None and self._target_lat is not None:
            dist  = _haversine(self._robot_lat, self._robot_lon,
                               self._target_lat, self._target_lon)
            tb    = _bearing(self._robot_lat, self._robot_lon,
                             self._target_lat, self._target_lon)
            rb    = _ros_yaw_to_bearing(self._robot_yaw)
            h_err = math.degrees(_angle_diff(tb, rb))

        active = (
            self._current_mode == 'FOLLOW'
            and self._target_lat is not None
            and time.time() - self._last_target_time <= self._pos_timeout
        )
        status = {
            'active':         active,
            'dist_to_target': round(dist, 2),
            'heading_err_deg': round(h_err, 1),
        }
        msg = String()
        msg.data = json.dumps(status)
        self._pub_status.publish(msg)

    def destroy_node(self):
        self._stop()
        super().destroy_node()


# ── Phase 4 camera follow stub ────────────────────────────────────────────────
# When camera tracking is added (YOLOv8 person detection), the detected
# person's position in the camera frame is fused here to generate a bearing
# offset, overriding the GPS-only heading error computed above.
# The GPS-based follow distance continues to govern linear speed.


def main(args=None):
    rclpy.init(args=args)
    node = FollowModeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
