#!/usr/bin/env python3
"""
return_home — Navigate the robot back to its startup position.

Usage:
    ros2 run agri_robot return_home

Prerequisites (must be running):
    ros2 launch agri_robot gazebo.launch.py
    ros2 launch agri_robot localization.launch.py
    ros2 launch agri_robot navigation.launch.py

Workflow:
    1. Reads /odometry/global — saves first message as "home pose"
    2. Waits until Nav2 is fully active
    3. Sends NavigateToPose goal back to saved home position
    4. Prints distance remaining every second until arrived
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


class _HomeSaver(Node):
    """Captures the first /odometry/global message as the home position."""

    def __init__(self):
        super().__init__('_home_saver')
        self._pose = None
        self._sub = self.create_subscription(
            Odometry, '/odometry/global', self._cb, 10)

    def _cb(self, msg: Odometry):
        if self._pose is None:
            self._pose = msg.pose.pose
            self.get_logger().info(
                f'Home saved → x={self._pose.position.x:.3f}  '
                f'y={self._pose.position.y:.3f}')

    @property
    def ready(self) -> bool:
        return self._pose is not None

    @property
    def pose(self):
        return self._pose


def main():
    rclpy.init()

    # ── 1. Save home from current GPS-corrected odometry ──────────────
    saver = _HomeSaver()
    saver.get_logger().info('Waiting for /odometry/global...')
    while not saver.ready:
        rclpy.spin_once(saver, timeout_sec=0.1)
    home_pose = saver.pose
    saver.destroy_node()

    # ── 2. Navigate to home ────────────────────────────────────────────
    navigator = BasicNavigator()
    navigator.get_logger().info('Waiting for navigate_to_pose action server...')
    # Wait for the action server directly — avoids AMCL/lifecycle service checks
    # that don't apply to our GPS-based setup.
    from rclpy.action import ActionClient
    from nav2_msgs.action import NavigateToPose
    _ac = ActionClient(navigator, NavigateToPose, 'navigate_to_pose')
    while not _ac.wait_for_server(timeout_sec=1.0):
        navigator.get_logger().info('navigate_to_pose not ready, waiting...')
    navigator.get_logger().info('Nav2 action server ready!')

    goal = PoseStamped()
    goal.header.frame_id = 'map'
    goal.header.stamp = navigator.get_clock().now().to_msg()
    goal.pose = home_pose

    navigator.get_logger().info(
        f'Returning to home: x={home_pose.position.x:.2f}  '
        f'y={home_pose.position.y:.2f}')
    navigator.goToPose(goal)

    # ── 3. Monitor progress ────────────────────────────────────────────
    while not navigator.isTaskComplete():
        feedback = navigator.getFeedback()
        if feedback:
            navigator.get_logger().info(
                f'Distance remaining: {feedback.distance_remaining:.2f} m')

    # ── 4. Report result ───────────────────────────────────────────────
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
