#!/usr/bin/env python3
"""
boundary_manager_node — GPS boundary polygon management.

Maintains a GPS polygon boundary (list of lat/lon points).  The boundary
can be set two ways:
  1. Walking the perimeter with the robot and pressing the RC CH7 button
     (rising edge on /rc/boundary_btn publishes each GPS fix as a waypoint)
  2. Drawing on the Flutter app map (MQTT app/boundary topic)

Enforcement (10 Hz):
  - "warning zone": robot is within warn_margin_m metres of any boundary edge
  - "violation": robot has been outside the polygon for > violation_timeout_s

Topics subscribed:
  /rc/boundary_btn   (std_msgs/Empty)   — RC button press: record current GPS fix
  /gps/fix           (sensor_msgs/NavSatFix) — current GPS position
  /app/boundary      (std_msgs/String)  — JSON array [{lat,lon},...] from app
  /current_mode      (std_msgs/String)  — suppress enforcement in MANUAL mode

Topics published:
  /boundary_polygon  (std_msgs/String)  — JSON [{lat,lon},...] (full polygon)
  /boundary_status   (std_msgs/String)  — JSON {inside, warning, violation, dist_to_edge}

Parameters:
  boundary.save_path         string  '/home/pi/boundary.json'
  boundary.warn_margin_m     float   2.0   metres from edge to trigger warning
  boundary.violation_timeout_s float 5.0   seconds outside before violation flag
  boundary.check_rate_hz     float   10.0
  boundary.enforce_in_manual bool    false  — skip enforcement in MANUAL mode
"""

import json
import math
import os
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, String
from sensor_msgs.msg import NavSatFix

EARTH_R = 6_371_000.0  # metres


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in metres."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def _point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    """Ray-casting algorithm in lat/lon space."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]['lon'], polygon[i]['lat']
        xj, yj = polygon[j]['lon'], polygon[j]['lat']
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def _dist_to_edge(lat: float, lon: float, polygon: list) -> float:
    """Minimum distance (metres) from point to any polygon edge."""
    n = len(polygon)
    min_d = float('inf')
    for i in range(n):
        j = (i + 1) % n
        # Use midpoint of edge as approximation (faster than true segment distance)
        mid_lat = (polygon[i]['lat'] + polygon[j]['lat']) / 2
        mid_lon = (polygon[i]['lon'] + polygon[j]['lon']) / 2
        d = _haversine(lat, lon, mid_lat, mid_lon)
        if d < min_d:
            min_d = d
    return min_d


class BoundaryManagerNode(Node):

    def __init__(self):
        super().__init__('boundary_manager_node')

        self.declare_parameter('boundary.save_path',         '/home/pi/boundary.json')
        self.declare_parameter('boundary.warn_margin_m',     2.0)
        self.declare_parameter('boundary.violation_timeout_s', 5.0)
        self.declare_parameter('boundary.check_rate_hz',     10.0)
        self.declare_parameter('boundary.enforce_in_manual', False)

        self._save_path      = self.get_parameter('boundary.save_path').value
        self._warn_margin    = self.get_parameter('boundary.warn_margin_m').value
        self._viol_timeout   = self.get_parameter('boundary.violation_timeout_s').value
        check_hz             = self.get_parameter('boundary.check_rate_hz').value
        self._enforce_manual = self.get_parameter('boundary.enforce_in_manual').value

        # State
        self._polygon: list = []
        self._recording = False   # True while RC button held for boundary walk
        self._current_lat = None
        self._current_lon = None
        self._current_mode = 'MANUAL'
        self._outside_since: float | None = None

        # Load saved boundary if it exists
        self._load_boundary()

        # Subscribers
        self.create_subscription(Empty,      '/rc/boundary_btn', self._btn_cb,    1)
        self.create_subscription(NavSatFix,  '/gps/fix',         self._gps_cb,   10)
        self.create_subscription(String,     '/app/boundary',    self._app_bnd_cb, 10)
        self.create_subscription(String,     '/current_mode',    self._mode_cb,  10)

        # Publishers
        self._pub_polygon = self.create_publisher(String, '/boundary_polygon', 10)
        self._pub_status  = self.create_publisher(String, '/boundary_status',  10)

        self.create_timer(1.0 / check_hz, self._check_cb)
        self.create_timer(2.0,            self._publish_polygon)

        self.get_logger().info(
            f'boundary_manager_node ready — {len(self._polygon)} waypoints loaded'
        )

    # ── GPS ───────────────────────────────────────────────────────────────────

    def _gps_cb(self, msg: NavSatFix):
        if msg.status.status < 0:
            return
        self._current_lat = msg.latitude
        self._current_lon = msg.longitude

    # ── RC button: record current GPS as polygon waypoint ─────────────────────

    def _btn_cb(self, _msg: Empty):
        if self._current_lat is None:
            self.get_logger().warn('RC boundary button: no GPS fix yet')
            return
        pt = {'lat': self._current_lat, 'lon': self._current_lon}
        self._polygon.append(pt)
        self._save_boundary()
        self.get_logger().info(
            f'Boundary waypoint added: {pt}  (total: {len(self._polygon)})'
        )
        self._publish_polygon()

    # ── App boundary (replaces existing polygon) ──────────────────────────────

    def _app_bnd_cb(self, msg: String):
        try:
            pts = json.loads(msg.data)
            if not isinstance(pts, list) or len(pts) < 3:
                raise ValueError('Boundary must have >= 3 points')
            for p in pts:
                if 'lat' not in p or 'lon' not in p:
                    raise ValueError('Each point must have lat and lon')
            self._polygon = pts
            self._save_boundary()
            self.get_logger().info(
                f'Boundary received from app: {len(pts)} points'
            )
            self._publish_polygon()
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            self.get_logger().warn(f'Invalid app/boundary: {exc}')

    # ── Mode ──────────────────────────────────────────────────────────────────

    def _mode_cb(self, msg: String):
        self._current_mode = msg.data

    # ── Enforcement check ─────────────────────────────────────────────────────

    def _check_cb(self):
        if len(self._polygon) < 3:
            return
        if self._current_lat is None:
            return
        skip_enforce = (
            self._current_mode == 'MANUAL' and not self._enforce_manual
        )

        inside = _point_in_polygon(self._current_lat, self._current_lon, self._polygon)
        dist   = _dist_to_edge(self._current_lat, self._current_lon, self._polygon)
        warning   = inside and dist < self._warn_margin
        violation = False

        if not inside and not skip_enforce:
            if self._outside_since is None:
                self._outside_since = time.time()
            elif time.time() - self._outside_since > self._viol_timeout:
                violation = True
                self.get_logger().warn(
                    f'BOUNDARY VIOLATION — outside for '
                    f'{time.time() - self._outside_since:.1f}s'
                )
        else:
            self._outside_since = None

        status = {
            'inside':    inside,
            'warning':   warning,
            'violation': violation,
            'dist_to_edge_m': round(dist, 2),
        }
        msg = String()
        msg.data = json.dumps(status)
        self._pub_status.publish(msg)

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save_boundary(self):
        try:
            with open(self._save_path, 'w') as f:
                json.dump(self._polygon, f)
        except OSError as exc:
            self.get_logger().warn(f'Cannot save boundary: {exc}')

    def _load_boundary(self):
        if not os.path.exists(self._save_path):
            return
        try:
            with open(self._save_path) as f:
                self._polygon = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self.get_logger().warn(f'Cannot load boundary: {exc}')

    def _publish_polygon(self):
        msg = String()
        msg.data = json.dumps(self._polygon)
        self._pub_polygon.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = BoundaryManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
