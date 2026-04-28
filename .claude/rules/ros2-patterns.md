# ROS 2 Patterns & Coding Standards

## Naming Conventions

| Context | Convention | Ví dụ |
|---|---|---|
| Package name | `snake_case` | `agri_robot` |
| Node name | `snake_case` | `yolo_detector_node` |
| Topic name | `/snake_case` | `/detected_obstacles` |
| Service name | `/snake_case` | `/return_to_home` |
| Action name | `/snake_case` | `/navigate_to_pose` |
| Python files | `snake_case.py` | `obstacle_publisher.py` |
| Config files | `snake_case.yaml` | `nav2_params.yaml` |
| Launch files | `snake_case.launch.py` | `full_demo.launch.py` |
| Python classes | `PascalCase` | `YoloDetectorNode` |
| Python variables | `snake_case` | `home_position`, `obstacle_list` |
| ROS params | `snake_case` | `wheel_radius`, `update_rate` |
| URDF links | `snake_case_link` | `front_left_wheel_link` |
| URDF joints | `snake_case_joint` | `front_left_wheel_joint` |

## Python Node Pattern (ROS 2)

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

class YoloDetectorNode(Node):
    def __init__(self):
        super().__init__('yolo_detector_node')

        # Khai báo params
        self.declare_parameter('model_path', 'yolov8n.pt')
        self.declare_parameter('confidence_threshold', 0.5)

        # Lấy params
        model_path = self.get_parameter('model_path').value

        # Subscribers
        self.image_sub = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 10)

        # Publishers
        self.obstacle_pub = self.create_publisher(
            ..., '/detected_obstacles', 10)

        # Timer
        self.timer = self.create_timer(0.1, self.timer_callback)

        self.get_logger().info('YoloDetectorNode started')

    def image_callback(self, msg: Image):
        # Xử lý ảnh
        pass

    def timer_callback(self):
        # Logic định kỳ
        pass


def main(args=None):
    rclpy.init(args=args)
    node = YoloDetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
```

## Package Structure (agri_robot)

```
agri_robot/
├── package.xml             ← Dependencies khai báo ở đây
├── setup.py                ← Entry points cho ROS 2 nodes
├── setup.cfg
├── agri_robot/             ← Python package (cùng tên)
│   ├── __init__.py
│   ├── navigation/
│   │   ├── __init__.py
│   │   ├── return_home.py
│   │   └── waypoint_nav.py
│   ├── ai_vision/
│   │   ├── __init__.py
│   │   ├── yolo_detector.py
│   │   └── obstacle_publisher.py
│   └── motor_control/
│       ├── __init__.py
│       └── skid_steer_driver.py
├── urdf/
├── config/
├── launch/
├── worlds/
└── resource/
    └── agri_robot
```

## setup.py Entry Points

```python
entry_points={
    'console_scripts': [
        'yolo_detector = agri_robot.ai_vision.yolo_detector:main',
        'obstacle_publisher = agri_robot.ai_vision.obstacle_publisher:main',
        'return_home = agri_robot.navigation.return_home:main',
        'waypoint_nav = agri_robot.navigation.waypoint_nav:main',
    ],
},
```

## Launch File Pattern

```python
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_dir = get_package_share_directory('agri_robot')

    return LaunchDescription([
        Node(
            package='agri_robot',
            executable='yolo_detector',
            name='yolo_detector_node',
            parameters=[{
                'model_path': os.path.join(pkg_dir, 'models', 'yolov8n.pt'),
                'confidence_threshold': 0.5,
            }],
            output='screen',
        ),
    ])
```

## Build & Run

```bash
# Build package
cd ~/ros2_ws
colcon build --packages-select agri_robot
source install/setup.bash

# Run node
ros2 run agri_robot yolo_detector

# Launch
ros2 launch agri_robot full_demo.launch.py

# Check topics
ros2 topic list
ros2 topic echo /detected_obstacles

# Check nodes
ros2 node list
ros2 node info /yolo_detector_node
```

## Workspace Setup

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
# Symlink hoặc copy agri_robot package vào đây
ln -s /path/to/Agri_Robot_Simulation/agri_robot .
cd ~/ros2_ws
colcon build
source install/setup.bash
```

Thêm vào `~/.bashrc`:
```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=0
```
