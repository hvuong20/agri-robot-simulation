# Agri Robot — Project Guide

Hệ thống robot nông nghiệp skid-steer tự hành (4 bánh, 2 motor). Gồm 2 phần:
- **Simulation** (Gazebo + ROS 2 + Nav2) — Phases 0–4, chạy trên WSL2
- **Real Hardware + App** (Raspberry Pi 3 + Flutter Android) — Phases A–F, đang triển khai

## Quy tắc bắt buộc

### Rule 1: Screenshot sau mỗi thay đổi lớn — Bắt buộc

Sau mỗi thay đổi lớn về UI (Flutter app), **phải**:
1. Chạy `flutter run` hoặc build APK
2. Chụp screenshot màn hình thực tế
3. So sánh với design gốc / màn hình trước thay đổi
4. Confirm không có regression trước khi commit

Áp dụng cho: mọi thay đổi file `*.dart` ảnh hưởng đến layout, màu sắc, widget mới.

---

## Memory & Context

| File | Nội dung | Load |
|---|---|---|
| `.claude/memory.md` | **Trạng thái thực tế, lỗi đã gặp, cấu hình thực tế** | **Always — đọc trước** |

## Rules Files

| File | Nội dung | Load |
|---|---|---|
| `project-overview.md` | Mô tả dự án, tech stack, file structure, mục tiêu | Always |
| `development-phases.md` | Phase breakdown, trạng thái hiện tại, bước tiếp theo | Always |
| `robot-architecture.md` | URDF structure, sensors, 2-motor skid-steer dual plugin | URDF/hardware files |
| `ros2-patterns.md` | Naming conventions, node patterns, topic/service/action | Tất cả ROS 2 files |
| `navigation-system.md` | Nav2, dual EKF, return-to-home, BT XML, waypoint nav | Navigation files |
| `ai-obstacle-avoidance.md` | YOLOv8, depth camera, costmap integration | AI/vision files |
| `simulation-workflow.md` | Gazebo setup, launch files, common errors & fixes | On request |

## Trạng thái nhanh (cập nhật 2026-04-30)

### Simulation (WSL2 + Gazebo)

| Phase | Nội dung | Status |
|---|---|---|
| 0 — Môi trường | WSL2 + ROS 2 Humble + Gazebo Classic 11 | ✅ Xong |
| 1 — URDF + Gazebo | Robot 4 bánh, teleop, sensors | ✅ Xong |
| 2 — Localization | Dual EKF + navsat_transform | ✅ Xong |
| 3 — Nav2 + Return-Home | `Successfully returned home!` | ✅ Xong |
| 4 — AI Obstacle Avoidance | Depth cam + YOLO node + Nav2 layer — code xong | 🔧 Cần test |
| 5 — Farm World + Testing | Chưa bắt đầu | ⬜ |

### Real Hardware + App (Raspberry Pi 3 + Flutter)

| Phase | Nội dung | Status |
|---|---|---|
| A — Hardware Drivers | RC interface + motor PWM + ESTOP guardian | ✅ Xong |
| B — Localization | EKF configs cho phần cứng (không sim_time) | ✅ Xong |
| C — Mode Manager + MQTT + App MVP | Flutter map + ESTOP button | ⬜ Tiếp theo |
| D — Boundary + Coverage | Boundary polygon + lawnmower | ⬜ |
| E — Follow Mode + Stuck Detection | GPS follow + stuck alert | ⬜ |
| F — Integration + Polish | Cloudflare Tunnel + full test | ⬜ |

## Packages

| Package | Đường dẫn | Mục đích |
|---|---|---|
| `agri_robot` | `agri_robot/` | Simulation (Gazebo, Nav2) |
| `agri_robot_hardware` | `agri_robot_hardware/` | Pi GPIO: RC, PWM motor, ESTOP |
| `agri_robot_control` | `agri_robot_control/` | Navigation, MQTT, mode manager |
| Flutter app | `agri_robot_app/` | Android app (Phase C — chưa tạo) |
