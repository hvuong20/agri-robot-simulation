# Simulation Workflow

## Windows + WSL2 Development Setup

```
┌─────────────────────────────────────────────┐
│              Windows 11                     │
│                                             │
│  VS Code ──Remote WSL──► WSL2 Ubuntu 22.04  │
│  Windows Terminal ──────► WSL2 Ubuntu 22.04  │
│                                             │
│  Gazebo GUI ◄── WSLg ── (tự động)           │
│  RViz2  GUI ◄── WSLg ── (tự động)           │
└─────────────────────────────────────────────┘
```

### Mở WSL2 terminal từ Windows

- **Cách 1:** Start Menu → tìm "Ubuntu 22.04" → mở
- **Cách 2:** Windows Terminal → dropdown → chọn "Ubuntu 22.04"
- **Cách 3:** VS Code → Terminal → New Terminal (sau khi connect Remote WSL)

### Workspace Setup (chạy trong WSL2)

```bash
# Tạo workspace
mkdir -p ~/agri_robot_ws/src
cd ~/agri_robot_ws/src

# Copy hoặc tạo package agri_robot ở đây (KHÔNG dùng /mnt/c/ — chậm)
# Nếu files đang ở Windows: copy vào WSL2
cp -r /mnt/c/Claude_project/Agri_Robot_Simulation/agri_robot ~/agri_robot_ws/src/

# Build
cd ~/agri_robot_ws
colcon build --packages-select agri_robot
source install/setup.bash

# Thêm vào ~/.bashrc
echo "source ~/agri_robot_ws/install/setup.bash" >> ~/.bashrc
```

### Mở project bằng VS Code (từ WSL2)

```bash
# Trong WSL2 terminal, gõ:
code ~/agri_robot_ws
# → VS Code tự mở trên Windows, kết nối vào WSL2
```

## Khởi động Simulation (từng bước — thứ tự bắt buộc)

```bash
# Terminal 1: Gazebo + Robot URDF
# Chờ: cửa sổ Gazebo mở + robot xanh xuất hiện (≈15 giây)
ros2 launch agri_robot gazebo.launch.py

# Terminal 2: Localization (EKF + navsat)
# Chờ: "[navsat_transform]: Datum (latitude, longitude...)"
ros2 launch agri_robot localization.launch.py

# Terminal 3: Nav2
# Chờ: "[lifecycle_manager_navigation]: Managed nodes are active"
ros2 launch agri_robot navigation.launch.py

# Terminal 4: Return home / AI
ros2 run agri_robot return_home
# Hoặc Phase 4:
# ros2 run agri_robot yolo_detector &
# ros2 run agri_robot obstacle_publisher

# Hoặc tất cả cùng lúc (Phase 5):
ros2 launch agri_robot full_demo.launch.py
```

> **Lưu ý:** Gazebo phải được start từ terminal có DISPLAY (WSL2 terminal với WSLg).
> Claude Code Bash tool không thể start Gazebo (không có DISPLAY). Nếu Gazebo crash,
> phải restart thủ công từ terminal Ubuntu.

## One-shot Launch: full_demo.launch.py

```python
# agri_robot/launch/full_demo.launch.py
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg = get_package_share_directory('agri_robot')
    return LaunchDescription([
        # 1. Gazebo world + robot
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'gazebo.launch.py'))),

        # 2. Localization (delay 3s để Gazebo ổn định)
        TimerAction(period=3.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(
                os.path.join(pkg, 'launch', 'localization.launch.py')))]),

        # 3. Nav2 (delay 5s)
        TimerAction(period=5.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(
                os.path.join(pkg, 'launch', 'navigation.launch.py')))]),

        # 4. AI nodes (delay 7s)
        TimerAction(period=7.0, actions=[
            IncludeLaunchDescription(PythonLaunchDescriptionSource(
                os.path.join(pkg, 'launch', 'ai_vision.launch.py')))]),
    ])
```

## Verification Checklist

### Phase 1 — Robot Model
- [ ] `ros2 launch agri_robot gazebo.launch.py` → robot xuất hiện, không bị fall qua mặt đất
- [ ] `ros2 topic list` → có `/odom`, `/joint_states`, `/cmd_vel`
- [ ] `ros2 run teleop_twist_keyboard teleop_twist_keyboard` → di chuyển được bằng phím
- [ ] `ros2 topic echo /odom` → có data liên tục khi di chuyển
- [ ] RViz2: thấy robot model, wheel joints đang quay

### Phase 2 — Localization
- [ ] `ros2 topic echo /gps/fix` → có `latitude`, `longitude` khác 0
- [ ] `ros2 topic echo /imu/data` → có angular_velocity, linear_acceleration
- [ ] `ros2 topic echo /odometry/global` → có x/y thay đổi khi robot di chuyển
- [ ] RViz2: `Fixed Frame = map`, robot position nhảy về GPS-based coordinate

### Phase 3 — Navigation
- [ ] Nav2 stack khởi động không lỗi
- [ ] RViz2: gửi **2D Nav Goal** → robot tự di chuyển đến đích
- [ ] `ros2 run agri_robot return_home` → robot về vị trí ban đầu
- [ ] Test replanning: đặt vật cản tĩnh trên đường → robot tự vòng qua

### Phase 4 — AI Obstacle Avoidance
- [ ] `ros2 topic echo /detected_objects` → có detection khi camera thấy người
- [ ] Spawn model người trong Gazebo trước mặt robot → robot phải dừng hoặc tránh
- [ ] `ros2 topic echo /detected_obstacle_points` → có PointCloud2 data
- [ ] Nav2 costmap: thấy obstacle được mark trong local costmap (RViz2)

### Phase 5 — Full Integration
- [ ] Full demo launch chạy không lỗi
- [ ] Scenario A→B→Home: robot đi đến điểm A, rồi B, rồi tự về home
- [ ] Scenario obstacle: robot đang đi thì có người bước vào → dừng → tránh → tiếp tục
- [ ] GPS loss: tắt GPS plugin → robot hành xử đúng (dừng, không bay lung tung)

## Debug Commands

```bash
# Xem tất cả topics
ros2 topic list

# Xem tần số publish của topic
ros2 topic hz /camera/image_raw

# Kiểm tra TF tree (quan trọng cho localization)
ros2 run tf2_tools view_frames

# Xem log của node
ros2 node list
ros2 node info /yolo_detector_node

# Xem params
ros2 param list /ekf_filter_node
ros2 param get /ekf_filter_node frequency

# Gazebo Classic: spawn model người để test (dùng rosservice, không phải gz CLI)
ros2 service call /spawn_entity gazebo_msgs/srv/SpawnEntity \
  '{name: "person1", xml: "$(cat person.sdf)", initial_pose: {position: {x: 3, y: 0, z: 0}}}'
```

## Common Errors & Fixes

### WSL2-specific

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| Gazebo không mở cửa sổ GUI | WSLg chưa kích hoạt | Đảm bảo Windows 11 + WSL2 đã update (`wsl --update`) |
| `LIBGL_ERROR: No matching fbConfigs` | GPU driver WSL2 chưa cài | Cài WSL2 GPU driver từ trang NVIDIA/AMD/Intel |
| Build rất chậm trong `/mnt/c/` | Windows filesystem I/O bottleneck | Chuyển code vào `~/` (WSL2 filesystem) |
| `ros2: command not found` sau khi mở terminal mới | Chưa source setup | Thêm `source /opt/ros/humble/setup.bash` vào `~/.bashrc` |
| Gazebo mở nhưng rất lag | Không dùng GPU acceleration | Cài driver GPU WSL2, kiểm tra `glxinfo | grep renderer` |

### ROS 2 Setup Errors (Common)

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `curl ros.key → 404 Not Found` | URL `ros.key` đã bị xóa từ 2024 | Dùng `wget -qO- .../ros.asc \| sudo gpg --dearmor -o ...` |
| `E: Unable to locate package ros-humble-desktop` | Repository chưa thêm vào sources | Verify với `cat /etc/apt/sources.list.d/ros2.list`, sau đó `sudo apt update` |
| `ros2: error: unrecognized arguments: --version` | ROS 2 không có flag `--version` | Dùng `echo $ROS_DISTRO` hoặc `ros2 pkg list` để verify |
| `gz sim --version → invalid argument` | Máy cài Gazebo Classic 11, không phải Harmonic | Dùng `gazebo --version`. Classic dùng `gazebo` command, không phải `gz sim` |
| `Package 'turtlebot3_gazebo' not found` | Package chưa được cài | `sudo apt install -y ros-humble-turtlebot3-gazebo` |
| Robot spawn nhưng không di chuyển khi bấm teleop | Terminal teleop chưa có focus | Click trực tiếp vào terminal đang chạy teleop, rồi mới bấm phím |
| Robot không spawn (topic `/odom` không xuất hiện) | `TURTLEBOT3_MODEL` chưa được set | `export TURTLEBOT3_MODEL=burger` rồi restart launch |
| Robot không di chuyển dù teleop đang gửi | Gazebo đang bị Pause | Nhấn nút ▶ Play ở thanh dưới cửa sổ Gazebo |

### ROS 2 / Gazebo chung

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `Could not find transform base_link → map` | Localization chưa chạy hoặc crash | Khởi động / restart `localization.launch.py`, check `ros2 run tf2_tools view_frames` |
| Robot chìm xuống đất trong Gazebo | `<collision>` trong URDF sai | Kiểm tra mass, inertia values trong URDF |
| Nav2 stuck, không di chuyển | Costmap inflation radius quá lớn | Giảm `inflation_radius` trong nav2_params.yaml |
| YOLOv8 chạy chậm | CPU inference | Dùng `yolov8n.pt` hoặc enable GPU với CUDA |
| GPS fix status = -1 | Plugin chưa có signal | Tăng `update_rate`, check plugin config |

### Nav2 / BT XML Errors

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `Cannot open: libnav2_path_expiring_timer_condition_bt_node.so` | Plugin không tồn tại trong bản cài | Xóa khỏi `plugin_lib_names` trong nav2_params.yaml |
| `Node not recognized: RemovePassedGoals` | Default BT XML dùng node không có trong build này | Tạo custom BT XML, set đường dẫn tuyệt đối trong nav2_params.yaml |
| `Error loading XML: navigate_through_poses_w_replanning...` | bt_navigator load 2 BT XML — cái through_poses cũng bị lỗi | Tạo custom `navigate_through_poses_bt.xml` và set `default_nav_through_poses_bt_xml` |
| BT XML custom không được load (vẫn dùng default) | nav2_bringup Humble không forward `default_nav_to_pose_bt_xml` launch arg | Set path trực tiếp trong `bt_navigator.ros__parameters` trong yaml |
| `Behavior tree threw exception: Empty Tree` | `default_nav_to_pose_bt_xml: ""` trong yaml | Xóa dòng đó hoặc set path đầy đủ |
| `Waiting for amcl/get_state...` vòng lặp vô hạn | `waitUntilNav2Active()` chờ AMCL (GPS setup không có AMCL) | Dùng `ActionClient.wait_for_server()` trực tiếp thay thế |
| `odometry/global` không có data — bị treo | navsat_transform chờ IMU heading (robot đứng yên) | Set `use_odometry_yaw: true` trong navsat.yaml |
| `Robot is out of bounds of the costmap` | Robot chưa có vị trí trong costmap (localization chưa lên) | Chờ localization ổn định trước khi start Nav2 |

## File Edit Guide

| Muốn thay đổi | Sửa file này |
|---|---|
| Kích thước / hình dạng robot | `agri_robot/urdf/agri_robot.urdf.xacro` |
| Tốc độ bánh xe, wheel separation | `agri_robot/urdf/agri_robot.urdf.xacro` (diff_drive plugin) |
| EKF fusion weights (local) | `agri_robot/config/ekf_local.yaml` |
| EKF fusion weights (global) | `agri_robot/config/ekf_global.yaml` |
| GPS transform config | `agri_robot/config/navsat.yaml` |
| Tốc độ nav, vùng tránh | `agri_robot/config/nav2_params.yaml` |
| Behavior Tree (Nav2) | `agri_robot/config/navigate_to_pose_bt.xml` |
| Return-to-home logic | `agri_robot/agri_robot/navigation/return_home.py` |
| YOLO model, confidence | `agri_robot/agri_robot/ai_vision/yolo_detector.py` (Phase 4) |
| Safety stop distance | `agri_robot/agri_robot/ai_vision/obstacle_publisher.py` (Phase 4) |
| Gazebo world (địa hình, cây) | `agri_robot/worlds/empty_field.sdf` |
