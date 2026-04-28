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

## Phase 0 — Cài đặt môi trường

```bash
# ROS 2 Humble
sudo apt update && sudo apt install ros-humble-desktop -y

# Gazebo Harmonic + ROS bridge
sudo apt install ros-humble-ros-gz -y

# Nav2 + localization
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup -y
sudo apt install ros-humble-robot-localization -y
sudo apt install ros-humble-joint-state-publisher-gui -y
sudo apt install ros-humble-xacro -y

# Python AI tools
pip install ultralytics opencv-python torch torchvision numpy

# Verify
ros2 --version   # phải thấy "ros2 humble"
gz sim --version # phải thấy Gazebo Harmonic
```

**Bước học đầu tiên:** Chạy Turtlebot3 simulation sẵn có để làm quen ROS 2 + Gazebo + Nav2:
```bash
sudo apt install ros-humble-turtlebot3* -y
export TURTLEBOT3_MODEL=burger
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
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
