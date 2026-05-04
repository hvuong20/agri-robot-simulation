# Agri Robot — Project Overview

**Agri Robot** là hệ thống robot nông nghiệp 4WD tự hành. Dự án gồm 2 phần song song:
1. **Simulation** — Gazebo Classic 11 + ROS 2 + Nav2 (Phases 0–5, chạy trên WSL2)
2. **Real Hardware + Android App** — Raspberry Pi 3 + Flutter (Phases A–F, đang triển khai)

## Tech Stack — Simulation

| Layer | Công nghệ |
|---|---|
| OS | Windows 11 + WSL2 + Ubuntu 22.04 |
| Middleware | ROS 2 Humble |
| Simulator | Gazebo Classic 11 (v11.10.2) — dùng `gazebo`, KHÔNG dùng `gz sim` |
| Navigation | Nav2 (simulation only — không dùng trên Pi 3) |
| Localization | robot_localization (EKF) |
| AI / Vision | YOLOv8 (Ultralytics) + OpenCV + PyTorch |

## Tech Stack — Real Hardware

| Layer | Công nghệ |
|---|---|
| Robot computer | Raspberry Pi 3 (Ubuntu 22.04 Server 64-bit, 1GB RAM) |
| Middleware | ROS 2 Humble |
| Motors | 2 motor skid-steer (L298N H-bridge), 4 bánh |
| RC | 2.4GHz 10ch receiver (protocol: iBUS / SBUS / PPM — TBD) |
| GPS | u-blox module, UART |
| IMU | MPU6050 / 9250 |
| Connectivity | 5G + Cloudflare Tunnel (giải quyết CGNAT) |
| Navigation | Custom pure-pursuit GPS navigator (thay Nav2 — quá nặng cho Pi 3 1GB) |
| App | Flutter Android (OpenStreetMap, MQTT) |
| MQTT broker | Mosquitto self-hosted trên Pi |

## File Structure

```
Agri_Robot_Simulation/
├── CLAUDE.md
├── .claude/
│   ├── memory.md              ← Trạng thái thực tế, lỗi đã gặp — đọc mỗi session
│   └── rules/
├── agri_robot/                ← Simulation package (Gazebo + Nav2)
│   ├── urdf/
│   ├── config/
│   ├── launch/
│   ├── worlds/
│   └── agri_robot/
│       ├── navigation/        ← return_home.py
│       └── ai_vision/         ← yolo_obstacle_node.py
├── agri_robot_hardware/       ← Pi hardware drivers
│   ├── agri_robot_hardware/
│   │   ├── rc_interface_node.py
│   │   ├── motor_driver_node.py
│   │   └── drivers/
│   │       ├── rc_protocol.py    ← iBUS/SBUS/PPM/Mock
│   │       └── pwm_motor.py      ← L298N/Mock
│   ├── config/
│   │   └── hardware_params.yaml  ← GPIO pins, RC channels (set mock → l298n/ibus on Pi)
│   └── launch/
│       └── hardware.launch.py
├── agri_robot_control/        ← Navigation + app bridge
│   ├── agri_robot_control/
│   │   ├── mode_manager_node.py       ← MANUAL/AUTO/FOLLOW/ESTOP state machine
│   │   ├── boundary_manager_node.py   ← GPS polygon, enforcement
│   │   ├── coverage_planner_node.py   ← Boustrophedon lawnmower path
│   │   ├── gps_navigator_node.py      ← Pure-pursuit GPS waypoint follower
│   │   ├── follow_mode_node.py        ← Phone-GPS follow mode
│   │   ├── mqtt_bridge_node.py        ← MQTT ↔ ROS 2 bidirectional bridge
│   │   └── stuck_detector_node.py     ← Two-layer stuck detection
│   ├── config/
│   │   ├── control_params.yaml
│   │   ├── ekf_local.yaml    ← Copy từ sim, use_sim_time removed
│   │   ├── ekf_global.yaml
│   │   ├── navsat.yaml       ← Update datum_lat/lon cho field thực tế
│   │   ├── twist_mux.yaml    ← /cmd_vel_teleop(p20) + /cmd_vel_auto(p5)
│   │   └── mqtt_config.yaml
│   └── launch/
│       ├── localization.launch.py
│       ├── navigation.launch.py
│       └── full_system.launch.py   ← Single command bringup
└── agri_robot_app/            ← Flutter Android app (Phase C — chưa tạo)
```

## MQTT Topics

| Topic | Hướng | Nội dung | QoS |
|---|---|---|---|
| `robot/position` | Pi → App | `{lat, lon, heading_deg, mode}` | 0 |
| `robot/status`   | Pi → App | `{mode, gps_fix, stuck, boundary, ...}` | 1 |
| `robot/path`     | Pi → App | `[{lat,lon}, ...]` coverage waypoints | 0 |
| `app/command`    | App → Pi | `{type: "mode_set\|goto", mode: "..."}` | 1 |
| `app/estop`      | App → Pi | `{}` — immediate | 2 |
| `app/boundary`   | App → Pi | `[{lat,lon}, ...]` polygon | 1 |
| `app/follow_position` | App → Pi | `{lat, lon}` phone GPS, 5 Hz | 0 |
| `app/coverage_config` | App → Pi | `{row_offset, speed}` | 1 |

## Critical Notes

1. **ESTOP guardian** tại `motor_driver_node` — không phải twist_mux. GPIO bị brake trực tiếp.
2. **Pi 3 RAM**: 600MB budget. KHÔNG chạy Nav2. 5 Python processes ~80MB + robot_localization ~50MB + OS ~200MB.
3. **`/dev/serial0` bị Bluetooth** chiếm trên Pi 3: phải `dtoverlay=disable-bt` trong `/boot/config.txt`.
4. **5G CGNAT**: App không kết nối trực tiếp được. Dùng Cloudflare Tunnel qua `cloudflared`.
5. **GPS datum**: Cập nhật `navsat.yaml` datum_lat/lon cho field thực tế trước khi deploy.
6. **Heading**: Dùng EKF yaw từ `/odometry/global`, KHÔNG dùng GPS track direction (không tin cậy < 0.2 m/s).
7. **hardware_params.yaml**: Mặc định `mock` — đổi thành `l298n`/`ibus` khi deploy lên Pi.

## Gazebo Classic Notes

- Dùng `gazebo` (không phải `gz sim`) — Gazebo Classic 11, KHÔNG phải Harmonic
- Plugins dùng prefix `libgazebo_ros_*`
- `ros2 --version` không tồn tại — dùng `echo $ROS_DISTRO`
- Không thể start Gazebo từ Bash tool (cần DISPLAY) — phải start thủ công từ WSL2 terminal

## Out of Scope (v1)

- Multi-robot coordination
- Camera thermal/NIR
- Arm/manipulator
- SLAM (dùng GPS outdoor)
- Nav2 trên Pi 3 (quá nặng — dùng custom pure-pursuit)
