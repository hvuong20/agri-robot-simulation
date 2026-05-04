#!/usr/bin/env python3
"""
mqtt_bridge_node — Bidirectional MQTT ↔ ROS 2 bridge.

Connects to a local Mosquitto broker (or cloud fallback) and:
  - Publishes robot telemetry to MQTT so the Flutter app can display it
  - Republishes MQTT app commands to ROS 2 topics

MQTT → ROS 2:
  app/command         → /app/command         (std_msgs/String, JSON passthrough)
  app/estop           → /estop_trigger        (std_msgs/Empty)
  app/boundary        → /app/boundary         (std_msgs/String, JSON passthrough)
  app/follow_position → /app/follow_position  (std_msgs/String, JSON passthrough)
  app/coverage_config → /app/coverage_config  (std_msgs/String, JSON passthrough)

ROS 2 → MQTT (10 Hz for position, 1 Hz for status):
  /gps/fix            → robot/position   {lat, lon, heading_deg, mode}
  /current_mode       → robot/position   (mode field)
  /boundary_status    → robot/status     (part of status JSON)
  /navigator/status   → robot/status     (part of status JSON)
  /stuck/status       → robot/status     (part of status JSON)
  /follow/status      → robot/status     (part of status JSON)
  /coverage_waypoints → robot/path       (full waypoint array)
  /stuck_alert        → robot/alert      {type: "stuck"} — immediate QoS 1

Parameters:
  mqtt.broker_host   string  'localhost'
  mqtt.broker_port   int     1883
  mqtt.keepalive_s   int     60
  mqtt.client_id     string  'agri_robot_pi'
  mqtt.reconnect_s   float   5.0   reconnect interval on disconnect
  mqtt.position_hz   float   10.0  robot/position publish rate
  mqtt.status_hz     float   1.0   robot/status publish rate
"""

import json
import math
import time
import threading

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Empty, String


def _yaw_from_q(q) -> float:
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class MQTTBridgeNode(Node):

    def __init__(self):
        super().__init__('mqtt_bridge_node')

        self.declare_parameter('mqtt.broker_host',  'localhost')
        self.declare_parameter('mqtt.broker_port',  1883)
        self.declare_parameter('mqtt.keepalive_s',  60)
        self.declare_parameter('mqtt.client_id',    'agri_robot_pi')
        self.declare_parameter('mqtt.reconnect_s',  5.0)
        self.declare_parameter('mqtt.position_hz',  10.0)
        self.declare_parameter('mqtt.status_hz',    1.0)

        self._host        = self.get_parameter('mqtt.broker_host').value
        self._port        = self.get_parameter('mqtt.broker_port').value
        self._keepalive   = self.get_parameter('mqtt.keepalive_s').value
        self._client_id   = self.get_parameter('mqtt.client_id').value
        self._reconnect_s = self.get_parameter('mqtt.reconnect_s').value
        pos_hz            = self.get_parameter('mqtt.position_hz').value
        status_hz         = self.get_parameter('mqtt.status_hz').value

        # Telemetry state
        self._lat           = 0.0
        self._lon           = 0.0
        self._heading_deg   = 0.0
        self._current_mode  = 'MANUAL'
        self._bnd_status    = {}
        self._nav_status    = {}
        self._stuck_status  = {}
        self._follow_status = {}

        # MQTT client
        self._mqtt = None
        self._mqtt_connected = False
        self._connect_thread = threading.Thread(
            target=self._mqtt_connect_loop, daemon=True
        )
        self._connect_thread.start()

        # ROS subscribers
        self.create_subscription(NavSatFix, '/gps/fix',           self._gps_cb,    10)
        self.create_subscription(Odometry,  '/odometry/global',   self._odom_cb,   10)
        self.create_subscription(String,    '/current_mode',      self._mode_cb,   10)
        self.create_subscription(String,    '/boundary_status',   self._bnd_cb,    10)
        self.create_subscription(String,    '/navigator/status',  self._nav_cb,    10)
        self.create_subscription(String,    '/stuck/status',      self._stuck_cb,  10)
        self.create_subscription(String,    '/follow/status',     self._follow_cb, 10)
        self.create_subscription(Empty,     '/stuck_alert',       self._stuck_alert_cb, 1)
        self.create_subscription(String,    '/coverage_waypoints', self._path_cb,  10)

        # ROS publishers (MQTT → ROS)
        self._pub_cmd    = self.create_publisher(String, '/app/command',         10)
        self._pub_estop  = self.create_publisher(Empty,  '/estop_trigger',        1)
        self._pub_bnd    = self.create_publisher(String, '/app/boundary',         10)
        self._pub_follow = self.create_publisher(String, '/app/follow_position',  10)
        self._pub_cov    = self.create_publisher(String, '/app/coverage_config',  10)

        # Publish timers
        self.create_timer(1.0 / pos_hz,    self._pub_position)
        self.create_timer(1.0 / status_hz, self._pub_status)

        self.get_logger().info(
            f'mqtt_bridge_node ready — connecting to {self._host}:{self._port}'
        )

    # ── MQTT connection loop (runs in background thread) ──────────────────────

    def _mqtt_connect_loop(self):
        while rclpy.ok():
            try:
                import paho.mqtt.client as mqtt
            except ImportError:
                self.get_logger().error(
                    'paho-mqtt not installed — run: pip3 install paho-mqtt'
                )
                time.sleep(30)
                continue

            client = mqtt.Client(client_id=self._client_id)
            client.on_connect    = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message    = self._on_message

            try:
                client.connect(self._host, self._port, self._keepalive)
                self._mqtt = client
                client.loop_forever()   # blocks until disconnect
            except Exception as exc:
                self.get_logger().warn(
                    f'MQTT connect failed: {exc} — retrying in {self._reconnect_s}s'
                )
            self._mqtt_connected = False
            self._mqtt = None
            time.sleep(self._reconnect_s)

    def _on_connect(self, client, _ud, _flags, rc):
        if rc == 0:
            self._mqtt_connected = True
            self.get_logger().info('MQTT connected')
            for topic in (
                'app/command', 'app/estop', 'app/boundary',
                'app/follow_position', 'app/coverage_config',
            ):
                client.subscribe(topic, qos=1)
        else:
            self.get_logger().warn(f'MQTT connect refused: rc={rc}')

    def _on_disconnect(self, _client, _ud, rc):
        self._mqtt_connected = False
        self.get_logger().warn(f'MQTT disconnected (rc={rc})')

    def _on_message(self, _client, _ud, msg):
        topic   = msg.topic
        payload = msg.payload.decode('utf-8', errors='replace')

        if topic == 'app/command':
            out = String(); out.data = payload
            self._pub_cmd.publish(out)
        elif topic == 'app/estop':
            self._pub_estop.publish(Empty())
            self.get_logger().warn('MQTT ESTOP received from app')
        elif topic == 'app/boundary':
            out = String(); out.data = payload
            self._pub_bnd.publish(out)
        elif topic == 'app/follow_position':
            out = String(); out.data = payload
            self._pub_follow.publish(out)
        elif topic == 'app/coverage_config':
            out = String(); out.data = payload
            self._pub_cov.publish(out)

    # ── ROS callbacks ─────────────────────────────────────────────────────────

    def _gps_cb(self, msg: NavSatFix):
        if msg.status.status >= 0:
            self._lat = msg.latitude
            self._lon = msg.longitude

    def _odom_cb(self, msg: Odometry):
        yaw = _yaw_from_q(msg.pose.pose.orientation)
        bearing = math.degrees(math.fmod(math.pi / 2.0 - yaw + 2 * math.pi, 2 * math.pi))
        self._heading_deg = bearing

    def _mode_cb(self, msg: String):
        self._current_mode = msg.data

    def _bnd_cb(self, msg: String):
        try:
            self._bnd_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _nav_cb(self, msg: String):
        try:
            self._nav_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _stuck_cb(self, msg: String):
        try:
            self._stuck_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _follow_cb(self, msg: String):
        try:
            self._follow_status = json.loads(msg.data)
        except json.JSONDecodeError:
            pass

    def _stuck_alert_cb(self, _msg: Empty):
        # Immediate push notification — QoS 1 so app receives it reliably
        self._mqtt_publish(
            'robot/alert',
            json.dumps({'type': 'stuck', 'ts': time.time()}),
            qos=1,
        )
        self.get_logger().warn('Stuck alert forwarded to MQTT robot/alert')

    def _path_cb(self, msg: String):
        self._mqtt_publish('robot/path', msg.data, qos=0)

    # ── MQTT publish helpers ──────────────────────────────────────────────────

    def _mqtt_publish(self, topic: str, payload: str, qos: int = 0):
        if self._mqtt is not None and self._mqtt_connected:
            try:
                self._mqtt.publish(topic, payload, qos=qos)
            except Exception as exc:
                self.get_logger().warn(f'MQTT publish failed: {exc}')

    def _pub_position(self):
        data = {
            'lat':         round(self._lat, 8),
            'lon':         round(self._lon, 8),
            'heading_deg': round(self._heading_deg, 1),
            'mode':        self._current_mode,
        }
        self._mqtt_publish('robot/position', json.dumps(data), qos=0)

    def _pub_status(self):
        data = {
            'mode':        self._current_mode,
            'gps_fix':     self._lat != 0.0,
            'boundary':    self._bnd_status,
            'navigation':  self._nav_status,
            'stuck':       self._stuck_status,
            'follow':      self._follow_status,
            'mqtt_ok':     self._mqtt_connected,
        }
        self._mqtt_publish('robot/status', json.dumps(data), qos=1)


def main(args=None):
    rclpy.init(args=args)
    node = MQTTBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
