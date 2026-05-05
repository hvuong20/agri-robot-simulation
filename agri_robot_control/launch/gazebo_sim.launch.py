"""
gazebo_sim.launch.py — One-command launch for full Gazebo simulation stack.

Starts in order:
  1. Gazebo + robot URDF           (agri_robot package)
  2. robot_localization EKF + navsat_transform  (agri_robot package)
  3. agri_robot_control bridge nodes (this package, after 5 s delay)

Requires:
  - ROS 2 Humble + Gazebo 11
  - agri_robot package built and sourced
  - Mosquitto broker on localhost:1883  (sudo apt install mosquitto && sudo systemctl start mosquitto)

Usage:
  ros2 launch agri_robot_control gazebo_sim.launch.py

After launch:
  - Open Flutter app, set MQTT host to <your_WSL_IP>:1883
  - Robot appears on the map at Gazebo GPS datum (10.45°N, 105.63°E)
  - Use app MQTT to set mode / draw boundary / start coverage

Topic flow:
  Flutter app
    ──MQTT──► mqtt_bridge_node ──► /app/command ──► mode_manager
                                ──► /app/boundary ──► boundary_manager
                                                        ──► coverage_planner
                                                              ──► /waypoints_goal
                                                                    ──► gps_navigator
                                                                          ──► /cmd_vel
                                                                                ──► Gazebo twist_mux
                                                                                      ──► /cmd_vel_mux
                                                                                            ──► motors
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    agri_robot_dir = get_package_share_directory('agri_robot')
    agri_ctrl_dir  = get_package_share_directory('agri_robot_control')

    # 1. Gazebo simulation + robot (Gazebo, RSP, twist_mux, robot spawn)
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(agri_robot_dir, 'launch', 'gazebo.launch.py')
        ),
    )

    # 2. Localization (EKF local + EKF global + navsat_transform)
    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(agri_robot_dir, 'launch', 'localization.launch.py')
        ),
    )

    # 3. Control bridge — delayed 5 s so Gazebo topics are available
    #    (Gazebo.launch already delays robot spawn 10 s; EKF warm-up ~5 s)
    bridge = TimerAction(
        period=5.0,
        actions=[
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(agri_ctrl_dir, 'launch', 'simulation_bridge.launch.py')
                ),
            ),
        ],
    )

    return LaunchDescription([gazebo, localization, bridge])
