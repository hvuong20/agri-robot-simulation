import os
import subprocess

from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg_path = get_package_share_directory('agri_robot')

    world_path = os.path.join(pkg_path, 'worlds', 'empty_field.sdf')
    urdf_path  = os.path.join(pkg_path, 'urdf',   'agri_robot.urdf.xacro')

    # Process xacro → URDF string at launch time
    robot_description = subprocess.check_output(
        ['xacro', urdf_path],
        stderr=subprocess.DEVNULL
    ).decode('utf-8')

    gazebo = ExecuteProcess(
        cmd=[
            'gazebo', '--verbose', world_path,
            '-s', 'libgazebo_ros_init.so',
            '-s', 'libgazebo_ros_factory.so',
        ],
        output='screen',
    )

    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
    )

    # Delay spawn by 10s — Gazebo needs time to load world + ROS plugins
    # before spawn_entity can call /spawn_entity service successfully.
    spawn = TimerAction(
        period=10.0,
        actions=[
            Node(
                package='gazebo_ros',
                executable='spawn_entity.py',
                name='spawn_entity',
                output='screen',
                arguments=[
                    '-topic', 'robot_description',
                    '-entity', 'agri_robot',
                    '-x', '0.0',
                    '-y', '0.0',
                    '-z', '0.15',
                    '-R', '0.0',
                    '-P', '0.0',
                    '-Y', '0.0',
                ],
            ),
        ],
    )

    return LaunchDescription([gazebo, rsp, spawn])
