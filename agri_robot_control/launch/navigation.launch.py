"""
navigation.launch.py — Navigation and control logic nodes.

Starts:
  - twist_mux: /cmd_vel_teleop (p=20) + /cmd_vel_auto (p=5) → /cmd_vel_mux
  - mode_manager_node
  - boundary_manager_node
  - coverage_planner_node
  - gps_navigator_node
  - follow_mode_node
  - mqtt_bridge_node
  - stuck_detector_node
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg         = get_package_share_directory('agri_robot_control')
    ctrl_cfg    = os.path.join(pkg, 'config', 'control_params.yaml')
    mqtt_cfg    = os.path.join(pkg, 'config', 'mqtt_config.yaml')
    twistmux_cfg = os.path.join(pkg, 'config', 'twist_mux.yaml')

    twist_mux = Node(
        package='twist_mux',
        executable='twist_mux',
        name='twist_mux',
        output='screen',
        parameters=[twistmux_cfg],
        remappings=[('cmd_vel_out', '/cmd_vel_mux')],
    )

    mode_manager = Node(
        package='agri_robot_control',
        executable='mode_manager_node',
        name='mode_manager_node',
        output='screen',
        parameters=[ctrl_cfg],
    )

    boundary_manager = Node(
        package='agri_robot_control',
        executable='boundary_manager_node',
        name='boundary_manager_node',
        output='screen',
        parameters=[ctrl_cfg],
    )

    coverage_planner = Node(
        package='agri_robot_control',
        executable='coverage_planner_node',
        name='coverage_planner_node',
        output='screen',
        parameters=[ctrl_cfg],
    )

    gps_navigator = Node(
        package='agri_robot_control',
        executable='gps_navigator_node',
        name='gps_navigator_node',
        output='screen',
        parameters=[ctrl_cfg],
    )

    follow_mode = Node(
        package='agri_robot_control',
        executable='follow_mode_node',
        name='follow_mode_node',
        output='screen',
        parameters=[ctrl_cfg],
    )

    mqtt_bridge = Node(
        package='agri_robot_control',
        executable='mqtt_bridge_node',
        name='mqtt_bridge_node',
        output='screen',
        parameters=[ctrl_cfg, mqtt_cfg],
    )

    stuck_detector = Node(
        package='agri_robot_control',
        executable='stuck_detector_node',
        name='stuck_detector_node',
        output='screen',
        parameters=[ctrl_cfg],
    )

    return LaunchDescription([
        twist_mux,
        mode_manager,
        boundary_manager,
        coverage_planner,
        gps_navigator,
        follow_mode,
        mqtt_bridge,
        stuck_detector,
    ])
