"""
localization.launch.py — EKF localization stack for real hardware.

Starts:
  - robot_localization ekf_node (local): /odom + /imu/data → /odometry/local
  - robot_localization ekf_node (global): /odometry/local + /gps/fix → /odometry/global
  - navsat_transform_node: GPS → /odometry/gps (feeds global EKF)
  - nmea_navsat_driver: reads GPS UART and publishes /gps/fix

NOTE: use_sim_time is explicitly False — this is for real hardware, not Gazebo.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('agri_robot_control')
    ekf_local_cfg  = os.path.join(pkg, 'config', 'ekf_local.yaml')
    ekf_global_cfg = os.path.join(pkg, 'config', 'ekf_global.yaml')
    navsat_cfg     = os.path.join(pkg, 'config', 'navsat.yaml')

    gps_port_arg = DeclareLaunchArgument(
        'gps_port',
        default_value='/dev/ttyACM0',
        description='Serial port for GPS NMEA sentences',
    )
    gps_baud_arg = DeclareLaunchArgument(
        'gps_baud',
        default_value='9600',
        description='GPS serial baud rate',
    )

    ekf_local = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node_odom',
        output='screen',
        parameters=[ekf_local_cfg, {'use_sim_time': False}],
        remappings=[('odometry/filtered', 'odometry/local')],
    )

    ekf_global = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node_map',
        output='screen',
        parameters=[ekf_global_cfg, {'use_sim_time': False}],
        remappings=[('odometry/filtered', 'odometry/global')],
    )

    navsat = Node(
        package='robot_localization',
        executable='navsat_transform_node',
        name='navsat_transform_node',
        output='screen',
        parameters=[navsat_cfg, {'use_sim_time': False}],
        remappings=[
            ('imu', '/imu/data'),
            ('gps/fix', '/gps/fix'),
            ('odometry/filtered', '/odometry/local'),
        ],
    )

    gps_driver = Node(
        package='nmea_navsat_driver',
        executable='nmea_serial_driver',
        name='nmea_serial_driver',
        output='screen',
        parameters=[{
            'port':     LaunchConfiguration('gps_port'),
            'baud':     LaunchConfiguration('gps_baud'),
            'frame_id': 'gps_link',
        }],
        remappings=[('fix', '/gps/fix')],
    )

    return LaunchDescription([
        gps_port_arg,
        gps_baud_arg,
        gps_driver,
        ekf_local,
        navsat,
        ekf_global,
    ])
