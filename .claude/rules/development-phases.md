# Development Phases

## Tổng quan

| Phase | Nội dung | Thời gian | Trạng thái |
|---|---|---|---|
| 0 | Cài đặt môi trường | 1–2 ngày | ⬜ Chưa bắt đầu |
| 1 | Mô hình Robot (URDF) + Gazebo | 3–5 ngày | ⬜ Chưa bắt đầu |
| 2 | Localization (GPS + IMU → EKF) | 3–4 ngày | ⬜ Chưa bắt đầu |
| 3 | Nav2 Path Planning + Return-to-Home | 3–4 ngày | ⬜ Chưa bắt đầu |
| 4 | AI Obstacle Avoidance (YOLOv8) | 5–7 ngày | ⬜ Chưa bắt đầu |
| 5 | Farm World + Integration Testing | 2–3 ngày | ⬜ Chưa bắt đầu |

---

## Phase 0 — Cài đặt môi trường (Windows + WSL2)

### Bước 0a — Cài WSL2 (chạy trong PowerShell với quyền Admin)

```powershell
# Mở PowerShell as Administrator, chạy:
wsl --install -d Ubuntu-22.04

# Khởi động lại máy khi được yêu cầu
# Sau đó mở "Ubuntu 22.04" từ Start Menu → tạo username + password
```

> **Windows 11** đã có WSLg tích hợp sẵn — Gazebo và RViz2 hiển thị cửa sổ GUI tự động, không cần cài thêm X server.

### Bước 0b — Cài VS Code + Remote WSL (trên Windows)

```
1. Tải VS Code: code.visualstudio.com
2. Mở VS Code → Extensions → tìm "WSL" → cài "Remote - WSL" (Microsoft)
3. Nhấn F1 → "WSL: Connect to WSL" → VS Code kết nối vào Ubuntu
4. Mọi terminal trong VS Code giờ chạy trong WSL2
```

### Bước 0c — Cài ROS 2 + Tools (chạy trong WSL2 Ubuntu terminal)

```bash
# Thêm ROS 2 apt repo
sudo apt update && sudo apt install -y curl gnupg lsb-release
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Cài ROS 2 Humble Desktop
sudo apt update && sudo apt install -y ros-humble-desktop

# Cài Gazebo Harmonic + ROS bridge
sudo apt install -y ros-humble-ros-gz

# Cài Nav2 + localization
sudo apt install -y ros-humble-navigation2 ros-humble-nav2-bringup
sudo apt install -y ros-humble-robot-localization
sudo apt install -y ros-humble-joint-state-publisher-gui
sudo apt install -y ros-humble-xacro ros-humble-teleop-twist-keyboard

# Python AI tools
pip3 install ultralytics opencv-python torch torchvision numpy

# Thêm vào ~/.bashrc để tự source mỗi lần mở terminal
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc

# Verify
ros2 --version   # phải thấy "ros2 humble"
gz sim --version # phải thấy Gazebo Harmonic
```

### Bước 0d — Đặt project files trong WSL2

```bash
# Code để trong WSL2 filesystem (nhanh hơn /mnt/c/ rất nhiều)
mkdir -p ~/agri_robot_ws/src
cd ~/agri_robot_ws/src

# Clone hoặc symlink project
# (nếu muốn giữ files trên Windows: /mnt/c/Claude_project/Agri_Robot_Simulation)
# Khuyến nghị: làm việc trong ~/agri_robot_ws/ để tránh I/O chậm
```

> **Lưu ý quan trọng:** Đặt code trong `~/` (WSL2 filesystem) thay vì `/mnt/c/` (Windows drive).
> Truy cập `/mnt/c/` có I/O chậm hơn 10-20x so với filesystem nội bộ của WSL2.

### Bước 0e — Chạy thử Turtlebot3 (kiểm tra toàn bộ pipeline)

```bash
sudo apt install -y ros-humble-turtlebot3 ros-humble-turtlebot3-gazebo
echo "export TURTLEBOT3_MODEL=burger" >> ~/.bashrc
source ~/.bashrc

# Mở Gazebo simulation:
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
# → Cửa sổ Gazebo xuất hiện trên Windows ✓

# Mở terminal thứ 2 trong VS Code: chạy Nav2
ros2 launch turtlebot3_navigation2 navigation2.launch.py
# → Robot tự di chuyển khi gửi goal từ RViz2 ✓
```

---

## Phase 1 — Mô hình Robot (URDF)

**Mục tiêu:** Robot 4 bánh xuất hiện trong Gazebo, di chuyển được bằng teleop

**Files cần tạo:**
- `agri_robot/urdf/agri_robot.urdf.xacro` — mô hình 3D
- `agri_robot/config/controllers.yaml` — 4WD skid-steer config
- `agri_robot/launch/gazebo.launch.py` — khởi động Gazebo
- `agri_robot/worlds/empty_field.sdf` — world trống để test

**Verification:**
```bash
ros2 launch agri_robot gazebo.launch.py
# → Robot xuất hiện trong Gazebo
ros2 run teleop_twist_keyboard teleop_twist_keyboard
# → Di chuyển được bằng phím
```

---

## Phase 2 — Localization (GPS + IMU → EKF)

**Mục tiêu:** Robot biết vị trí của mình (lat/lon → x/y/z trong map frame)

**Files cần tạo:**
- `agri_robot/config/ekf.yaml` — EKF filter config
- `agri_robot/config/navsat.yaml` — navsat_transform config
- `agri_robot/launch/localization.launch.py`

**Verification:**
```bash
ros2 topic echo /odometry/global
# → Có data vị trí liên tục (x, y, z)
ros2 topic echo /gps/fix
# → Có latitude, longitude
```

---

## Phase 3 — Nav2 + Return-to-Home

**Mục tiêu:** Robot nhận waypoint, tự di chuyển đến đích, và tự về home

**Files cần tạo:**
- `agri_robot/config/nav2_params.yaml` — Nav2 full config
- `agri_robot/launch/navigation.launch.py`
- `agri_robot/scripts/navigation/return_home.py` — logic về nhà

**Verification:**
```bash
# Gửi goal qua RViz2 → robot tự đi
# Chạy return_home.py → robot về đúng điểm xuất phát
ros2 run agri_robot return_home
```

---

## Phase 4 — AI Obstacle Avoidance

**Mục tiêu:** Phát hiện vật cản bằng YOLOv8 + depth cam, Nav2 tự tránh

**Files cần tạo:**
- `agri_robot/scripts/ai_vision/yolo_detector.py` — ROS 2 node YOLOv8
- `agri_robot/scripts/ai_vision/obstacle_publisher.py` — publish vị trí vật cản
- `agri_robot/config/nav2_params.yaml` — thêm obstacle layer vào costmap

**Verification:**
```bash
ros2 run agri_robot yolo_detector
# → Topic /detected_obstacles có data khi camera thấy người/vật
# Spawn model người trong Gazebo → robot tránh tự động
```

---

## Phase 5 — Farm World + Integration Testing

**Mục tiêu:** Test toàn bộ hệ thống trong môi trường đồng ruộng thực tế

**Files cần tạo:**
- `agri_robot/worlds/farm_field.sdf` — đồng ruộng có hàng cây, địa hình gồ ghề
- `agri_robot/launch/full_demo.launch.py` — launch tất cả cùng lúc

**Test scenarios:**
1. A → B → return-to-home tự động
2. Vật cản tĩnh (cây, cột) → nav tránh
3. Vật cản động (người đi lại) → AI detect + tránh
4. GPS signal loss → robot dừng, chờ signal

---

## Lộ trình Học (Người mới bắt đầu)

| Tuần | Nội dung học |
|---|---|
| 1 | ROS 2 concepts: node, topic, service, action. Chạy examples |
| 2 | URDF + RViz2: tạo robot đơn giản, xem joints |
| 3 | Gazebo + teleop: robot di chuyển trong simulator |
| 4 | Nav2 basics: autonomous navigation với map có sẵn |
| 5 | GPS + robot_localization: outdoor navigation |
| 6 | YOLOv8: chạy detection trên camera feed |
| 7 | Tích hợp AI + Nav2: obstacle avoidance hoàn chỉnh |
| 8 | Full demo + testing tất cả scenarios |
