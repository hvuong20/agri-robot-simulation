# Navigation System

## Sơ đồ tổng quát

```
GPS (/gps/fix) ──────────────┐
                              ├──► navsat_transform ──► /odometry/gps
IMU (/imu/data) ─────────────┘         │
                                       │
Wheel Odom (/odom)                     │
   + IMU (/imu/data)                   │
      └──► local EKF ──► /odometry/local ──────────┐
                                                    ├──► global EKF ──► /odometry/global
                               /odometry/gps ───────┘                        │
                                                                              ▼
                                                                    Nav2 (odom_topic)
                                                                              │
                                                                    DWB Controller ──► /cmd_vel
```

## Localization — Dual EKF Setup

### Local EKF (`ekf_local.yaml`)
- **Input:** `/odom` (wheel odometry) + `/imu/data`
- **Output:** `/odometry/local` (odom frame — stable short-term)
- **Output frame:** `odom`

```yaml
frequency: 30.0
two_d_mode: true
world_frame: odom   # local EKF works in odom frame

odom0: /odom
odom0_config: [true, true, false, false, false, true, true, false, false, false, false, true, false, false, false]

imu0: /imu/data
imu0_config: [false, false, false, true, true, true, false, false, false, true, true, true, true, true, false]
imu0_remove_gravitational_acceleration: true
```

### navsat_transform (`navsat.yaml`)
- **Input:** `/gps/fix` + `/imu/data` + `/odometry/local`
- **Output:** `/odometry/gps`

```yaml
frequency: 10.0
delay: 1.0                    # giảm từ 3.0 — kết hợp use_odometry_yaw
magnetic_declination_radians: 0.0
yaw_offset: 0.0
zero_altitude: true
use_odometry_yaw: true        # QUAN TRỌNG: dùng yaw từ odometry, không từ IMU riêng
                              # Tránh deadlock khi robot đứng yên (không có GPS heading)
wait_for_datum: false
```

### Global EKF (`ekf_global.yaml`)
- **Input:** `/odometry/local` + `/odometry/gps`
- **Output:** `/odometry/global` (map frame — GPS-anchored)
- **Output frame:** `map`

```yaml
world_frame: map    # global EKF works in map frame

odom0: /odometry/local
odom0_config: [true, true, false, false, false, true, true, false, false, false, false, true, false, false, false]

odom1: /odometry/gps
odom1_config: [true, true, false, false, false, false, false, false, false, false, false, false, false, false, false]
```

> **Tại sao `/odometry/local` chứ không phải `/odometry/filtered`?**
> Nếu đặt tên là `/odometry/filtered`, global EKF (output remapped to `/odometry/global`)
> vẫn lắng nghe `/odometry/filtered` như input → **circular subscription** — global EKF
> feed kết quả của mình vào chính nó. Đặt tên khác phá vỡ vòng lặp này.

### localization.launch.py — cấu trúc
```python
Node(ekf_node, name='ekf_filter_node',           # local EKF
     remappings=[('odometry/filtered', '/odometry/local')]),

Node(navsat_transform_node,
     remappings=[
         ('odometry/filtered', '/odometry/local'),  # input
         ('odometry/gps', '/odometry/gps'),          # output
     ]),

Node(ekf_node, name='ekf_filter_node_map',        # global EKF
     remappings=[('odometry/filtered', '/odometry/global')]),
```
Tất cả nodes đều cần `parameters=[config_file, {'use_sim_time': True}]`.

---

## Return-to-Home (`agri_robot/agri_robot/navigation/return_home.py`)

**Logic:**
1. Subscribe `/odometry/global` — lưu message đầu tiên làm "home pose"
2. Chờ `navigate_to_pose` action server sẵn sàng (KHÔNG dùng `waitUntilNav2Active()`)
3. Gửi PoseStamped về home qua `navigator.goToPose()`
4. In distance remaining mỗi vòng lặp

**Quan trọng — tại sao không dùng `waitUntilNav2Active()`:**
```python
# ❌ Sai — gây loop chờ AMCL mãi mãi (GPS setup không có AMCL)
navigator.waitUntilNav2Active()

# ✅ Đúng — chờ trực tiếp action server
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
_ac = ActionClient(navigator, NavigateToPose, 'navigate_to_pose')
while not _ac.wait_for_server(timeout_sec=1.0):
    navigator.get_logger().info('navigate_to_pose not ready, waiting...')
```

**Chạy:**
```bash
ros2 run agri_robot return_home
```

---

## Nav2 Configuration (`agri_robot/config/nav2_params.yaml`)

**Design:**
- Không có `map_server` / `static_layer` (GPS-based, đồng trống)
- `global_costmap`: rolling 50×50m, `track_unknown_space: false` (unknown = free)
- `local_costmap`: rolling 10×10m, chỉ có `inflation_layer`
- `odom_topic: /odometry/global` (GPS-corrected absolute position)

**Key values:**
```yaml
bt_navigator:
  default_nav_to_pose_bt_xml: "/home/hvuong20/agri_robot_ws/install/agri_robot/share/agri_robot/config/navigate_to_pose_bt.xml"
  default_nav_through_poses_bt_xml: "/home/hvuong20/agri_robot_ws/install/agri_robot/share/agri_robot/config/navigate_through_poses_bt.xml"

controller_server (DWB):
  max_vel_x: 1.5 m/s
  max_vel_theta: 1.0 rad/s
  xy_goal_tolerance: 0.50 m

global_costmap:
  rolling_window: true, 50×50m, resolution 0.10m
  robot_radius: 0.50m

local_costmap:
  rolling_window: true, 10×10m, resolution 0.05m
```

### Custom BT XML — tại sao cần

nav2_bringup trong Humble **không forward** `default_nav_to_pose_bt_xml` launch argument.
bt_navigator chỉ đọc từ `configured_params` (params_file). Do đó phải set đường dẫn
tuyệt đối trực tiếp trong `nav2_params.yaml`.

bt_navigator load **2 BT XML** khi khởi động:
- `default_nav_to_pose_bt_xml` → cho `NavigateToPose` action
- `default_nav_through_poses_bt_xml` → cho `NavigateThroughPoses` action

Default XML của Nav2 dùng node `RemovePassedGoals` không có trong build này → phải custom cả 2.

**Custom BT (navigate_to_pose_bt.xml) — chỉ dùng nodes có sẵn:**
- `RecoveryNode`, `PipelineSequence`, `RateController`
- `ComputePathToPose`, `FollowPath`
- `ReactiveFallback`, `GoalUpdated`, `RoundRobin`
- `ClearEntireCostmap`, `Spin`, `Wait`, `BackUp`

---

## Khởi động stack (thứ tự bắt buộc)

```bash
# Terminal 1
ros2 launch agri_robot gazebo.launch.py
# → Chờ robot xuất hiện trong Gazebo (≈15 giây)

# Terminal 2
ros2 launch agri_robot localization.launch.py
# → Chờ: [navsat_transform]: Datum (latitude, longitude...)

# Terminal 3
ros2 launch agri_robot navigation.launch.py
# → Chờ: [lifecycle_manager_navigation]: Managed nodes are active

# Terminal 4
ros2 run agri_robot return_home
```

## Debug Localization

```bash
# Kiểm tra /odometry/global có data không
ros2 topic echo /odometry/global --once

# Kiểm tra TF map→base_link
ros2 run tf2_ros tf2_echo map base_link

# Kiểm tra TF tree
ros2 run tf2_tools view_frames

# Xem tất cả topics localization
ros2 topic list | grep odometry
```

## Waypoint Navigation (tương lai — Phase 5)

```python
from nav2_simple_commander.robot_navigator import BasicNavigator
from geometry_msgs.msg import PoseStamped
import rclpy

rclpy.init()
nav = BasicNavigator()

# Chờ action server (KHÔNG dùng waitUntilNav2Active)
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
_ac = ActionClient(nav, NavigateToPose, 'navigate_to_pose')
while not _ac.wait_for_server(timeout_sec=1.0):
    pass

waypoints = []
for (x, y) in [(5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]:
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.orientation.w = 1.0
    waypoints.append(pose)

nav.followWaypoints(waypoints)
while not nav.isTaskComplete():
    pass
```
