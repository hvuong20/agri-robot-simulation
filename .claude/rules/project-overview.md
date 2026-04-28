# Agri Robot Simulation — Project Overview

**Agri Robot** là hệ thống mô phỏng robot nông nghiệp 4WD tự hành, được xây dựng bằng
ROS 2 + Gazebo trước khi build prototype phần cứng thực tế.

## Mục tiêu

| Tính năng | Mô tả |
|---|---|
| **4WD Skid-Steer** | 4 động cơ độc lập, điều khiển từng bánh riêng lẻ |
| **Return-to-Home** | Lưu GPS home khi khởi động, tự lái về sau khi hoàn thành nhiệm vụ |
| **AI Obstacle Avoidance** | Depth camera + YOLOv8 phát hiện người/vật cản → Nav2 tránh tự động |

## Tech Stack

| Layer | Công nghệ | Vai trò |
|---|---|---|
| OS (host) | **Windows 11** | Máy tính phát triển |
| OS (dev) | **WSL2 + Ubuntu 22.04** | Môi trường Linux chạy bên trong Windows |
| Middleware | **ROS 2 Humble** (LTS đến 2027) | Kết nối tất cả modules |
| Simulator | **Gazebo Classic 11** (v11.10.2) | Vật lý, sensor simulation |
| Navigation | **Nav2** | Path planning, return-to-home |
| Localization | **robot_localization** (EKF) | Fuse GPS + IMU → vị trí chính xác |
| AI / Vision | **YOLOv8** (Ultralytics) + **OpenCV** | Object detection từ camera |
| AI Backend | **PyTorch** 2.x | Runtime cho YOLOv8 |
| Visualization | **RViz2** | Debug robot, path, sensor data |
| Code Editor | **VS Code** + Remote WSL extension | Viết code từ Windows, chạy trong WSL2 |
| Language | **Python** 3.10+ | ROS 2 nodes (ưu tiên Python trước C++) |

> **Tại sao WSL2 thay vì ROS 2 native Windows?**
> ROS 2 có bản native Windows nhưng thiếu nhiều package, Gazebo không chạy tốt.
> WSL2 cho môi trường Linux đầy đủ bên trong Windows — tất cả tutorial và package đều hoạt động bình thường.

> **Gazebo Classic 11 vs Harmonic:** ROS 2 Humble trên Ubuntu 22.04 cài kèm Gazebo Classic 11 (không phải Harmonic).
> Dùng lệnh `gazebo` (không phải `gz sim`). Plugins dùng prefix `libgazebo_ros_*`.

## Sensors (Planned)

| Sensor | Model tham khảo | Dùng cho |
|---|---|---|
| Depth Camera | Intel RealSense D435 / ZED 2 | Object detection + distance |
| GPS/RTK-GPS | Ublox F9P (RTK) | Outdoor navigation, return-to-home |
| IMU | Built-in hoặc MPU-6050 | EKF fusion với GPS |

## File Structure

```
Agri_Robot_Simulation/
├── CLAUDE.md
├── .claude/
│   └── rules/              ← Tất cả quy tắc dự án
├── agri_robot/             ← ROS 2 package chính
│   ├── urdf/               ← Robot model (URDF/Xacro)
│   ├── config/             ← Nav2, EKF, controller params
│   ├── launch/             ← Launch files
│   ├── worlds/             ← Gazebo world files (.sdf)
│   └── scripts/            ← Python ROS 2 nodes
│       ├── navigation/     ← Waypoint nav, return-to-home
│       ├── ai_vision/      ← YOLOv8 obstacle detection
│       └── motor_control/  ← 4WD driver node
└── docs/                   ← Tài liệu, diagrams
```

## Môi trường hoạt động

- **Ngoài trời — đồng ruộng:** Địa hình gồ ghề, GPS-based navigation
- **Không cần SLAM** (không map trong nhà) — dùng GPS + IMU fusion là đủ
- **Tốc độ di chuyển:** 0.5–2.0 m/s (field robot, không cần nhanh)

## Out of Scope (v1)

- Tích hợp phần cứng thực tế (chỉ mô phỏng)
- Multi-robot coordination
- Camera thermal/NIR (chỉ RGB-D)
- Arm/manipulator (chỉ di chuyển)
- Cloud connectivity / remote control qua internet
