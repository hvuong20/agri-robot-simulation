# Robot Architecture

## Tổng quan cơ học

Robot nông nghiệp 4WD kiểu XAG — 4 bánh to dẫn động độc lập, skid-steer steering.

```
       [FL]─────────────────[FR]
         │      Chassis      │
         │  ┌─────────────┐  │
         │  │ Depth Camera│  │
         │  │   (front)   │  │
         │  │             │  │
         │  │  GPS/IMU    │  │
         │  │  (center)   │  │
         │  └─────────────┘  │
       [RL]─────────────────[RR]
```

## URDF Structure

File: `agri_robot/urdf/agri_robot.urdf.xacro`

```
base_link
  ├── chassis_link          (visual: box, collision: box)
  ├── front_left_wheel      (joint: continuous, axis: y)
  ├── front_right_wheel     (joint: continuous, axis: y)
  ├── rear_left_wheel       (joint: continuous, axis: y)
  ├── rear_right_wheel      (joint: continuous, axis: y)
  ├── camera_link           (joint: fixed, trên đầu chassis)
  │   └── camera_optical_frame
  ├── gps_link              (joint: fixed, trên chassis)
  └── imu_link              (joint: fixed, center chassis)
```

## Thông số Robot (Tham khảo XAG R80)

| Thông số | Giá trị |
|---|---|
| Chiều dài chassis | 1.2 m |
| Chiều rộng chassis | 0.9 m |
| Chiều cao (không payload) | 0.5 m |
| Đường kính bánh | 0.35 m |
| Khối lượng (simulate) | 80 kg |
| Wheelbase | 0.85 m |
| Track width | 0.9 m |
| Tốc độ tối đa | 2.0 m/s |

## 4WD Skid-Steer Configuration

**Nguyên lý:** Điều khiển tốc độ 2 bên trái/phải khác nhau để quay.
- Rẽ trái: bánh phải quay nhanh hơn bánh trái
- Rẽ phải: bánh trái quay nhanh hơn bánh phải
- Quay tại chỗ: 2 bên quay ngược chiều nhau

**ROS 2 Controller (`controllers.yaml`):**
```yaml
controller_manager:
  ros__parameters:
    update_rate: 50

agri_robot_controller:
  ros__parameters:
    type: diff_drive_controller/DiffDriveController
    left_wheel_names:  ["front_left_wheel_joint",  "rear_left_wheel_joint"]
    right_wheel_names: ["front_right_wheel_joint", "rear_right_wheel_joint"]
    wheel_separation: 0.9       # track width (m)
    wheel_radius:     0.175     # bán kính bánh (m)
    publish_rate: 50.0
    cmd_vel_topic: /cmd_vel
    odom_frame_id: odom
    base_frame_id: base_link
```

## Sensor Configuration

### Depth Camera
```xml
<!-- URDF Gazebo plugin -->
<gazebo reference="camera_link">
  <sensor type="depth" name="depth_camera">
    <update_rate>30</update_rate>
    <camera>
      <horizontal_fov>1.047</horizontal_fov>  <!-- 60° FOV -->
      <image>
        <width>640</width>
        <height>480</height>
        <format>R8G8B8</format>
      </image>
      <clip><near>0.1</near><far>10.0</far></clip>
    </camera>
    <plugin name="camera_plugin" filename="libgazebo_ros_camera.so">
      <ros><namespace>/camera</namespace></ros>
      <camera_name>depth_camera</camera_name>
      <frame_name>camera_optical_frame</frame_name>
    </plugin>
  </sensor>
</gazebo>
<!-- Topics output: /camera/image_raw, /camera/depth/image_raw, /camera/points -->
```

### GPS Plugin
```xml
<gazebo reference="gps_link">
  <sensor type="gps" name="gps_sensor">
    <update_rate>10</update_rate>
    <plugin name="gps_plugin" filename="libgazebo_ros_gps_sensor.so">
      <ros><namespace>/gps</namespace></ros>
      <frame_name>gps_link</frame_name>
    </plugin>
  </sensor>
</gazebo>
<!-- Topic output: /gps/fix (sensor_msgs/NavSatFix) -->
```

### IMU Plugin
```xml
<gazebo reference="imu_link">
  <sensor type="imu" name="imu_sensor">
    <update_rate>100</update_rate>
    <plugin name="imu_plugin" filename="libgazebo_ros_imu_sensor.so">
      <ros><namespace>/imu</namespace></ros>
      <frame_name>imu_link</frame_name>
    </plugin>
  </sensor>
</gazebo>
<!-- Topic output: /imu/data (sensor_msgs/Imu) -->
```

## ROS 2 Topics Published by Robot

| Topic | Type | Source |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | Input — Nav2/teleop gửi vào |
| `/odom` | `nav_msgs/Odometry` | diff_drive_controller |
| `/camera/image_raw` | `sensor_msgs/Image` | Depth camera plugin |
| `/camera/depth/image_raw` | `sensor_msgs/Image` | Depth camera plugin |
| `/camera/points` | `sensor_msgs/PointCloud2` | Depth camera plugin |
| `/gps/fix` | `sensor_msgs/NavSatFix` | GPS plugin |
| `/imu/data` | `sensor_msgs/Imu` | IMU plugin |
| `/joint_states` | `sensor_msgs/JointState` | ros2_control |
