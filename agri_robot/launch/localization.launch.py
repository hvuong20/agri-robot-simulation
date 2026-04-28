import os

from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg_path = get_package_share_directory('agri_robot')

    ekf_local_config  = os.path.join(pkg_path, 'config', 'ekf_local.yaml')
    ekf_global_config = os.path.join(pkg_path, 'config', 'ekf_global.yaml')
    navsat_config     = os.path.join(pkg_path, 'config', 'navsat.yaml')

    return LaunchDescription([

        # ── 1. Local EKF ────────────────────────────────────────────────
        #    Fuses: /odom (wheel) + /imu/data
        #    Publishes: /odometry/filtered  (odom frame — relative)
        #    This gives stable short-term positioning without GPS noise.
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_filter_node',
            output='screen',
            parameters=[ekf_local_config, {'use_sim_time': True}],
            remappings=[('odometry/filtered', '/odometry/filtered')],
        ),

        # ── 2. NavSat Transform ──────────────────────────────────────────
        #    Converts: /gps/fix (lat/lon) → /odometry/gps (x/y in map)
        #    Needs /odometry/filtered from local EKF for heading reference.
        Node(
            package='robot_localization',
            executable='navsat_transform_node',
            name='navsat_transform',
            output='screen',
            parameters=[navsat_config, {'use_sim_time': True}],
            remappings=[
                ('imu/data',             '/imu/data'),
                ('gps/fix',              '/gps/fix'),
                ('odometry/filtered',    '/odometry/filtered'),
                ('odometry/gps',         '/odometry/gps'),
            ],
        ),

        # ── 3. Global EKF ────────────────────────────────────────────────
        #    Fuses: /odometry/filtered + /odometry/gps
        #    Publishes: /odometry/global  (map frame — GPS-anchored)
        #    Used by Nav2 for absolute positioning and return-to-home.
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_filter_node_map',
            output='screen',
            parameters=[ekf_global_config, {'use_sim_time': True}],
            remappings=[('odometry/filtered', '/odometry/global')],
        ),
    ])
