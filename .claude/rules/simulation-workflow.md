# Simulation Workflow

## Local Development Setup

```bash
# Workspace
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
ln -s /path/to/Agri_Robot_Simulation/agri_robot .

# Build
cd ~/ros2_ws
colcon build --packages-select agri_robot
source install/setup.bash
```

## Khởi động Simulation (từng bước)

```bash
# Terminal 1: Gazebo + Robot URDF
ros2 launch agri_robot gazebo.launch.py

# Terminal 2: Localization (EKF + navsat)
ros2 launch agri_robot localization.launch.py

# Terminal 3: Nav2
ros2 launch agri_robot navigation.launch.py

# Terminal 4: AI Obstacle Avoidance
ros2 run agri_robot yolo_detector &
ros2 run agri_robot obstacle_publisher

# Hoặc tất cả cùng lúc:
ros2 launch agri_robot full_demo.launch.py
```

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

# Gazebo: spawn model người để test
gz model --spawn-file=person.sdf --model-name=person1 -x 3 -y 0 -z 0
```

## Common Errors & Fixes

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `Could not find transform base_link → map` | TF chưa publish | Chờ localization khởi động, check `ros2 run tf2_tools view_frames` |
| Robot chìm xuống đất trong Gazebo | `<collision>` trong URDF sai | Kiểm tra mass, inertia values trong URDF |
| Nav2 stuck, không di chuyển | Costmap inflation radius quá lớn | Giảm `inflation_radius` trong nav2_params.yaml |
| YOLOv8 chạy chậm | CPU inference | Dùng `yolov8n.pt` hoặc enable GPU với CUDA |
| GPS fix status = -1 | Plugin chưa có signal | Tăng `update_rate`, check plugin config |

## File Edit Guide

| Muốn thay đổi | Sửa file này |
|---|---|
| Kích thước / hình dạng robot | `agri_robot/urdf/agri_robot.urdf.xacro` |
| Tốc độ bánh xe, wheelbase | `agri_robot/config/controllers.yaml` |
| EKF fusion weights | `agri_robot/config/ekf.yaml` |
| Tốc độ nav, vùng tránh | `agri_robot/config/nav2_params.yaml` |
| YOLO model, confidence | `agri_robot/scripts/ai_vision/yolo_detector.py` |
| Safety stop distance | `agri_robot/scripts/ai_vision/obstacle_publisher.py` |
| Gazebo world (địa hình, cây) | `agri_robot/worlds/farm_field.sdf` |
| Return-to-home logic | `agri_robot/scripts/navigation/return_home.py` |
