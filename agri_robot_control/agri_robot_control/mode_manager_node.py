#!/usr/bin/env python3
"""
mode_manager_node — Robot operating mode state machine.

State machine:
  STARTUP → MANUAL | AUTO_COVERAGE | FOLLOW
  Any state → ESTOP  (sticky — must be explicitly cleared)
  ESTOP     → MANUAL (after RC CH6 clears AND MQTT confirm, or RC-only)

Inputs:
  /rc/mode_switch    (std_msgs/Int8)    0=MANUAL 1=AUTO 2=FOLLOW  (from RC)
  /estop_trigger     (std_msgs/Empty)   ESTOP active
  /estop_clear       (std_msgs/Empty)   ESTOP hardware released
  MQTT app/command   → republished as /app/command (std_msgs/String, JSON)

Output:
  /current_mode      (std_msgs/String)  "MANUAL"|"AUTO"|"FOLLOW"|"ESTOP"

Parameters:
  mode.estop_require_mqtt_confirm  bool   false
      If true, ESTOP clear requires both RC release AND MQTT ack.
      Default false (RC-only clear is sufficient).
"""

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int8, Empty, String

_RC_MANUAL = 0
_RC_AUTO   = 1
_RC_FOLLOW = 2

_MODE_MAP = {
    'MANUAL': 'MANUAL',
    'AUTO':   'AUTO',
    'FOLLOW': 'FOLLOW',
    'ESTOP':  'ESTOP',
}


class ModManagerNode(Node):

    def __init__(self):
        super().__init__('mode_manager_node')

        self.declare_parameter('mode.estop_require_mqtt_confirm', False)
        self._require_mqtt_confirm = self.get_parameter(
            'mode.estop_require_mqtt_confirm'
        ).value

        # State
        self._current_mode      = 'MANUAL'
        self._estop_active      = False
        self._rc_estop_cleared  = False   # RC CH6 has returned HIGH
        self._mqtt_estop_acked  = False   # app sent estop_clear confirm

        # RC mode subscription
        self.create_subscription(Int8,  '/rc/mode_switch',  self._rc_mode_cb,  10)
        self.create_subscription(Empty, '/estop_trigger',   self._estop_on_cb,  1)
        self.create_subscription(Empty, '/estop_clear',     self._estop_off_cb, 1)
        self.create_subscription(String, '/app/command',    self._app_cmd_cb,  10)

        self._pub_mode = self.create_publisher(String, '/current_mode', 10)

        # Publish mode at 2 Hz for status consumers
        self.create_timer(0.5, self._publish_mode)

        self.get_logger().info('mode_manager_node ready — initial mode: MANUAL')

    # ── ESTOP ─────────────────────────────────────────────────────────────────

    def _estop_on_cb(self, _msg: Empty):
        if not self._estop_active:
            self._estop_active     = True
            self._rc_estop_cleared = False
            self._mqtt_estop_acked = False
            self._current_mode     = 'ESTOP'
            self.get_logger().error('ESTOP — mode locked to ESTOP')
            self._publish_mode()

    def _estop_off_cb(self, _msg: Empty):
        self._rc_estop_cleared = True
        self._try_clear_estop()

    def _try_clear_estop(self):
        if not self._estop_active:
            return
        if self._require_mqtt_confirm and not self._mqtt_estop_acked:
            self.get_logger().info(
                'RC ESTOP released — waiting for MQTT ack before clearing'
            )
            return
        self._estop_active     = False
        self._rc_estop_cleared = False
        self._mqtt_estop_acked = False
        self._current_mode     = 'MANUAL'
        self.get_logger().info('ESTOP cleared — mode restored to MANUAL')
        self._publish_mode()

    # ── RC mode switch ────────────────────────────────────────────────────────

    def _rc_mode_cb(self, msg: Int8):
        if self._estop_active:
            return

        rc_val = msg.data
        if rc_val == _RC_MANUAL:
            new_mode = 'MANUAL'
        elif rc_val == _RC_AUTO:
            new_mode = 'AUTO'
        elif rc_val == _RC_FOLLOW:
            new_mode = 'FOLLOW'
        else:
            return

        if new_mode != self._current_mode:
            self.get_logger().info(
                f'Mode RC: {self._current_mode} → {new_mode}'
            )
            self._current_mode = new_mode

    # ── App command (MQTT bridge republishes here) ────────────────────────────

    def _app_cmd_cb(self, msg: String):
        try:
            cmd = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f'Invalid app/command JSON: {msg.data}')
            return

        cmd_type = cmd.get('type', '')

        if cmd_type == 'estop_clear':
            self._mqtt_estop_acked = True
            if self._rc_estop_cleared or not self._require_mqtt_confirm:
                self._try_clear_estop()
            return

        if cmd_type == 'mode_set':
            if self._estop_active:
                self.get_logger().warn('Mode set ignored — ESTOP active')
                return
            req_mode = cmd.get('mode', '').upper()
            if req_mode in ('MANUAL', 'AUTO', 'FOLLOW'):
                if req_mode != self._current_mode:
                    self.get_logger().info(
                        f'Mode App: {self._current_mode} → {req_mode}'
                    )
                    self._current_mode = req_mode

    # ── Publisher ─────────────────────────────────────────────────────────────

    def _publish_mode(self):
        msg = String()
        msg.data = self._current_mode
        self._pub_mode.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ModManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
