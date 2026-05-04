# Development Phases

## Simulation Phases (WSL2 + Gazebo)

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Cài đặt môi trường | ✅ Xong |
| 1 | URDF + Gazebo | ✅ Xong |
| 2 | Localization (Dual EKF) | ✅ Xong |
| 3 | Nav2 + Return-to-Home + Teleop | ✅ Xong |
| 4 | AI Obstacle Avoidance (YOLOv8 + depth camera) | 🔧 Code xong — cần test Gazebo |
| 5 | Farm World + Integration Testing | ⬜ Chưa bắt đầu |

## Real Hardware Phases (Raspberry Pi 3 + Flutter App)

| Phase | Nội dung | Trạng thái |
|---|---|---|
| A | Hardware Drivers (RC + Motor PWM + ESTOP) | ✅ Xong |
| B | Localization configs cho real hardware | ✅ Xong (trong agri_robot_control/config) |
| C | Mode Manager + MQTT Bridge + Flutter App MVP | ⬜ **Tiếp theo** |
| D | Boundary Manager + Coverage Planner + App Boundary Editor | ⬜ |
| E | Follow Mode + Stuck Detector + App Follow UI | ⬜ |
| F | Integration + Cloudflare Tunnel + Polish | ⬜ |

---

## Phase A — Hardware Drivers ✅

**Files đã tạo:**
- `agri_robot_hardware/agri_robot_hardware/drivers/rc_protocol.py`
  - `RCProtocolDriver` ABC + `IBUSDriver` + `SBUSDriver` + `PPMDriver` + `MockRCDriver`
  - Factory `create_driver(protocol, **kwargs)`
- `agri_robot_hardware/agri_robot_hardware/rc_interface_node.py`
  - Đọc RC channels, map → `/cmd_vel_teleop` (Twist), `/rc/mode_switch` (Int8),
    `/estop_trigger` (Empty), `/estop_clear` (Empty), `/rc/boundary_btn` (Empty)
  - Deadband ±30µs, edge detection ESTOP + boundary button
- `agri_robot_hardware/agri_robot_hardware/drivers/pwm_motor.py`
  - `L298NDriver` (RPi.GPIO, software PWM 1kHz) + `MockPWMMotor`
  - Factory `create_motor_driver(config)`
- `agri_robot_hardware/agri_robot_hardware/motor_driver_node.py`
  - Subscribe `/cmd_vel_mux` → differential mixing → L298N GPIO PWM
  - **ESTOP guardian**: subscribe `/estop_trigger` → `motor.brake()` ngay lập tức (bypass twist_mux)
  - Watchdog 0.5s: stop nếu không có cmd_vel
  - Dead-reckoning odometry → publish `/odom`
  - Publish `/motor/status` (JSON)
- `agri_robot_hardware/config/hardware_params.yaml` — default `mock`, đổi `l298n`/`ibus` trên Pi
- `agri_robot_hardware/launch/hardware.launch.py`

**Verify trên Pi:**
```bash
ros2 launch agri_robot_hardware hardware.launch.py protocol:=ibus motor_driver:=l298n
ros2 topic echo /cmd_vel_teleop      # RC sticks → Twist messages
ros2 topic echo /estop_trigger       # CH6 xuống LOW → Empty message
ros2 topic echo /motor/status        # JSON {left, right, estop}
```

---

## Phase B — Localization Configs ✅

**Files đã tạo trong `agri_robot_control/config/`:**
- `ekf_local.yaml` — `/odom` + `/imu/data` → `/odometry/local` (30 Hz)
- `ekf_global.yaml` — `/odometry/local` + `/odometry/gps` → `/odometry/global` (10 Hz)
- `navsat.yaml` — GPS → `/odometry/gps` + `/gps/filtered`
  - **Phải update `datum_lat`/`datum_lon`** cho field thực tế trước deploy
  - `use_odometry_yaw: false` — dùng IMU/EKF yaw (không dùng GPS track direction)
- `agri_robot_control/launch/localization.launch.py` — GPS driver + 2 EKF + navsat

**Verify trên Pi:**
```bash
ros2 launch agri_robot_control localization.launch.py gps_port:=/dev/ttyACM0
ros2 topic hz /odometry/global       # → ~10 Hz sau 60s warm-up
ros2 topic echo /gps/fix             # → lat/lon từ GPS hardware
```

---

## Phase C — Mode Manager + MQTT + Flutter App MVP ⬜ (Tiếp theo)

**Goal:** App hiển thị robot position trên OSM map, ESTOP button hoạt động, mode switch.

**Files cần tạo:**

ROS 2 (đã có code, cần test):
- `agri_robot_control/agri_robot_control/mode_manager_node.py` ✅
- `agri_robot_control/agri_robot_control/mqtt_bridge_node.py` ✅

Flutter app (chưa tạo) — `agri_robot_app/`:
- `pubspec.yaml` — flutter_map, mqtt_client, geolocator, latlong2, provider
- `lib/main.dart`
- `lib/services/mqtt_service.dart` — paho MQTT over WiFi/5G
- `lib/services/location_service.dart` — phone GPS
- `lib/screens/map_screen.dart` — OSM map + robot marker + heading arrow
- `lib/screens/control_screen.dart` — mode selector + status
- `lib/widgets/emergency_stop_btn.dart` — prominent red FAB

**Verify:**
```bash
# Pi: start full system (mock mode for desktop test)
ros2 launch agri_robot_control full_system.launch.py

# App: connect MQTT → robot/position xuất hiện trên map
# App: nhấn ESTOP → /estop_trigger xuất hiện trong ros2 topic echo
```

---

## Phase D — Boundary + Coverage ⬜

**Goal:** Robot tự chạy lawnmower pattern trong GPS boundary.

**Nodes đã viết (cần test):**
- `boundary_manager_node.py` ✅ — GPS polygon, RC-walk recording, violation enforcement
- `coverage_planner_node.py` ✅ — boustrophedon algorithm, configurable row_offset
- `gps_navigator_node.py` ✅ — pure-pursuit, 10 Hz control loop, 1.5m waypoint tolerance

**Flutter:**
- `lib/screens/boundary_editor.dart` — tap map → add waypoint, draw polygon, send to Pi

---

## Phase E — Follow Mode + Stuck Detection ⬜

**Goal:** Robot đi theo điện thoại. Stuck alert qua app.

**Nodes đã viết (cần test):**
- `follow_mode_node.py` ✅ — phone GPS, 0.5m hysteresis, 3s GPS timeout
- `stuck_detector_node.py` ✅ — Layer 1: cmd_vel/odom mismatch, Layer 2: GPS confirm

**Flutter:**
- Follow mode UI + notification khi stuck

---

## Phase F — Integration + Polish ⬜

- Full system test tất cả modes
- Tune pure-pursuit PID gains
- Cloudflare Tunnel setup (`cloudflared service install`)
- MQTT reconnect handling trên app
- Battery low alert

---

## Simulation — Phase 4 AI Obstacle Avoidance 🔧

**Code đã viết:**
- `agri_robot/agri_robot/ai_vision/yolo_obstacle_node.py` — RGB+depth sync → YOLOv8 → PointCloud2 `/yolo_obstacles`
- `agri_robot/launch/ai_vision.launch.py`
- `agri_robot/urdf/agri_robot.urdf.xacro` — depth camera sensor added (`libgazebo_ros_camera.so`, type=depth)
- `agri_robot/config/nav2_params.yaml` — ObstacleLayer với `sensor_frame: "camera_optical_link"`

**Bugs đã fix:**
- BUG-001: `frame_id = 'camera_optical_link'` (was `camera_optical_frame`)
- BUG-002: `_images_cb` luôn publish PointCloud2 dù model=None
- BUG-003: Xóa `<format>` tag khỏi depth sensor (Gazebo tự set 32FC1)
- BUG-004: Thêm `velocity_smoother` vào `lifecycle_manager_navigation.node_names`

**Cần test:**
```bash
# Start hệ thống như bình thường, thêm terminal 4:
ros2 launch agri_robot ai_vision.launch.py
ros2 topic hz /yolo_obstacles     # phải có data khi camera thấy vật cản
# Spawn người trong Gazebo, verify robot tránh
```

---

## Restart Workflow (Simulation)

Claude Code không thể start Gazebo (cần DISPLAY). User phải start thủ công:

```bash
# Terminal 1 — Gazebo
ros2 launch agri_robot gazebo.launch.py

# Terminal 2 — Localization
ros2 launch agri_robot localization.launch.py

# Terminal 3 — Nav2
ros2 launch agri_robot navigation.launch.py

# Terminal 4 — Test
ros2 run agri_robot return_home
```

## Restart Workflow (Real Hardware on Pi)

```bash
# Single command bringup
ros2 launch agri_robot_control full_system.launch.py protocol:=ibus motor_driver:=l298n gps_port:=/dev/ttyACM0

# Debug individual nodes
ros2 launch agri_robot_hardware hardware.launch.py    # RC + motors only
ros2 launch agri_robot_control localization.launch.py # GPS + EKF only
ros2 launch agri_robot_control navigation.launch.py   # Control nodes only
```
