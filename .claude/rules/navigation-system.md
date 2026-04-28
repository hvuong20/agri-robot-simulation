# Navigation System

## Tổng quan

```
GPS (/gps/fix) ──────────────┐
                              ├──► robot_localization (EKF) ──► /odometry/global
IMU (/imu/data) ─────────────┘                                       │
                                                                      ▼
Wheel Odom (/odom) ─────────────────────────────────────► Nav2 Costmap & Planner
                                                                      │
                                                                      ▼
                                                          DWB Controller ──► /cmd_vel
```

## robot_localization (EKF)

File: `agri_robot/config/ekf.yaml`

```yaml
ekf_filter_node:
  ros__parameters:
    frequency: 30.0
    sensor_timeout: 0.1
    two_d_mode: true          # outdoor flat field → 2D mode
    publish_tf: true

    map_frame: map
    odom_frame: odom
    base_link_frame: base_link
    world_frame: odom

    # Fuse wheel odometry
    odom0: /odom
    odom0_config: [true,  true,  false,   # x, y, z
                   false, false, false,   # roll, pitch, yaw
                   true,  true,  false,   # vx, vy, vz
                   false, false, true,    # vroll, vpitch, vyaw
                   false, false, false]   # ax, ay, az

    # Fuse IMU
    imu0: /imu/data
    imu0_config: [false, false, false,
                  true,  true,  true,
                  false, false, false,
                  true,  true,  true,
                  true,  true,  false]
    imu0_remove_gravitational_acceleration: true
```

## navsat_transform_node

Chuyển GPS lat/lon → ROS x/y trong map frame.

File: `agri_robot/config/navsat.yaml`

```yaml
navsat_transform_node:
  ros__parameters:
    frequency: 10.0
    delay: 3.0                # chờ EKF ổn định
    magnetic_declination_radians: 0.0
    yaw_offset: 1.5707963     # camera nhìn về phía trước
    zero_altitude: true
    broadcast_utm_transform: false
    publish_filtered_gps: true
    use_odometry_yaw: false
    wait_for_datum: false

    # Topics
    # Input:  /gps/fix, /imu/data, /odometry/filtered
    # Output: /odometry/global (GPS-fused position)
```

## Return-to-Home

File: `agri_robot/scripts/navigation/return_home.py`

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix
from nav2_simple_commander.robot_navigator import BasicNavigator
from geometry_msgs.msg import PoseStamped
import math

class ReturnHomeNode(Node):
    def __init__(self):
        super().__init__('return_home_node')
        self.home_gps = None
        self.home_saved = False

        # Lưu GPS đầu tiên nhận được làm home position
        self.gps_sub = self.create_subscription(
            NavSatFix, '/gps/fix', self._save_home, 10)

    def _save_home(self, msg: NavSatFix):
        if not self.home_saved and msg.status.status >= 0:
            self.home_gps = (msg.latitude, msg.longitude)
            self.home_saved = True
            self.get_logger().info(
                f'Home saved: lat={msg.latitude:.6f}, lon={msg.longitude:.6f}')

    def go_home(self):
        if not self.home_saved:
            self.get_logger().error('Home position not saved yet!')
            return False

        nav = BasicNavigator()
        nav.waitUntilNav2Active()

        # Chuyển GPS home sang PoseStamped (qua /odometry/global)
        home_pose = self._gps_to_pose(self.home_gps)
        nav.goToPose(home_pose)

        while not nav.isTaskComplete():
            feedback = nav.getFeedback()
            dist = feedback.distance_remaining
            self.get_logger().info(f'Distance to home: {dist:.2f}m')

        result = nav.getResult()
        self.get_logger().info(f'Return home result: {result}')
        return True
```

## Nav2 Configuration

File: `agri_robot/config/nav2_params.yaml`

```yaml
bt_navigator:
  ros__parameters:
    global_frame: map
    robot_base_frame: base_link
    odom_topic: /odometry/global
    default_bt_xml_filename: "navigate_w_replanning_and_recovery.xml"

controller_server:
  ros__parameters:
    controller_frequency: 20.0
    controller_plugins: ["FollowPath"]
    FollowPath:
      plugin: "dwb_core::DWBLocalPlanner"
      min_vel_x: 0.0
      max_vel_x: 1.5        # tốc độ tối đa (m/s)
      max_vel_theta: 1.0    # tốc độ quay (rad/s)
      min_speed_xy: 0.0
      max_speed_xy: 1.5

planner_server:
  ros__parameters:
    planner_plugins: ["GridBased"]
    GridBased:
      plugin: "nav2_navfn_planner/NavfnPlanner"
      tolerance: 0.5
      use_astar: false

global_costmap:
  global_costmap:
    ros__parameters:
      update_frequency: 1.0
      publish_frequency: 1.0
      global_frame: map
      robot_base_frame: base_link
      robot_radius: 0.55    # nửa chiều rộng robot (m)
      plugins: ["static_layer", "obstacle_layer", "inflation_layer"]

local_costmap:
  local_costmap:
    ros__parameters:
      update_frequency: 5.0
      publish_frequency: 2.0
      global_frame: odom
      robot_base_frame: base_link
      rolling_window: true
      width: 5              # 5m x 5m local window
      height: 5
      resolution: 0.05
      robot_radius: 0.55
      plugins: ["obstacle_layer", "inflation_layer"]
```

## Waypoint Navigation

```python
from nav2_simple_commander.robot_navigator import BasicNavigator
from geometry_msgs.msg import PoseStamped
import rclpy

rclpy.init()
nav = BasicNavigator()
nav.waitUntilNav2Active()

# Tạo danh sách waypoints (trong map frame)
waypoints = []
for (x, y) in [(5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]:
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.w = 1.0
    waypoints.append(pose)

# Di chuyển qua tất cả waypoints
nav.followWaypoints(waypoints)
while not nav.isTaskComplete():
    pass

# Về home
nav.goToPose(home_pose)
```

## Trạng thái Nav2 (State Machine)

```
IDLE → NAVIGATING → GOAL_REACHED
            ↓
        OBSTACLE_DETECTED → REPLANNING → NAVIGATING
            ↓
        NAVIGATION_FAILED → RECOVERY → IDLE
```
