import os
import subprocess

from launch import LaunchDescription
from launch.actions import ExecuteProcess
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

    return LaunchDescription([

        # ── 1. Start Gazebo Classic with the farm world ──────────────
        #    -s loads two ROS plugins:
        #       libgazebo_ros_init.so     → ROS 2 node inside Gazebo
        #       libgazebo_ros_factory.so  → enables spawn_entity
        ExecuteProcess(
            cmd=[
                'gazebo', '--verbose', world_path,
                '-s', 'libgazebo_ros_init.so',
                '-s', 'libgazebo_ros_factory.so',
            ],
            output='screen',
        ),

        # ── 2. Robot State Publisher ─────────────────────────────────
        #    Reads robot_description and publishes TF transforms for
        #    all links (base_link → wheels, camera, imu, gps, …).
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
        ),

        # ── 3. Spawn robot into Gazebo ───────────────────────────────
        #    Reads URDF from /robot_description topic and spawns the
        #    robot entity at position (0, 0, 0.15).
        #    z=0.15 = chassis_z so wheels land exactly on the ground.
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
    ])
