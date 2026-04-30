from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='agri_robot',
            executable='yolo_obstacle_node',
            name='yolo_obstacle_node',
            output='screen',
            parameters=[{'use_sim_time': True}],
        ),
    ])
