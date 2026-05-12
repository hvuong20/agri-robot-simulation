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
| B | Localization configs cho real hardware | ✅ Xong |
| C | Mode Manager + MQTT Bridge + Flutter App MVP | ✅ Xong |
| D | Boundary Manager + Coverage Planner + App Boundary Editor | ✅ Xong |
| E | Follow Mode + Stuck Detector + App Follow UI | ✅ Xong |
| F | Integration + Battery Monitor + Cloudflare Tunnel + APK | ✅ Code xong — cần Pi 3 để test |

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
- `agri_robot_hardware/agri_robot_hardware/battery_monitor_node.py`
  - Mock: drain từ 85%, sine wave ripple, ~1%/phút
  - Real: ADS1115 I2C ADC, voltage divider ratio 0.25
  - Publish `/battery/status` JSON mỗi 5s
- `agri_robot_hardware/config/hardware_params.yaml` — default `mock`, đổi `l298n`/`ibus` trên Pi

**Verify trên Pi:**
```bash
ros2 launch agri_robot_hardware hardware.launch.py protocol:=ibus motor_driver:=l298n
ros2 topic echo /cmd_vel_teleop      # RC sticks → Twist messages
ros2 topic echo /estop_trigger       # CH6 xuống LOW → Empty message
ros2 topic echo /battery/status      # JSON {voltage, percent, low, critical}
```

---

## Phase B — Localization Configs ✅

**Files đã tạo trong `agri_robot_control/config/`:**
- `ekf_local.yaml` — `/odom` + `/imu/data` → `/odometry/local` (30 Hz)
- `ekf_global.yaml` — `/odometry/local` + `/odometry/gps` → `/odometry/global` (10 Hz)
- `navsat.yaml` — GPS → `/odometry/gps` + `/gps/filtered`
  - **Phải update `datum_lat`/`datum_lon`** cho field thực tế trước deploy
- `agri_robot_control/launch/localization.launch.py` — GPS driver + 2 EKF + navsat

**Verify trên Pi:**
```bash
ros2 launch agri_robot_control localization.launch.py gps_port:=/dev/ttyACM0
ros2 topic hz /odometry/global       # → ~10 Hz sau 60s warm-up
```

---

## Phase C — Mode Manager + MQTT + Flutter App MVP ✅

**ROS 2 nodes:**
- `agri_robot_control/agri_robot_control/mode_manager_node.py` — MANUAL/AUTO/FOLLOW/ESTOP state machine
- `agri_robot_control/agri_robot_control/mqtt_bridge_node.py` — paho-mqtt, auto-reconnect, relay battery/stuck/follow

**Flutter app (`agri_robot_app/lib/`):**
- `main.dart` — `_AppShell` bottom-nav (Map / Control), stuck SnackBar
- `services/mqtt_service.dart` — MQTT over WiFi/5G, QoS routing
- `services/location_service.dart` — phone GPS publish 5 Hz
- `screens/map_screen.dart` — OSM map, robot marker + heading arrow, boundary editor
- `screens/control_screen.dart` — mode selector, follow/coverage controls, battery chips, settings button
- `screens/settings_screen.dart` — MQTT broker config, reconnect
- `widgets/emergency_stop_btn.dart` — red FAB ESTOP
- `widgets/mode_selector.dart` — MANUAL/AUTO/FOLLOW toggle

---

## Phase D — Boundary + Coverage ✅

**Nodes:**
- `boundary_manager_node.py` — GPS polygon, RC-walk recording (CH7), app boundary, 10 Hz enforcement
- `coverage_planner_node.py` — Boustrophedon (lawnmower), publish `/waypoints_goal` + `/coverage_waypoints`
- `gps_navigator_node.py` — Pure-pursuit 10 Hz, heading từ EKF yaw, 1.5m tolerance

**Bug fix quan trọng:** `coverage_planner` → `gps_navigator` dùng topic `/waypoints_goal` (không phải `/coverage_waypoints`). Fix thêm `/waypoints_goal` publisher vào coverage_planner.

**Flutter:** Boundary editor inline trong `map_screen.dart` — tap map → polygon, send via MQTT.

---

## Phase E — Follow Mode + Stuck Detection ✅

**Nodes:**
- `follow_mode_node.py` — Phone GPS follow, 0.5m hysteresis, 3s timeout
- `stuck_detector_node.py` — Layer 1: cmd_vel/odom mismatch, Layer 2: GPS drift < 0.5m/3s

**Flutter:** Follow status card + stuck banner + SnackBar notification trong `control_screen.dart`.

---

## Phase F — Integration + Polish ✅ (code), cần Pi 3

**Đã hoàn thành:**
- `agri_robot_control/launch/simulation_bridge.launch.py` — kết nối control nodes với Gazebo
  - Key: gps_navigator + follow_mode remapped `/cmd_vel_auto` → `/cmd_vel`
- `agri_robot_control/launch/gazebo_sim.launch.py` — 1 lệnh chạy toàn bộ stack
- `agri_robot_hardware/agri_robot_hardware/battery_monitor_node.py` — mock + ADS1115
- `agri_robot_control/scripts/setup_cloudflare_tunnel.sh` — cài Cloudflare Tunnel trên Pi
- Battery UI trong Flutter: chips màu xanh/vàng/đỏ, parse từ MQTT `robot/status`
- Settings navigation từ Control Panel AppBar
- GitHub repo: https://github.com/hvuong20/agri-robot-simulation
- APK build: 48.3 MB (`app-release.apk`)

**Cần làm trên Pi 3:**
- [ ] Update `navsat.yaml` datum
- [ ] Chạy `setup_cloudflare_tunnel.sh`
- [ ] Đổi `hardware_params.yaml` sang l298n + ibus + ads1115
- [ ] Tune `nav.kp_angular`
- [ ] Full system test

---

## Simulation — Phase 4 AI Obstacle Avoidance 🔧

**Code đã viết:**
- `agri_robot/agri_robot/ai_vision/yolo_obstacle_node.py` — RGB+depth sync → YOLOv8 → PointCloud2
- `agri_robot/launch/ai_vision.launch.py`

**Cách test:**
```bash
# Terminal 1–3: Gazebo + Localization + Nav2
# Terminal 4:
ros2 launch agri_robot ai_vision.launch.py
ros2 topic hz /yolo_obstacles
```

---

## Restart Workflow (Simulation)

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
ros2 launch agri_robot_hardware hardware.launch.py    # RC + motors + battery
ros2 launch agri_robot_control localization.launch.py # GPS + EKF
ros2 launch agri_robot_control navigation.launch.py   # Control nodes
```
