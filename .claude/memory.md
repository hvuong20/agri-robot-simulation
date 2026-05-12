# Agri Robot — Project Memory

Ghi lại trạng thái thực tế, các lỗi đã gặp và cách fix, dùng để tham chiếu trong mọi session.

---

## Trạng thái Phase (cập nhật 2026-05-06)

### Simulation (WSL2 + Gazebo)

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Cài WSL2 + ROS 2 Humble + Gazebo Classic 11 | ✅ Hoàn thành |
| 1 | URDF robot 2-motor skid-steer (4 bánh) + Gazebo launch + teleop + twist_mux | ✅ Hoàn thành |
| 2 | Localization: dual EKF + navsat_transform | ✅ Hoàn thành |
| 3 | Nav2 + Return-to-Home | ✅ Hoàn thành — `Successfully returned home!` |
| 4 | AI Obstacle Avoidance (YOLOv8) | 🔧 Code xong, cần test Gazebo |
| 5 | Farm World + Integration Testing | ⬜ Chưa bắt đầu |

### Real Hardware + App (Raspberry Pi 3 + Flutter)

| Phase | Nội dung | Trạng thái |
|---|---|---|
| A | Hardware Drivers (RC + Motor PWM + ESTOP guardian + Battery) | ✅ Hoàn thành |
| B | Localization configs cho real hardware (EKF, navsat, no sim_time) | ✅ Hoàn thành |
| C | Mode Manager + MQTT Bridge + Flutter App MVP | ✅ Hoàn thành |
| D | Boundary Manager + Coverage Planner + App Boundary Editor | ✅ Hoàn thành |
| E | Follow Mode + Stuck Detector + App Follow UI | ✅ Hoàn thành |
| F | Battery Monitor + Cloudflare Tunnel + APK Build | ✅ Code xong — cần Pi 3 |

### Flutter & Build Environment (Windows)

| Item | Trạng thái | Chi tiết |
|---|---|---|
| Flutter SDK | ✅ | `C:\flutter\flutter` v3.38.9, PATH permanent |
| Android SDK | ✅ | `C:\Android\android-sdk`, android-36, build-tools 35.0.0 |
| Java 17 | ✅ | `C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot` |
| APK | ✅ 48.3 MB | `agri_robot_app\build\app\outputs\flutter-apk\app-release.apk` |
| GitHub | ✅ | https://github.com/hvuong20/agri-robot-simulation (public) |

---

## Cấu hình thực tế (khác với plan ban đầu)

### Robot URDF — thông số thực
```
Chassis:  0.80 × 0.55 × 0.20 m  (nhỏ hơn plan XAG R80)
Bánh:     đường kính 0.20 m, bề rộng 0.08 m
Footprint radius: 0.50 m
Track width (wheel_separation): 0.62 m
Max speed: 1.5 m/s linear, 1.0 rad/s angular
```

### Dẫn động 2 Motor Skid-Steer (4 bánh) — 2 diff_drive plugins (QUAN TRỌNG)
Robot phần cứng chỉ có **2 motor**: motor trái (front_left + rear_left liên kết cơ học) và motor phải (front_right + rear_right liên kết cơ học). Đây là skid-steer diff-drive tiêu chuẩn — **không phải 4 motor độc lập**.

Trong Gazebo Classic, `libgazebo_ros_diff_drive.so` chỉ nhận 1 left joint + 1 right joint nên phải dùng **2 plugin** để kéo đủ 4 bánh (hiệu ứng tương đương 2-motor):
- `drive_front`: `front_left_wheel_joint` + `front_right_wheel_joint` — `publish_odom: true`
- `drive_rear`: `rear_left_wheel_joint` + `rear_right_wheel_joint` — `publish_odom: false` (tránh duplicate)
- Cả 2 subscribe `/cmd_vel_mux` (output của twist_mux) qua `<remapping>cmd_vel:=cmd_vel_mux</remapping>`

**QUAN TRỌNG:** Không dùng `<command_topic>` — tag đó bị Gazebo Classic ROS 2 ignore silently. Phải dùng `<remapping>` bên trong `<ros>`.

### Dual EKF — topic names thực
```
local EKF:  /odom + /imu/data  →  /odometry/local   (KHÔNG dùng /odometry/filtered)
navsat:     /odometry/local + /gps/fix  →  /odometry/gps
global EKF: /odometry/local + /odometry/gps  →  /odometry/global
Nav2:       odom_topic = /odometry/global
```
**Tại sao dùng `/odometry/local` thay `/odometry/filtered`:** Nếu đặt tên là `/odometry/filtered`, global EKF (remapped to `/odometry/global`) vẫn subscribe vào `/odometry/filtered` gây **circular subscription** — global EKF tự feed vào chính nó.

### BT XML paths (hardcoded trong nav2_params.yaml)
```
default_nav_to_pose_bt_xml:
  /home/hvuong20/agri_robot_ws/install/agri_robot/share/agri_robot/config/navigate_to_pose_bt.xml

default_nav_through_poses_bt_xml:
  /home/hvuong20/agri_robot_ws/install/agri_robot/share/agri_robot/config/navigate_through_poses_bt.xml
```

### return_home.py — implementation thực
Không dùng `waitUntilNav2Active()` (gây vòng chờ AMCL). Thay bằng:
```python
_ac = ActionClient(navigator, NavigateToPose, 'navigate_to_pose')
while not _ac.wait_for_server(timeout_sec=1.0):
    ...  # chờ action server
```
Lưu home từ `/odometry/global` (không phải `/gps/fix`) — đã ở map frame, dùng trực tiếp làm PoseStamped.

---

### twist_mux — tách teleop và Nav2 (QUAN TRỌNG)
`velocity_smoother` (Nav2 node) publish `/cmd_vel` liên tục ở 20 Hz với zero velocity → **override teleop**.
**Fix:** Dùng `twist_mux` để route `/cmd_vel_teleop` (priority 10) và `/cmd_vel` (priority 1) → `/cmd_vel_mux`.
Robot URDF plugins (`drive_front`, `drive_rear`) subscribe `/cmd_vel_mux` (không phải `/cmd_vel`).

Topology thực tế:
```
teleop → /cmd_vel_teleop (priority 10) ─┐
Nav2 (velocity_smoother) → /cmd_vel (p1)├─► twist_mux → /cmd_vel_mux → robot
```

File config: `config/twist_mux.yaml`
Launch: twist_mux node trong `gazebo.launch.py`, remap `/cmd_vel_out` → `/cmd_vel_mux`
Teleop command: `ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r /cmd_vel:=/cmd_vel_teleop`

---

## Lỗi đã gặp và cách fix (Phase 1–3)

### [P1] Plugin depth camera không load
```
[Err] Failed to load plugin libgazebo_ros_openni_kinect.so
```
**Fix:** Dùng `libgazebo_ros_camera.so` thay thế (Phase 4 mới cần depth).

### [P1] Robot không spawn (exit code 1)
`spawn_entity.py` timeout sau 31 giây vì Gazebo chưa khởi động xong plugin.
**Fix:** Thêm `TimerAction(period=10.0)` trong `gazebo.launch.py` trước khi gọi spawn_entity.

### [P2] `/odometry/global` không có data — bị treo
**Root cause 1:** `navsat_transform_node` chờ IMU heading (robot đứng yên = không có heading).
**Fix:** `use_odometry_yaw: true` trong `navsat.yaml` + giảm `delay: 1.0`.

**Root cause 2:** `use_sim_time` chưa set trong localization nodes.
**Fix:** Thêm `{'use_sim_time': True}` vào tất cả 3 nodes trong `localization.launch.py`.

**Root cause 3:** Global EKF circular subscription.
**Fix:** Rename local EKF output từ `/odometry/filtered` → `/odometry/local`.

### [P3] Zombie Nav2 nodes — velocity_smoother conflict
Khi Nav2 crash và restart, các node cũ có thể còn trong DDS graph (ghost node).
Khi launch lại, `velocity_smoother` gặp conflict với ghost node → configure fail ngay lập tức (không log gì).
**Fix:** `pkill -9 -f 'velocity_smoother|bt_navigator|...'` rồi chờ 5–8 giây cho DDS clear.
**Verify clean:** `ros2 node list | grep velocity` → không có kết quả.

### [P3] Nav2 background process chết khi shell exit
Khi dùng `bash -c "nohup ros2 launch ... & echo done"` (shell exit ngay), Nav2 có thể chết.
**Fix:** Giữ shell sống ít nhất 5 giây: `... & sleep 5 && echo done`.
Localization dùng `& sleep 12 && tail` nên sống được.

### [P3] BT node không tìm thấy khi load
```
Could not load library: libnav2_path_expiring_timer_condition_bt_node.so
```
**Fix:** Xóa các plugin không tồn tại khỏi `plugin_lib_names` trong `nav2_params.yaml`.

### [P3] Empty Tree / RemovePassedGoals
```
[bt_navigator] Exception when loading BT: Node not recognized: RemovePassedGoals
Error loading XML: navigate_to_pose_w_replanning_and_recovery.xml
```
**Root cause:** nav2_bringup trong Humble **không forward** `default_nav_to_pose_bt_xml` launch argument → bt_navigator luôn load default BT XML từ Nav2.

**Fix:** Set path trực tiếp trong `nav2_params.yaml`:
```yaml
bt_navigator:
  ros__parameters:
    default_nav_to_pose_bt_xml: "/home/hvuong20/agri_robot_ws/install/..."
    default_nav_through_poses_bt_xml: "/home/hvuong20/agri_robot_ws/install/..."
```

**Quan trọng:** bt_navigator load **2 BT XML** khi khởi động (to_pose VÀ through_poses). Phải cung cấp custom XML cho cả 2.

### [P3] `error_code_id` port không tồn tại trong nav2 1.1.20
```
Possible typo? ...tried to remap port "error_code_id" in node [ComputePathToPose]...
```
`ComputePathToPose`, `ComputePathThroughPoses`, `Spin`, `Wait`, `BackUp` trong build này (nav2 1.1.20-1jammy) **không expose port `error_code_id`**.
**Fix:** Xóa tất cả `error_code_id="{...}"` khỏi cả 2 BT XML files.

### [P3] `BackUp` action server race condition khi bt_navigator load
```
"backup" action server not available after waiting for 1.00s
```
bt_navigator load BT XML ngay khi behavior_server vừa activated, trước khi
behavior_server kịp register action server `backup`.
**Fix:** Bỏ `BackUp`, `Spin`, `Wait` khỏi `navigate_through_poses_bt.xml` — chỉ dùng `ClearEntireCostmap` (service, không phải action).

### [P3] `waitUntilNav2Active()` treo vô hạn
```
[return_home] Waiting for amcl/get_state...  (loop mãi không thoát)
```
**Fix:** Bỏ `waitUntilNav2Active()`, thay bằng `ActionClient.wait_for_server()` trực tiếp.

### [P3] `default_nav_to_pose_bt_xml: ""` gây Empty Tree
Khi set `default_nav_to_pose_bt_xml: ""` trong yaml, bt_navigator load empty string → không có tree.
**Fix:** Xóa hoàn toàn dòng đó nếu không muốn set, HOẶC set path đầy đủ.

### [P3] ModuleNotFoundError: No module named 'agri_robot.navigation'
**Root cause:** Chạy `cp -r` nhiều lần → nested directory: `agri_robot/agri_robot/agri_robot/navigation/`
**Fix:** `rm -rf ~/agri_robot_ws/src/agri_robot && cp -r ... ~/agri_robot_ws/src/agri_robot`

### [P3] Teleop không hoạt động — robot đứng yên khi bấm 'i'
**Root cause:** `velocity_smoother` (Nav2) publish zero velocity lên `/cmd_vel` ở 20 Hz, override mọi teleop.
`ros2 topic info /cmd_vel` → Publisher count: 6 (velocity_smoother + behavior_server).
**Fix:** Dùng `twist_mux` — xem phần "twist_mux" ở trên.

### [colcon] Build lỗi "can't copy ... urdf/urdf: doesn't exist or not a regular file"
**Root cause:** Dùng `cp -r .../config/` tạo nested dir `config/config/` hoặc `urdf/urdf/` trong src.
Colcon cache lưu nested path → build lần sau fail dù đã xóa nested dir.
**Fix:** `rm -rf build/agri_robot install/agri_robot` rồi rebuild sạch.
**Phòng ngừa:** Copy từng file thay vì `cp -r dir/` khi dest dir đã tồn tại:
```bash
cp /mnt/c/.../config/twist_mux.yaml ~/agri_robot_ws/src/agri_robot/config/
```

---

## Workflow Restart (khi Gazebo crash)

Gazebo phải được start từ terminal có DISPLAY (WSL2 với WSLg). Claude Code không thể start Gazebo từ Bash tool (không có DISPLAY).

```bash
# Terminal 1 — Gazebo
source /opt/ros/humble/setup.bash && source ~/agri_robot_ws/install/setup.bash
ros2 launch agri_robot gazebo.launch.py
# Chờ robot xanh xuất hiện trong cửa sổ Gazebo

# Terminal 2 — Localization
source /opt/ros/humble/setup.bash && source ~/agri_robot_ws/install/setup.bash
ros2 launch agri_robot localization.launch.py
# Chờ: [navsat_transform]: Datum (latitude, longitude...)

# Terminal 3 — Nav2
source /opt/ros/humble/setup.bash && source ~/agri_robot_ws/install/setup.bash
ros2 launch agri_robot navigation.launch.py
# Chờ: [lifecycle_manager_navigation]: Managed nodes are active

# Terminal 4 — Return Home test
source /opt/ros/humble/setup.bash && source ~/agri_robot_ws/install/setup.bash
ros2 run agri_robot return_home
```

**Thứ tự bắt buộc:** Terminal 1 trước (Gazebo cần ổn định), rồi 2, rồi 3, rồi 4.
**Quan trọng:** Mỗi terminal phải `source` cả 2 setup files trước khi chạy lệnh.

---

## Files quan trọng — vị trí thực trong WSL2

| File | Đường dẫn WSL2 |
|---|---|
| Source package | `~/agri_robot_ws/src/agri_robot/` |
| Installed package | `~/agri_robot_ws/install/agri_robot/share/agri_robot/` |
| URDF | `src/agri_robot/urdf/agri_robot.urdf.xacro` |
| EKF local config | `src/agri_robot/config/ekf_local.yaml` |
| EKF global config | `src/agri_robot/config/ekf_global.yaml` |
| navsat config | `src/agri_robot/config/navsat.yaml` |
| Nav2 params | `src/agri_robot/config/nav2_params.yaml` |
| BT XML (to_pose) | `src/agri_robot/config/navigate_to_pose_bt.xml` |
| BT XML (through_poses) | `src/agri_robot/config/navigate_through_poses_bt.xml` |
| Return home script | `src/agri_robot/agri_robot/navigation/return_home.py` |
| Logs (Nav2) | `/tmp/nav2.log` |
| Logs (localization) | `/tmp/localization.log` |

**Windows mirror:** `c:\Claude_project\Agri_Robot_Simulation\agri_robot\`
**Đồng bộ từ Windows → WSL2:** `cp -r /mnt/c/Claude_project/Agri_Robot_Simulation/agri_robot/config/ ~/agri_robot_ws/src/agri_robot/config/`

---

## Rebuild sau khi thay đổi file

```bash
cd ~/agri_robot_ws
colcon build --packages-select agri_robot --symlink-install
# Sau build: config files được install vào share/agri_robot/config/
# Python files được symlink — không cần rebuild khi sửa .py
```

**Khi nào cần rebuild bắt buộc:**
- Thêm file mới vào `config/` (phải chạy colcon để install)
- Thay đổi `setup.py` hoặc `package.xml`
- Thêm entry_points mới

**Khi nào KHÔNG cần rebuild (symlink-install):**
- Sửa nội dung `.py` files hiện có
- Sửa nội dung `.yaml` files hiện có (đã được install, sửa source là đủ nếu dùng --symlink-install)

---

## Phase 4 — AI Obstacle Avoidance (YOLOv8)

### Files tạo ra
| File | Mô tả |
|---|---|
| `agri_robot/ai_vision/__init__.py` | Package marker |
| `agri_robot/ai_vision/yolo_obstacle_node.py` | ROS 2 node: RGB+depth sync → YOLOv8 → PointCloud2 |
| `launch/ai_vision.launch.py` | Khởi động yolo_obstacle_node |

### Pipeline
```
/camera/image_raw  ──┐
                     ├─► ApproximateTimeSynchronizer
/camera/depth/image_raw ┘         │
                                  ▼
                         YoloObstacleNode (yolov8n.pt)
                                  │ PointCloud2
                                  ▼
                         /yolo_obstacles
                                  │
                                  ▼
                    Nav2 ObstacleLayer (local_costmap)
                                  │
                                  ▼
                         DWB Local Planner → tránh vật cản
```

### Topic thực tế
- `/camera/image_raw` — RGB 15Hz từ `libgazebo_ros_camera.so` (type=camera)
- `/camera/depth/image_raw` — Depth 10Hz từ `libgazebo_ros_camera.so` (type=depth, 32FC1)
- `/camera/camera_info` — Camera intrinsics
- `/yolo_obstacles` — PointCloud2, frame `camera_optical_frame`

### Cấu hình nav2_params.yaml (obstacle layer)
```yaml
obstacle_layer:
  plugin: "nav2_costmap_2d::ObstacleLayer"
  observation_sources: yolo_sensor
  yolo_sensor:
    topic: /yolo_obstacles
    data_type: "PointCloud2"
    sensor_frame: "camera_optical_frame"
    observation_persistence: 1.0
    marking: True
    clearing: True
    obstacle_max_range: 5.0
    obstacle_min_range: 0.3
```

### Cách test Phase 4
```bash
# Terminal 1–3: Gazebo + Localization + Nav2 (như trước)

# Terminal 4 — AI Vision node
source /opt/ros/humble/setup.bash && source ~/agri_robot_ws/install/setup.bash
ros2 launch agri_robot ai_vision.launch.py

# Terminal 5 — Verify detection
ros2 topic echo /yolo_obstacles   # phải có data khi camera thấy vật cản

# Spawn người trong Gazebo để test
ros2 run gazebo_ros spawn_entity.py \
  -database person_standing -entity test_person \
  -x 2.0 -y 0.0 -z 0.0
```

---

## Git commits Phase 3 + Hardware

```
0d90c09 feat(Phase A+B): add hardware drivers + control stack for Raspberry Pi 3
d178015 fix: load custom BT XML directly from nav2_params
9ba6e52 fix: rename local EKF output to /odometry/local
b88f530 fix: delay spawn_entity by 10s to wait for Gazebo
64f3100 feat: true 4WD — add rear axle drive plugin
d3bb45a fix: add use_sim_time=true to all localization nodes
c0a6c84 fix: replace openni_kinect depth plugin
```

---

## Real Hardware — Packages đã tạo (Phase A+B)

### agri_robot_hardware — GPIO + RC drivers

**RC Protocol driver** (`drivers/rc_protocol.py`):
- Abstract base `RCProtocolDriver`: `open()`, `read_channels() → dict[int,int]|None`, `is_connected()`, `close()`
- `IBUSDriver`: 115200 baud, 32-byte frame `[0x20 0x40 + 28 bytes + 2 byte checksum]`, channels 1–14
- `SBUSDriver`: 100000 baud, 8E2 inverted UART, 11-bit packed channels. Pi 3 cần hardware inverter
- `PPMDriver`: pigpio GPIO interrupt, sync gap > 2500µs
- `MockRCDriver`: `set_channel(ch, value)` để test không cần hardware
- `create_driver(protocol, **kwargs)` factory

**rc_interface_node**: poll `rc.poll_rate_hz` (default 50 Hz), publish:
- `/cmd_vel_teleop` (Twist): CH2=throttle, CH1=steering, deadband ±30µs
- `/rc/mode_switch` (Int8): CH5 → 0=MANUAL/1=AUTO/2=FOLLOW
- `/estop_trigger` (Empty): CH6 falls below 1300µs → rising edge
- `/estop_clear` (Empty): CH6 returns above 1300µs → falling edge
- `/rc/boundary_btn` (Empty): CH7 rising edge

**PWM Motor driver** (`drivers/pwm_motor.py`):
- `L298NDriver`: RPi.GPIO, software PWM 1kHz, 6 GPIO pins (left_en/in1/in2 + right_en/in1/in2)
- `MockPWMMotor`: stores last commanded speeds, `is_braking` flag
- `create_motor_driver(config)` factory

**motor_driver_node**:
- Subscribe `/cmd_vel_mux` → differential mixing (v_left = v - ω*L/2)
- **ESTOP**: subscribe `/estop_trigger` → `motor.brake()` NGAY LẬP TỨC (không qua twist_mux)
- Watchdog: stop nếu không có cmd_vel trong `motor.cmd_timeout_s` (default 0.5s)
- Dead-reckoning odom: `x += v*cos(yaw)*dt`, đủ dùng khi chưa có encoder
- Fallback to `MockPWMMotor` nếu GPIO setup lỗi

**config/hardware_params.yaml** — tất cả default `mock`, switch to real khi deploy:
```yaml
rc.protocol: mock          # → ibus / sbus / ppm
motor.driver: mock         # → l298n
motor.left_en: 12          # GPIO BCM (HW PWM0)
motor.right_en: 13         # GPIO BCM (HW PWM1)
```

### agri_robot_control — Navigation + App Bridge

**Nodes:**
| Node | Chức năng |
|---|---|
| `mode_manager_node` | MANUAL/AUTO/FOLLOW/ESTOP state machine. ESTOP sticky — RC + optional MQTT ack |
| `boundary_manager_node` | GPS polygon, RC-walk recording (CH7 button), app boundary, violation enforcement (10 Hz) |
| `coverage_planner_node` | Boustrophedon path: rotate polygon to longest edge, sweep rows at `row_offset_m` |
| `gps_navigator_node` | Pure-pursuit, 10 Hz. Heading từ EKF yaw (convert ROS yaw → geographic bearing) |
| `follow_mode_node` | Phone GPS follow, 0.5m hysteresis, 3s timeout. Phase 4: camera person tracking |
| `mqtt_bridge_node` | paho-mqtt, auto-reconnect thread, QoS routing. ESTOP QoS 2 |
| `stuck_detector_node` | Layer 1: cmd_vel vs /odom velocity. Layer 2: GPS drift < 0.5m over 3s |

**Topic wiring:**
```
RC CH1/CH2 → rc_interface_node → /cmd_vel_teleop (p20) ─┐
                                                         ├─ twist_mux → /cmd_vel_mux → motor_driver_node → GPIO
gps_navigator / follow_mode → /cmd_vel_auto (p5) ────────┘
                                                                            ↑
RC CH6 → /estop_trigger ────────────────────────────────────────────────────┘ (bypass twist_mux)

mode_manager_node publishes /current_mode → gps_navigator, follow_mode, boundary_manager gating
```

**Deploy lên Pi:**
1. Sửa `hardware_params.yaml`: đổi `protocol: ibus` (hoặc sbus/ppm), `driver: l298n`, `battery.driver: ads1115`
2. Sửa `navsat.yaml`: cập nhật `datum_lat`, `datum_lon` cho field thực tế
3. Disable Bluetooth: thêm `dtoverlay=disable-bt` vào `/boot/config.txt`, reboot
4. Cài dependencies Pi: `pip3 install RPi.GPIO pyserial paho-mqtt adafruit-circuitpython-ads1x15`
5. `ros2 launch agri_robot_control full_system.launch.py protocol:=ibus motor_driver:=l298n`

---

## Quyết định kỹ thuật đã chốt

### RC Transmitter
- **FlySky FS-i6** (6 kênh) đủ dùng — CH1–CH6 hoạt động
- CH7 (boundary waypoint button RC) không có → dùng boundary editor trên app thay thế
- Cần receiver **FS-iA6B** (có iBUS), không phải FS-iA6 (PPM only)

### Motor nâng cấp (payload 180 kg)
- Tổng tải: ~240 kg (180 kg hàng + 60 kg khung)
- **Motor**: 2x DC 48V 500W gear motor (~56 Nm/motor với safety factor)
- **Driver**: Cytron MD60C 60A (interface PWM+DIR giống L298N, ít thay đổi code)
- **Pin**: LiFePO4 48V 20Ah + BMS 48V 30A (an toàn hơn LiPo cho robot nặng)
- **Battery config**: đổi `cell_count: 16`, `FULL_CELL_V: 3.65`, `EMPTY_CELL_V: 3.0`
- **Code cần thêm**: `CytronMD60CDriver` trong `pwm_motor.py` (~30 dòng, interface tương tự L298N)
- L298N **không dùng được** với motor lớn (max 2A, 3A peak)

### Simulation Bridge (Gazebo ↔ Control nodes)
- `simulation_bridge.launch.py`: 7 control nodes với `use_sim_time: True`
- Key remapping: `/cmd_vel_auto` → `/cmd_vel` để feed vào Gazebo twist_mux (priority 1)
- Gazebo datum: 10.45°N, 105.63°E

### Flutter stamp fix
- `C:\flutter\flutter\bin\cache\flutter_tools.stamp` phải chứa git HEAD + `:`
- Nếu flutter bootstrap fail "Building flutter tool... The system cannot find path": cập nhật stamp
  ```powershell
  $h = cmd /c "pushd C:\flutter\flutter & git rev-parse HEAD"; Set-Content "C:\flutter\flutter\bin\cache\flutter_tools.stamp" "`"$($h.Trim()):`""
  ```

### Build APK (Windows)
```powershell
$env:JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot"
$env:ANDROID_HOME="C:\Android\android-sdk"
$env:Path="C:\flutter\flutter\bin;$env:JAVA_HOME\bin;" + $env:Path
cd C:\Claude_project\Agri_Robot_Simulation\agri_robot_app
flutter build apk --release
# Output: build\app\outputs\flutter-apk\app-release.apk
```
