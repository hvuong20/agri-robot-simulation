"""
hardware.launch.py — Launch RC interface + motor driver on Raspberry Pi 3.

Usage (on Pi):
    ros2 launch agri_robot_hardware hardware.launch.py

Optional overrides:
    ros2 launch agri_robot_hardware hardware.launch.py protocol:=ibus
    ros2 launch agri_robot_hardware hardware.launch.py motor_driver:=l298n

Nodes started:
  - rc_interface_node   : reads RC receiver, publishes /cmd_vel_teleop + mode/estop topics
  - motor_driver_node   : /cmd_vel_mux → GPIO PWM + ESTOP guardian + /odom

twist_mux is NOT started here — it lives in agri_robot_control/launch/full_system.launch.py
so the full navigation stack can be brought up separately.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('agri_robot_hardware')
    params_file = os.path.join(pkg_share, 'config', 'hardware_params.yaml')

    protocol_arg = DeclareLaunchArgument(
        'protocol',
        default_value='mock',
        description='RC protocol: mock | ibus | sbus | ppm',
    )
    motor_driver_arg = DeclareLaunchArgument(
        'motor_driver',
        default_value='mock',
        description='Motor driver: mock | l298n',
    )

    rc_node = Node(
        package='agri_robot_hardware',
        executable='rc_interface_node',
        name='rc_interface_node',
        output='screen',
        parameters=[
            params_file,
            {'rc.protocol': LaunchConfiguration('protocol')},
        ],
    )

    motor_node = Node(
        package='agri_robot_hardware',
        executable='motor_driver_node',
        name='motor_driver_node',
        output='screen',
        parameters=[
            params_file,
            {'motor.driver': LaunchConfiguration('motor_driver')},
        ],
    )

    return LaunchDescription([
        protocol_arg,
        motor_driver_arg,
        rc_node,
        motor_node,
    ])
