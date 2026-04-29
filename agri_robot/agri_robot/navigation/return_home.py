#!/usr/bin/env python3
"""
return_home — Navigate the robot back to its startup position.

Usage:
    ros2 run agri_robot return_home

Workflow:
    1. Saves current position as home
    2. Waits for user to press Enter (drive robot away with teleop first)
    3. Checks robot has moved at least MIN_DIST metres from home
    4. Sends NavigateToPose goal back to home
    5. Prints distance remaining until arrived

Prerequisites (must be running):
    ros2 launch agri_robot gazebo.launch.py
    ros2 launch agri_robot localization.launch.py
    ros2 launch agri_robot navigation.launch.py
"""
import math

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

MIN_DIST = 1.0   # metres — robot must be at least this far from home before navigating back


class _OdomReader(Node):
    """Reads one message from /odometry/global and stores it."""

    def __init__(self, node_name='_odom_reader'):
        super().__init__(node_name)
        self._pose = None
        self._sub = self.create_subscription(
            Odometry, '/odometry/global', self._cb, 10)

    def _cb(self, msg: Odometry):
        if self._pose is None:
            self._pose = msg.pose.pose

    def spin_until_ready(self):
        while self._pose is None:
            rclpy.spin_once(self, timeout_sec=0.1)

    @property
    def pose(self):
        return self._pose


def _dist(a, b) -> float:
    return math.sqrt((a.position.x - b.position.x) ** 2 +
                     (a.position.y - b.position.y) ** 2)


def _fix_quaternion(orientation):
    """Return w=1 if quaternion is zero (invalid), else unchanged."""
    total = (orientation.x ** 2 + orientation.y ** 2 +
             orientation.z ** 2 + orientation.w ** 2)
    if total < 0.01:
        orientation.w = 1.0
    return orientation


def main():
    rclpy.init()

    # ── 1. Save home ───────────────────────────────────────────────────────
    saver = _OdomReader('_home_saver')
    saver.get_logger().info('Waiting for /odometry/global ...')
    saver.spin_until_ready()
    home_pose = saver.pose
    saver.destroy_node()

    print(f'\n>>> HOME saved:  x={home_pose.position.x:.3f}  y={home_pose.position.y:.3f}')
    print('>>> Now drive the robot AWAY from home using teleop.')
    print('>>> When done, come back to this terminal and press Enter...\n')
    input('    [Press Enter to start navigating back to home]\n')

    # ── 2. Read current position ───────────────────────────────────────────
    reader = _OdomReader('_pos_reader')
    reader.spin_until_ready()
    current_pose = reader.pose
    reader.destroy_node()

    dist = _dist(home_pose, current_pose)
    print(f'\n>>> Current pos: x={current_pose.position.x:.3f}  y={current_pose.position.y:.3f}')
    print(f'>>> Distance from home: {dist:.2f} m')

    if dist < MIN_DIST:
        print(f'\n>>> WARNING: robot is only {dist:.2f} m from home (minimum {MIN_DIST} m).')
        print('>>> Drive the robot further away before testing return-to-home.')
        print('>>> Continuing anyway — robot may not visibly move.\n')

    # ── 3. Wait for Nav2 action server ────────────────────────────────────
    navigator = BasicNavigator()
    navigator.get_logger().info('Waiting for navigate_to_pose action server...')
    _ac = ActionClient(navigator, NavigateToPose, 'navigate_to_pose')
    while not _ac.wait_for_server(timeout_sec=1.0):
        navigator.get_logger().info('navigate_to_pose not ready, waiting...')
    navigator.get_logger().info('Nav2 ready — sending goal!')

    # ── 4. Send goal ───────────────────────────────────────────────────────
    goal = PoseStamped()
    goal.header.frame_id = 'map'
    goal.header.stamp = navigator.get_clock().now().to_msg()
    goal.pose.position = home_pose.position
    goal.pose.orientation = _fix_quaternion(home_pose.orientation)

    navigator.get_logger().info(
        f'Returning to home: x={home_pose.position.x:.3f}  y={home_pose.position.y:.3f}')
    navigator.goToPose(goal)

    # ── 5. Monitor progress ────────────────────────────────────────────────
    while not navigator.isTaskComplete():
        feedback = navigator.getFeedback()
        if feedback:
            navigator.get_logger().info(
                f'Distance remaining: {feedback.distance_remaining:.2f} m')

    # ── 6. Report result ───────────────────────────────────────────────────
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
