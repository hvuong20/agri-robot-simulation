# Agri Robot — Project Memory

Ghi lại trạng thái thực tế, các lỗi đã gặp và cách fix, dùng để tham chiếu trong mọi session.

---

## Trạng thái Phase (cập nhật 2026-04-29)

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Cài WSL2 + ROS 2 Humble + Gazebo Classic 11 | ✅ Hoàn thành |
| 1 | URDF robot 4WD + Gazebo launch + teleop | ✅ Hoàn thành |
| 2 | Localization: dual EKF + navsat_transform | ✅ Hoàn thành |
| 3 | Nav2 + Return-to-Home | ✅ Hoàn thành — `Successfully returned home!` |
| 4 | AI Obstacle Avoidance (YOLOv8) | ⬜ Chưa bắt đầu |
| 5 | Farm World + Integration Testing | ⬜ Chưa bắt đầu |

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

### 4WD — 2 diff_drive plugins (QUAN TRỌNG)
Robot dùng **2 plugin** `libgazebo_ros_diff_drive.so`:
- `drive_front`: điều khiển `front_left_wheel_joint` + `front_right_wheel_joint`
  - `publish_odom: true`, `publish_odom_tf: true`
- `drive_rear`: điều khiển `rear_left_wheel_joint` + `rear_right_wheel_joint`
  - `publish_odom: false`, `publish_odom_tf: false` (tránh duplicate)
- Cả 2 đều subscribe cùng topic `cmd_vel`

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

## Git commits Phase 3

```
d178015 fix: load custom BT XML directly from nav2_params
9ba6e52 fix: rename local EKF output to /odometry/local
b88f530 fix: delay spawn_entity by 10s to wait for Gazebo
64f3100 feat: true 4WD — add rear axle drive plugin
d3bb45a fix: add use_sim_time=true to all localization nodes
c0a6c84 fix: replace openni_kinect depth plugin
```
