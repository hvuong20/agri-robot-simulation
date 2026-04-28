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

## Thông số Robot (Thực tế trong URDF — đã xây dựng)

| Thông số | Giá trị |
|---|---|
| Chiều dài chassis | 0.80 m |
| Chiều rộng chassis | 0.55 m |
| Chiều cao chassis | 0.20 m |
| Đường kính bánh | 0.20 m (bán kính 0.10 m) |
| Bề rộng bánh | 0.08 m |
| Khối lượng (simulate) | 20 kg chassis + 2 kg mỗi bánh |
| Track width (wheel_separation) | 0.62 m |
| Footprint radius (Nav2) | 0.50 m |
| Tốc độ tối đa | 1.5 m/s linear, 1.0 rad/s angular |

## 4WD Skid-Steer Configuration (Gazebo Classic)

**Nguyên lý:** Điều khiển tốc độ 2 bên trái/phải khác nhau để quay.
- Rẽ trái: bánh phải quay nhanh hơn bánh trái
- Rẽ phải: bánh trái quay nhanh hơn bánh phải
- Quay tại chỗ: 2 bên quay ngược chiều nhau

**Triển khai thực tế — 2 plugin diff_drive:**

Gazebo Classic `libgazebo_ros_diff_drive.so` chỉ điều khiển được 2 bánh (1 trái + 1 phải).
Để có true 4WD, dùng **2 plugin riêng biệt**:

```xml
<!-- Plugin 1: Front axle — publish odom và TF -->
<plugin name="drive_front" filename="libgazebo_ros_diff_drive.so">
  <left_joint>front_left_wheel_joint</left_joint>
  <right_joint>front_right_wheel_joint</right_joint>
  <wheel_separation>0.62</wheel_separation>
  <wheel_diameter>0.20</wheel_diameter>
  <command_topic>cmd_vel</command_topic>
  <publish_odom>true</publish_odom>
  <publish_odom_tf>true</publish_odom_tf>
  <robot_base_frame>base_footprint</robot_base_frame>
</plugin>

<!-- Plugin 2: Rear axle — KHÔNG publish odom (tránh duplicate) -->
<plugin name="drive_rear" filename="libgazebo_ros_diff_drive.so">
  <left_joint>rear_left_wheel_joint</left_joint>
  <right_joint>rear_right_wheel_joint</right_joint>
  <wheel_separation>0.62</wheel_separation>
  <wheel_diameter>0.20</wheel_diameter>
  <command_topic>cmd_vel</command_topic>   <!-- cùng topic với front -->
  <publish_odom>false</publish_odom>
  <publish_odom_tf>false</publish_odom_tf>
</plugin>
```

**Kết quả:** Cả 4 bánh đều quay đồng bộ theo `/cmd_vel`. `/odom` chỉ được publish 1 lần (từ front plugin).

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
