# Agri Robot Simulation — Project Guide

Hệ thống mô phỏng robot nông nghiệp skid-steer tự hành (4 bánh, 2 motor). Rules được tổ chức trong `.claude/rules/`.

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

## Trạng thái nhanh (cập nhật 2026-04-29)

| Phase | Status |
|---|---|
| 0 — Môi trường | ✅ Xong |
| 1 — URDF + Gazebo | ✅ Xong |
| 2 — Localization | ✅ Xong |
| 3 — Nav2 + Return-Home | ✅ Xong — `Successfully returned home!` |
| 4 — AI Obstacle Avoidance | ⬜ Chưa bắt đầu |
| 5 — Farm World + Testing | ⬜ Chưa bắt đầu |
