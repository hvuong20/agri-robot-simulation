#!/usr/bin/env python3
"""
return_home — Navigate the robot back to its startup position.

Usage:
    ros2 run agri_robot return_home

Workflow:
    1. Waits for /odometry/global to STABILIZE (EKF converged, no big jumps)
    2. Saves stable position as home
    3. Waits for user to press Enter (drive robot away with teleop first)
    4. Checks robot has moved at least MIN_DIST metres from home
    5. Sends NavigateToPose goal back to home
    6. Prints distance remaining until arrived

Prerequisites (must be running):
    ros2 launch agri_robot gazebo.launch.py
    ros2 launch agri_robot localization.launch.py
    ros2 launch agri_robot navigation.launch.py
"""
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

MIN_DIST      = 1.0   # metres — robot must move at least this far from home
STABLE_SECS   = 3.0   # seconds of stable odometry = EKF converged
STABLE_THRESH = 1.0   # metres — max drift during stable window
EKF_TIMEOUT   = 60.0  # seconds — give up waiting for EKF


class _OdomReader(Node):
    """Subscribes to /odometry/global and tracks latest pose."""

    def __init__(self, node_name='_odom_reader'):
        super().__init__(node_name)
        self._pose = None
        self.create_subscription(Odometry, '/odometry/global', self._cb, 10)

    def _cb(self, msg: Odometry):
        self._pose = msg.pose.pose

    def spin_once(self, timeout=0.1):
        rclpy.spin_once(self, timeout_sec=timeout)

    @property
    def pose(self):
        return self._pose


def _dist(a, b) -> float:
    return math.sqrt((a.position.x - b.position.x) ** 2 +
                     (a.position.y - b.position.y) ** 2)


def _fix_quaternion(ori):
    """Set w=1 if quaternion is invalid (all zeros)."""
    if (ori.x ** 2 + ori.y ** 2 + ori.z ** 2 + ori.w ** 2) < 0.01:
        ori.w = 1.0
    return ori


def wait_for_stable_odometry(reader: _OdomReader) -> bool:
    """
    Wait until /odometry/global stops jumping — signals EKF convergence.
    Returns True when stable, False on timeout.

    /odometry/global outputs absolute UTM coordinates. At startup, before
    GPS/EKF converges, the position can jump hundreds of km. We wait for
    the position to remain within STABLE_THRESH metres for STABLE_SECS
    seconds before trusting it as the true home position.
    """
    print('[EKF] Waiting for odometry to stabilize (EKF convergence) ...')
    print(f'[EKF] Need {STABLE_SECS}s without jumps > {STABLE_THRESH} m  '
          f'(timeout {EKF_TIMEOUT}s)')

    # wait for first message
    t_start = time.time()
    while reader.pose is None:
        reader.spin_once()
        if time.time() - t_start > EKF_TIMEOUT:
            return False

    anchor_pose   = reader.pose
    stable_since  = time.time()
    last_reported = time.time()
    last_log_pose = reader.pose   # separate reference for display — NOT reset on anchor reset

    while time.time() - t_start < EKF_TIMEOUT:
        reader.spin_once()
        current = reader.pose
        if current is None:
            continue

        drift = _dist(anchor_pose, current)

        # Print progress every 2s — show drift vs PREVIOUS log point, not vs anchor
        if time.time() - last_reported > 2.0:
            display_drift = _dist(last_log_pose, current)
            elapsed_stable = time.time() - stable_since
            print(f'[EKF] pos=({current.position.x:.1f}, {current.position.y:.1f})  '
                  f'jump={display_drift:.1f} m  stable={elapsed_stable:.1f}s/{STABLE_SECS}s')
            last_reported = time.time()
            last_log_pose = current

        if drift > STABLE_THRESH:
            # EKF jumped — reset stable window
            anchor_pose  = current
            stable_since = time.time()
        elif time.time() - stable_since >= STABLE_SECS:
            print(f'[EKF] STABLE at x={current.position.x:.3f}  y={current.position.y:.3f}')
            return True

    return False


def main():
    rclpy.init()

    reader = _OdomReader()

    # ── 1. Wait for EKF to converge ───────────────────────────────────────
    if not wait_for_stable_odometry(reader):
        print('\nERROR: /odometry/global did not stabilize within '
              f'{EKF_TIMEOUT}s.')
        print('Check: is localization.launch.py running?  '
              'Is GPS fix available?')
        rclpy.shutdown()
        return

    home_pose = reader.pose
    reader.destroy_node()

    # ── 2. Show home + wait for user to drive away ────────────────────────
    print(f'\n>>> HOME: x={home_pose.position.x:.3f}  y={home_pose.position.y:.3f}')
    print('>>> Drive the robot AWAY using teleop now.')
    print('>>> When done, come back here and press Enter ...\n')
    input('    [Press Enter to navigate back to home]\n')

    # ── 3. Check robot actually moved ─────────────────────────────────────
    curr_reader = _OdomReader('_curr_reader')
    curr_reader.spin_once(timeout=1.0)
    current_pose = curr_reader.pose
    curr_reader.destroy_node()

    if current_pose is not None:
        dist = _dist(home_pose, current_pose)
        print(f'\n>>> Current: x={current_pose.position.x:.3f}  '
              f'y={current_pose.position.y:.3f}')
        print(f'>>> Distance from home: {dist:.2f} m')
        if dist < MIN_DIST:
            print(f'\n>>> WARNING: only {dist:.2f} m from home — '
                  f'drive further before testing.\n')

    # ── 4. Wait for Nav2 ──────────────────────────────────────────────────
    navigator = BasicNavigator()
    navigator.get_logger().info('Waiting for navigate_to_pose action server...')
    _ac = ActionClient(navigator, NavigateToPose, 'navigate_to_pose')
    while not _ac.wait_for_server(timeout_sec=1.0):
        navigator.get_logger().info('navigate_to_pose not ready, waiting...')
    navigator.get_logger().info('Nav2 ready — sending goal!')

    # ── 5. Send goal ───────────────────────────────────────────────────────
    goal = PoseStamped()
    goal.header.frame_id = 'map'
    goal.header.stamp    = navigator.get_clock().now().to_msg()
    goal.pose.position   = home_pose.position
    goal.pose.orientation = _fix_quaternion(home_pose.orientation)

    navigator.get_logger().info(
        f'Returning to x={home_pose.position.x:.3f}  '
        f'y={home_pose.position.y:.3f}')
    navigator.goToPose(goal)

    # ── 6. Monitor ─────────────────────────────────────────────────────────
    while not navigator.isTaskComplete():
        feedback = navigator.getFeedback()
        if feedback:
            navigator.get_logger().info(
                f'Distance remaining: {feedback.distance_remaining:.2f} m')

    result = navigator.getResult()
    if result == TaskResult.SUCCEEDED:
        navigator.get_logger().info('Successfully returned home!')
    elif result == TaskResult.CANCELED:
        navigator.get_logger().warn('Navigation was canceled.')
    else:
        navigator.get_logger().error(f'Navigation failed: {result}')

    rclpy.shutdown()


if __name__ == '__main__':
    main()
