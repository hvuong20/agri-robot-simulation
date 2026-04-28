import os

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg_path     = get_package_share_directory('agri_robot')
    nav2_bringup = get_package_share_directory('nav2_bringup')

    nav2_params_path = os.path.join(pkg_path, 'config', 'nav2_params.yaml')
    bt_xml_path      = os.path.join(pkg_path, 'config', 'navigate_to_pose_bt.xml')

    return LaunchDescription([

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup, 'launch', 'navigation_launch.py')
            ),
            launch_arguments={
                'use_sim_time': 'true',
                'params_file': nav2_params_path,
                'default_nav_to_pose_bt_xml': bt_xml_path,
            }.items(),
        ),
    ])
