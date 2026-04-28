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
        # Local EKF output → /odometry/local (unambiguous name)
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_filter_node',
            output='screen',
            parameters=[ekf_local_config, {'use_sim_time': True}],
            remappings=[('odometry/filtered', '/odometry/local')],
        ),

        # ── 2. NavSat Transform ──────────────────────────────────────────
        Node(
            package='robot_localization',
            executable='navsat_transform_node',
            name='navsat_transform',
            output='screen',
            parameters=[navsat_config, {'use_sim_time': True}],
            remappings=[
                ('imu/data',          '/imu/data'),
                ('gps/fix',           '/gps/fix'),
                ('odometry/filtered', '/odometry/local'),
                ('odometry/gps',      '/odometry/gps'),
            ],
        ),

        # ── 3. Global EKF ────────────────────────────────────────────────
        #    INPUT:  /odometry/local (local EKF) + /odometry/gps (navsat)
        #    OUTPUT: /odometry/global (map frame, GPS-anchored)
        #    The remapping here only affects the OUTPUT (odometry/filtered
        #    → /odometry/global). Input odom0=/odometry/local is different
        #    so no circular subscription.
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_filter_node_map',
            output='screen',
            parameters=[ekf_global_config, {'use_sim_time': True}],
            remappings=[('odometry/filtered', '/odometry/global')],
        ),
    ])
