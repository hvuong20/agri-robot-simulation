# Agri Robot — Project Guide

Hệ thống robot nông nghiệp skid-steer tự hành (4 bánh, 2 motor). Gồm 2 phần:
- **Simulation** (Gazebo + ROS 2 + Nav2) — Phases 0–4, chạy trên WSL2
- **Real Hardware + App** (Raspberry Pi 3 + Flutter Android) — Phases A–F, code xong, chờ phần cứng

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

## Trạng thái nhanh (cập nhật 2026-05-06)

### Simulation (WSL2 + Gazebo)

| Phase | Nội dung | Status |
|---|---|---|
| 0 — Môi trường | WSL2 + ROS 2 Humble + Gazebo Classic 11 | ✅ Xong |
| 1 — URDF + Gazebo | Robot 4 bánh, teleop, sensors | ✅ Xong |
| 2 — Localization | Dual EKF + navsat_transform | ✅ Xong |
| 3 — Nav2 + Return-Home | `Successfully returned home!` | ✅ Xong |
| 4 — AI Obstacle Avoidance | Depth cam + YOLO node + Nav2 layer — code xong | 🔧 Cần test Gazebo |
| 5 — Farm World + Testing | Chưa bắt đầu | ⬜ |

### Real Hardware + App (Raspberry Pi 3 + Flutter)

| Phase | Nội dung | Status |
|---|---|---|
| A — Hardware Drivers | RC interface + motor PWM + ESTOP guardian | ✅ Xong |
| B — Localization | EKF configs cho phần cứng (không sim_time) | ✅ Xong |
| C — Mode Manager + MQTT + App MVP | Flutter map + ESTOP button | ✅ Xong |
| D — Boundary + Coverage | Boundary polygon + lawnmower | ✅ Xong |
| E — Follow Mode + Stuck Detection | GPS follow + stuck alert | ✅ Xong |
| F — Integration + Polish | Battery monitor + Cloudflare Tunnel + APK | ✅ Code xong — cần Pi 3 để test |

### Flutter & Build Tools (Windows)

| Item | Trạng thái | Path |
|---|---|---|
| Flutter SDK 3.38.9 | ✅ Cài xong | `C:\flutter\flutter` |
| Android SDK (android-36) | ✅ Cài xong | `C:\Android\android-sdk` |
| Java 17 (Temurin) | ✅ Cài xong | `C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot` |
| APK release build | ✅ 48.3 MB | `agri_robot_app\build\app\outputs\flutter-apk\app-release.apk` |
| GitHub repo | ✅ Public | https://github.com/hvuong20/agri-robot-simulation |

## Packages

| Package | Đường dẫn | Mục đích |
|---|---|---|
| `agri_robot` | `agri_robot/` | Simulation (Gazebo, Nav2) |
| `agri_robot_hardware` | `agri_robot_hardware/` | Pi GPIO: RC, PWM motor, ESTOP, battery |
| `agri_robot_control` | `agri_robot_control/` | Navigation, MQTT, mode manager |
| Flutter app | `agri_robot_app/` | Android app ✅ APK built |

## Quyết định kỹ thuật đã chốt

| Vấn đề | Quyết định | Lý do |
|---|---|---|
| Navigation stack | Custom pure pursuit thay Nav2 | Nav2 quá nặng cho Pi 3 1GB RAM |
| MQTT broker | Mosquitto self-hosted trên Pi | Không phụ thuộc cloud |
| Remote access | Cloudflare Tunnel (`cloudflared`) | Giải quyết 5G CGNAT |
| Map | OpenStreetMap via `flutter_map` | Miễn phí, không cần API key |
| RC transmitter | FlySky FS-i6 (6 kênh) đủ dùng | CH7 mất nhưng boundary editor trên app thay thế |
| Motor (payload 180kg) | 48V DC 500W + Cytron MD60C 60A | L298N max 2A không đủ |
| Pin (payload 180kg) | LiFePO4 48V 20Ah + BMS 30A | An toàn hơn LiPo cho robot nặng |

## Build APK (lần sau)

```powershell
$env:JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot"
$env:ANDROID_HOME="C:\Android\android-sdk"
$env:Path="C:\flutter\flutter\bin;$env:JAVA_HOME\bin;" + $env:Path
cd C:\Claude_project\Agri_Robot_Simulation\agri_robot_app
flutter build apk --release
```

## Việc còn lại (cần phần cứng Pi 3)

- [ ] Update `navsat.yaml` datum_lat/datum_lon cho field thực tế
- [ ] Chạy `setup_cloudflare_tunnel.sh` trên Pi
- [ ] Đổi `hardware_params.yaml`: `protocol: ibus`, `motor.driver: l298n`, `battery.driver: ads1115`
- [ ] Tune `nav.kp_angular` cho pure pursuit thực tế
- [ ] Full system test: RC manual → AUTO → FOLLOW → ESTOP
