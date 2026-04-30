"""
full_system.launch.py — Complete robot bringup for Raspberry Pi 3.

Launches in order:
  1. hardware.launch.py  (RC + motors — from agri_robot_hardware)
  2. localization.launch.py  (GPS + EKF)
  3. navigation.launch.py    (twist_mux + all control nodes + MQTT)

Usage:
    ros2 launch agri_robot_control full_system.launch.py

Optional overrides:
    ros2 launch agri_robot_control full_system.launch.py protocol:=ibus motor_driver:=l298n
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    hw_pkg   = get_package_share_directory('agri_robot_hardware')
    ctrl_pkg = get_package_share_directory('agri_robot_control')

    protocol_arg = DeclareLaunchArgument(
        'protocol',
        default_value='mock',
        description='RC protocol: mock | ibus | sbus | ppm',
    )
    motor_arg = DeclareLaunchArgument(
        'motor_driver',
        default_value='mock',
        description='Motor driver: mock | l298n',
    )
    gps_port_arg = DeclareLaunchArgument(
        'gps_port',
        default_value='/dev/ttyACM0',
        description='Serial port for GPS',
    )

    hardware = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(hw_pkg, 'launch', 'hardware.launch.py')
        ),
        launch_arguments={
            'protocol':     LaunchConfiguration('protocol'),
            'motor_driver': LaunchConfiguration('motor_driver'),
        }.items(),
    )

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ctrl_pkg, 'launch', 'localization.launch.py')
        ),
        launch_arguments={
            'gps_port': LaunchConfiguration('gps_port'),
        }.items(),
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ctrl_pkg, 'launch', 'navigation.launch.py')
        ),
    )

    return LaunchDescription([
        protocol_arg,
        motor_arg,
        gps_port_arg,
        hardware,
        localization,
        navigation,
    ])
