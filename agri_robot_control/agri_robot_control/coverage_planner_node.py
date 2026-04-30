#!/usr/bin/env python3
"""
coverage_planner_node — Boustrophedon (lawnmower) coverage path planner.

Accepts a GPS polygon boundary and generates a back-and-forth sweep path
aligned to the longest axis of the bounding rectangle.

Subscriptions:
  /boundary_polygon   (std_msgs/String)  JSON [{lat,lon},...] polygon
  /app/coverage_config (std_msgs/String) JSON {row_offset, speed} from app

Publications:
  /coverage_waypoints (std_msgs/String)  JSON [{lat,lon},...] ordered waypoints
  /coverage_ready     (std_msgs/Bool)    true when a valid path is available

Parameters:
  coverage.row_offset_m  float  3.0   sweep row spacing in metres (≥2.0 for GPS)
  coverage.start_edge    string 'auto' 'auto'|'north'|'south'|'east'|'west'
  coverage.margin_m      float  1.0   inset margin from boundary edges
"""

import json
import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

EARTH_R = 6_371_000.0


def _latlon_to_xy(lat: float, lon: float, ref_lat: float, ref_lon: float):
    """Approximate lat/lon to local ENU metres."""
    x = math.radians(lon - ref_lon) * EARTH_R * math.cos(math.radians(ref_lat))
    y = math.radians(lat - ref_lat) * EARTH_R
    return x, y


def _xy_to_latlon(x: float, y: float, ref_lat: float, ref_lon: float):
    lat = ref_lat + math.degrees(y / EARTH_R)
    lon = ref_lon + math.degrees(x / (EARTH_R * math.cos(math.radians(ref_lat))))
    return lat, lon


def _rotate(x: float, y: float, angle: float):
    """Rotate (x, y) by angle radians."""
    c, s = math.cos(angle), math.sin(angle)
    return c * x - s * y, s * x + c * y


def _boustrophedon(polygon_latlon: list, row_offset: float, margin: float):
    """
    Generate boustrophedon waypoints for a GPS polygon.

    Returns list of {lat, lon} dicts.
    """
    if len(polygon_latlon) < 3:
        return []

    # Use centroid as local origin
    ref_lat = sum(p['lat'] for p in polygon_latlon) / len(polygon_latlon)
    ref_lon = sum(p['lon'] for p in polygon_latlon) / len(polygon_latlon)

    # Convert to local XY
    pts_xy = [_latlon_to_xy(p['lat'], p['lon'], ref_lat, ref_lon) for p in polygon_latlon]

    # Find minimum bounding rectangle orientation (simplified: use longest edge angle)
    best_angle = 0.0
    best_len   = 0.0
    n = len(pts_xy)
    for i in range(n):
        j = (i + 1) % n
        dx = pts_xy[j][0] - pts_xy[i][0]
        dy = pts_xy[j][1] - pts_xy[i][1]
        length = math.hypot(dx, dy)
        if length > best_len:
            best_len   = length
            best_angle = math.atan2(dy, dx)

    # Rotate polygon so longest edge is along X axis
    rot_pts = [_rotate(x, y, -best_angle) for x, y in pts_xy]

    x_coords = [p[0] for p in rot_pts]
    y_coords = [p[1] for p in rot_pts]
    x_min, x_max = min(x_coords) + margin, max(x_coords) - margin
    y_min, y_max = min(y_coords) + margin, max(y_coords) - margin

    if x_max <= x_min or y_max <= y_min:
        return []

    # Generate sweep rows
    waypoints_rot = []
    y  = y_min
    row = 0
    while y <= y_max:
        if row % 2 == 0:
            waypoints_rot.append((x_min, y))
            waypoints_rot.append((x_max, y))
        else:
            waypoints_rot.append((x_max, y))
            waypoints_rot.append((x_min, y))
        y += row_offset
        row += 1

    # Rotate back and convert to lat/lon
    result = []
    for rx, ry in waypoints_rot:
        wx, wy = _rotate(rx, ry, best_angle)
        lat, lon = _xy_to_latlon(wx, wy, ref_lat, ref_lon)
        result.append({'lat': round(lat, 8), 'lon': round(lon, 8)})

    return result


class CoveragePlannerNode(Node):

    def __init__(self):
        super().__init__('coverage_planner_node')

        self.declare_parameter('coverage.row_offset_m', 3.0)
        self.declare_parameter('coverage.margin_m',     1.0)

        self._row_offset = self.get_parameter('coverage.row_offset_m').value
        self._margin     = self.get_parameter('coverage.margin_m').value

        self._polygon: list = []
        self._waypoints: list = []

        self.create_subscription(String, '/boundary_polygon',   self._boundary_cb,    10)
        self.create_subscription(String, '/app/coverage_config', self._config_cb,     10)

        self._pub_wp    = self.create_publisher(String, '/coverage_waypoints', 10)
        self._pub_ready = self.create_publisher(Bool,   '/coverage_ready',     10)

        self.get_logger().info('coverage_planner_node ready')

    def _boundary_cb(self, msg: String):
        try:
            pts = json.loads(msg.data)
            if len(pts) < 3:
                return
            self._polygon = pts
            self._plan()
        except (json.JSONDecodeError, KeyError):
            pass

    def _config_cb(self, msg: String):
        try:
            cfg = json.loads(msg.data)
            if 'row_offset' in cfg:
                self._row_offset = max(2.0, float(cfg['row_offset']))
            if self._polygon:
                self._plan()
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    def _plan(self):
        wps = _boustrophedon(self._polygon, self._row_offset, self._margin)
        self._waypoints = wps

        wp_msg = String()
        wp_msg.data = json.dumps(wps)
        self._pub_wp.publish(wp_msg)

        ready_msg = Bool()
        ready_msg.data = len(wps) > 0
        self._pub_ready.publish(ready_msg)

        self.get_logger().info(
            f'Coverage plan: {len(wps)} waypoints, '
            f'row_offset={self._row_offset}m'
        )


def main(args=None):
    rclpy.init(args=args)
    node = CoveragePlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
