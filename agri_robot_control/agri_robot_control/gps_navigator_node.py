#!/usr/bin/env python3
"""
gps_navigator_node — Pure-pursuit GPS waypoint navigator (replaces Nav2).

Consumes a list of GPS waypoints and drives the robot through them using a
pure-pursuit controller.  Heading is taken from EKF yaw (/odometry/global),
NOT from GPS track direction (unreliable below ~0.2 m/s).

Subscriptions:
  /odometry/global   (nav_msgs/Odometry)  EKF-fused global pose
  /waypoints_goal    (std_msgs/String)    JSON [{lat,lon},...] — new mission
  /navigator/cancel  (std_msgs/Empty)     abort current mission
  /current_mode      (std_msgs/String)    pause when not AUTO

Publications:
  /cmd_vel_auto      (geometry_msgs/Twist)  velocity commands to twist_mux
  /navigator/status  (std_msgs/String)      JSON {active, waypoint_idx, total, dist_to_next}

Parameters:
  nav.lookahead_m       float  2.0   pure-pursuit lookahead distance
  nav.waypoint_tol_m    float  1.5   consider waypoint reached within this radius
  nav.max_linear_vel    float  0.8   m/s
  nav.max_angular_vel   float  0.6   rad/s
  nav.kp_angular        float  1.2   proportional gain for heading error
  nav.goal_lat          float  0.0   optional single-point goal (used by return-home)
  nav.goal_lon          float  0.0
"""

import json
import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Empty, String

EARTH_R = 6_371_000.0


def _bearing(lat1, lon1, lat2, lon2) -> float:
    """True bearing in radians from point1 → point2 (0 = north, CW positive)."""
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlon  = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = (math.cos(rlat1) * math.sin(rlat2)
         - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    return math.atan2(x, y)


def _haversine(lat1, lon1, lat2, lon2) -> float:
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def _yaw_from_quaternion(q) -> float:
    """Extract yaw angle (radians) from geometry_msgs Quaternion."""
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def _angle_diff(a: float, b: float) -> float:
    """Shortest signed angle from b to a (radians)."""
    d = a - b
    while d >  math.pi: d -= 2 * math.pi
    while d < -math.pi: d += 2 * math.pi
    return d


def _ros_yaw_to_bearing(yaw: float) -> float:
    """
    Convert ROS yaw (ENU, 0=East, CCW positive) to geographic bearing
    (0=North, CW positive).
    """
    return math.fmod(math.pi / 2.0 - yaw + 2 * math.pi, 2 * math.pi)


class GPSNavigatorNode(Node):

    def __init__(self):
        super().__init__('gps_navigator_node')

        self.declare_parameter('nav.lookahead_m',    2.0)
        self.declare_parameter('nav.waypoint_tol_m', 1.5)
        self.declare_parameter('nav.max_linear_vel', 0.8)
        self.declare_parameter('nav.max_angular_vel', 0.6)
        self.declare_parameter('nav.kp_angular',     1.2)
        self.declare_parameter('nav.goal_lat',        0.0)
        self.declare_parameter('nav.goal_lon',        0.0)

        self._lookahead  = self.get_parameter('nav.lookahead_m').value
        self._wp_tol     = self.get_parameter('nav.waypoint_tol_m').value
        self._max_v      = self.get_parameter('nav.max_linear_vel').value
        self._max_w      = self.get_parameter('nav.max_angular_vel').value
        self._kp_w       = self.get_parameter('nav.kp_angular').value

        # Check for single-point goal parameter (return-home use case)
        goal_lat = self.get_parameter('nav.goal_lat').value
        goal_lon = self.get_parameter('nav.goal_lon').value
        if goal_lat != 0.0 or goal_lon != 0.0:
            self._waypoints = [{'lat': goal_lat, 'lon': goal_lon}]
        else:
            self._waypoints: list = []

        self._wp_idx       = 0
        self._active       = False
        self._current_mode = 'MANUAL'

        # Robot position from EKF
        self._robot_lat  = None
        self._robot_lon  = None
        self._robot_yaw  = 0.0   # ENU yaw from EKF

        self.create_subscription(Odometry, '/odometry/global', self._odom_cb,    10)
        self.create_subscription(String,   '/waypoints_goal',  self._goal_cb,    10)
        self.create_subscription(Empty,    '/navigator/cancel', self._cancel_cb,  1)
        self.create_subscription(String,   '/current_mode',    self._mode_cb,    10)

        self._pub_cmd    = self.create_publisher(Twist, '/cmd_vel_auto',      10)
        self._pub_status = self.create_publisher(String, '/navigator/status', 10)

        self.create_timer(0.1, self._control_loop)   # 10 Hz
        self.create_timer(1.0, self._publish_status)

        self.get_logger().info('gps_navigator_node ready')

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _odom_cb(self, msg: Odometry):
        # /odometry/global uses NavSatFix-derived lat/lon in pose position
        # robot_localization publishes in ECEF-projected metres; we need lat/lon.
        # For real use, subscribe to /gps/fix for absolute lat/lon and
        # /odometry/global for heading only.
        #
        # Here we store yaw for heading control; lat/lon updated by GPS separately.
        self._robot_yaw = _yaw_from_quaternion(
            msg.pose.pose.orientation
        )

    def _gps_cb(self, msg):
        self._robot_lat = msg.latitude
        self._robot_lon = msg.longitude

    def _goal_cb(self, msg: String):
        try:
            wps = json.loads(msg.data)
            if not isinstance(wps, list) or len(wps) == 0:
                raise ValueError('Empty waypoint list')
            self._waypoints = wps
            self._wp_idx    = 0
            self._active    = True
            self.get_logger().info(
                f'Navigator: new mission with {len(wps)} waypoints'
            )
        except (json.JSONDecodeError, ValueError) as exc:
            self.get_logger().warn(f'Invalid waypoints_goal: {exc}')

    def _cancel_cb(self, _msg: Empty):
        self._active = False
        self._stop()
        self.get_logger().info('Navigator: mission cancelled')

    def _mode_cb(self, msg: String):
        prev = self._current_mode
        self._current_mode = msg.data
        if prev == 'AUTO' and self._current_mode != 'AUTO':
            self._stop()

    # ── Control loop (10 Hz) ──────────────────────────────────────────────────

    def _control_loop(self):
        if not self._active:
            return
        if self._current_mode != 'AUTO':
            return
        if self._robot_lat is None or self._wp_idx >= len(self._waypoints):
            self._active = False
            self._stop()
            if self._wp_idx >= len(self._waypoints) and len(self._waypoints) > 0:
                self.get_logger().info('Navigator: mission complete')
            return

        target = self._waypoints[self._wp_idx]
        dist   = _haversine(self._robot_lat, self._robot_lon,
                            target['lat'],   target['lon'])

        if dist < self._wp_tol:
            self._wp_idx += 1
            self.get_logger().info(
                f'Navigator: reached waypoint {self._wp_idx}/{len(self._waypoints)}'
            )
            if self._wp_idx >= len(self._waypoints):
                self._active = False
                self._stop()
                self.get_logger().info('Navigator: mission complete')
            return

        # Compute bearing to target
        target_bearing = _bearing(
            self._robot_lat, self._robot_lon,
            target['lat'],   target['lon']
        )
        robot_bearing = _ros_yaw_to_bearing(self._robot_yaw)
        heading_error = _angle_diff(target_bearing, robot_bearing)

        # Pure pursuit: scale forward speed by how well we're aligned
        alignment = math.cos(heading_error)
        linear_v  = self._max_v * max(0.0, alignment)
        angular_v = max(-self._max_w, min(self._max_w, self._kp_w * heading_error))

        cmd = Twist()
        cmd.linear.x  = linear_v
        cmd.angular.z = angular_v
        self._pub_cmd.publish(cmd)

    def _stop(self):
        self._pub_cmd.publish(Twist())

    def _publish_status(self):
        dist = 0.0
        if (self._robot_lat is not None
                and self._wp_idx < len(self._waypoints)):
            t = self._waypoints[self._wp_idx]
            dist = _haversine(self._robot_lat, self._robot_lon,
                              t['lat'], t['lon'])
        status = {
            'active':       self._active,
            'waypoint_idx': self._wp_idx,
            'total':        len(self._waypoints),
            'dist_to_next': round(dist, 2),
        }
        msg = String()
        msg.data = json.dumps(status)
        self._pub_status.publish(msg)

    def destroy_node(self):
        self._stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GPSNavigatorNode()
    # Also subscribe to GPS fix directly
    from sensor_msgs.msg import NavSatFix
    node.create_subscription(NavSatFix, '/gps/fix', node._gps_cb, 10)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
