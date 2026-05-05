"""
simulation_bridge.launch.py — Connect agri_robot_control nodes to Gazebo simulation.

Launches ONLY the control-logic nodes.  Gazebo already provides:
  - twist_mux          (/cmd_vel + /cmd_vel_teleop → /cmd_vel_mux)
  - localization        (/gps/fix, /odom, /odometry/global, /odometry/local)
  - robot physics

Topic remappings vs real-hardware navigation.launch.py:
  gps_navigator  /cmd_vel_auto → /cmd_vel   (Gazebo twist_mux input, priority 1)
  follow_mode    /cmd_vel_auto → /cmd_vel

RC input (/rc/mode_switch, /rc/boundary_btn) is silent in simulation;
mode changes happen via MQTT from the Flutter app.

ESTOP flow in simulation:
  App ESTOP button → MQTT app/estop → mqtt_bridge → /estop_trigger
    → mode_manager sets mode=ESTOP → gps_navigator/follow_mode stop publishing
    → /cmd_vel times out (0.5 s) → Gazebo robot stops

  App long-press ESTOP → MQTT estop_clear → mode_manager clears to MANUAL

Usage (requires Mosquitto on localhost:1883):
  ros2 launch agri_robot_control simulation_bridge.launch.py
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg      = get_package_share_directory('agri_robot_control')
    ctrl_cfg = os.path.join(pkg, 'config', 'control_params.yaml')
    mqtt_cfg = os.path.join(pkg, 'config', 'mqtt_config.yaml')
    sim_p    = {'use_sim_time': True}

    return LaunchDescription([

        # ── Mode state machine ────────────────────────────────────────────────
        # RC topics are silent in sim; mode is controlled purely via MQTT.
        Node(
            package='agri_robot_control',
            executable='mode_manager_node',
            name='mode_manager_node',
            output='screen',
            parameters=[ctrl_cfg, sim_p],
        ),

        # ── Boundary manager ──────────────────────────────────────────────────
        # Receives boundary polygon from Flutter app via MQTT app/boundary.
        # RC CH7 boundary-record button is silent in sim.
        Node(
            package='agri_robot_control',
            executable='boundary_manager_node',
            name='boundary_manager_node',
            output='screen',
            parameters=[ctrl_cfg, sim_p],
        ),

        # ── Coverage planner ──────────────────────────────────────────────────
        # Listens to /boundary_polygon → generates boustrophedon path.
        # Publishes /coverage_waypoints (display) + /waypoints_goal (navigator).
        # On mode→AUTO: resends waypoints to /waypoints_goal.
        Node(
            package='agri_robot_control',
            executable='coverage_planner_node',
            name='coverage_planner_node',
            output='screen',
            parameters=[ctrl_cfg, sim_p],
        ),

        # ── GPS navigator (AUTO mode) ─────────────────────────────────────────
        # Remap /cmd_vel_auto → /cmd_vel so it enters Gazebo's twist_mux
        # at priority 1.  Only active when /current_mode == "AUTO".
        Node(
            package='agri_robot_control',
            executable='gps_navigator_node',
            name='gps_navigator_node',
            output='screen',
            parameters=[ctrl_cfg, sim_p],
            remappings=[('/cmd_vel_auto', '/cmd_vel')],
        ),

        # ── Follow mode (FOLLOW mode) ─────────────────────────────────────────
        # Receives phone GPS from MQTT app/follow_position.
        # Same /cmd_vel remap — only one of gps_navigator / follow_mode
        # publishes at a time (guarded by /current_mode).
        Node(
            package='agri_robot_control',
            executable='follow_mode_node',
            name='follow_mode_node',
            output='screen',
            parameters=[ctrl_cfg, sim_p],
            remappings=[('/cmd_vel_auto', '/cmd_vel')],
        ),

        # ── MQTT bridge ───────────────────────────────────────────────────────
        # Requires Mosquitto broker at localhost:1883 (or mqtt_config.yaml host).
        # Bidirectional: Flutter app ↔ ROS 2 topics.
        Node(
            package='agri_robot_control',
            executable='mqtt_bridge_node',
            name='mqtt_bridge_node',
            output='screen',
            parameters=[ctrl_cfg, mqtt_cfg, sim_p],
        ),

        # ── Stuck detector ────────────────────────────────────────────────────
        # Monitors /cmd_vel_mux (Gazebo twist_mux output) vs /odom velocity.
        # Publishes /stuck_alert → mqtt_bridge forwards to Flutter app.
        Node(
            package='agri_robot_control',
            executable='stuck_detector_node',
            name='stuck_detector_node',
            output='screen',
            parameters=[ctrl_cfg, sim_p],
        ),
    ])
