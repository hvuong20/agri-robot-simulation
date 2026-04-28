# AI Obstacle Avoidance

## Tổng quan Pipeline

```
/camera/image_raw ──────────► YoloDetectorNode ──► /detected_objects
/camera/depth/image_raw ────►      │                    │
                                   │                    ▼
                              Depth Lookup      ObstaclePublisherNode
                                                        │
                                                        ▼
                                              /local_costmap/obstacles
                                                        │
                                                        ▼
                                                Nav2 DWB Planner
                                                (tự tránh vật cản)
```

## YoloDetectorNode

File: `agri_robot/scripts/ai_vision/yolo_detector.py`

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D, BoundingBox2D
from cv_bridge import CvBridge
from ultralytics import YOLO
import numpy as np

class YoloDetectorNode(Node):
    def __init__(self):
        super().__init__('yolo_detector_node')

        self.declare_parameter('model_path', 'yolov8n.pt')
        self.declare_parameter('confidence', 0.5)
        self.declare_parameter('target_classes', [0, 15, 16])
        # 0=person, 15=cat, 16=dog — các class cần tránh

        model_path = self.get_parameter('model_path').value
        self.conf = self.get_parameter('confidence').value
        self.target_classes = self.get_parameter('target_classes').value

        self.model = YOLO(model_path)
        self.bridge = CvBridge()

        self.image_sub = self.create_subscription(
            Image, '/camera/image_raw', self.image_callback, 10)

        self.detection_pub = self.create_publisher(
            Detection2DArray, '/detected_objects', 10)

        self.get_logger().info(f'YOLO model loaded: {model_path}')

    def image_callback(self, msg: Image):
        cv_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        results = self.model(cv_image, conf=self.conf, verbose=False)

        detections = Detection2DArray()
        detections.header = msg.header

        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in self.target_classes:
                    continue

                det = Detection2D()
                det.bbox.center.position.x = float(box.xywh[0][0])
                det.bbox.center.position.y = float(box.xywh[0][1])
                det.bbox.size_x = float(box.xywh[0][2])
                det.bbox.size_y = float(box.xywh[0][3])
                detections.detections.append(det)

        self.detection_pub.publish(detections)
```

## ObstaclePublisherNode

File: `agri_robot/scripts/ai_vision/obstacle_publisher.py`

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray
from nav_msgs.msg import OccupancyGrid
from cv_bridge import CvBridge
import numpy as np

class ObstaclePublisherNode(Node):
    """
    Nhận detection từ YOLO + depth image → tính vị trí 3D vật cản
    → Publish vào costmap để Nav2 tránh
    """
    def __init__(self):
        super().__init__('obstacle_publisher_node')

        self.declare_parameter('safety_radius', 1.0)  # m xung quanh vật cản
        self.declare_parameter('camera_fov_h', 1.047) # 60° horizontal FOV
        self.declare_parameter('camera_height', 0.5)  # chiều cao camera từ mặt đất

        self.bridge = CvBridge()
        self.latest_depth = None

        self.depth_sub = self.create_subscription(
            Image, '/camera/depth/image_raw', self._depth_cb, 10)
        self.detection_sub = self.create_subscription(
            Detection2DArray, '/detected_objects', self._detection_cb, 10)

        # Publish dạng PointCloud2 hoặc custom obstacle msg vào Nav2
        # (cụ thể implementation tùy Nav2 costmap plugin đang dùng)

    def _depth_cb(self, msg: Image):
        self.latest_depth = self.bridge.imgmsg_to_cv2(msg, '32FC1')

    def _detection_cb(self, msg: Detection2DArray):
        if self.latest_depth is None:
            return

        for det in msg.detections:
            # Lấy pixel center của bounding box
            cx = int(det.bbox.center.position.x)
            cy = int(det.bbox.center.position.y)

            # Lấy depth tại điểm center (đơn vị: m)
            depth = self.latest_depth[cy, cx]
            if np.isnan(depth) or depth <= 0:
                continue

            self.get_logger().info(f'Obstacle detected at {depth:.2f}m ahead')
            # → Publish vị trí vào Nav2 costmap
```

## Classes Phát hiện (COCO Dataset)

| Class ID | Tên | Ghi chú |
|---|---|---|
| 0 | person | Người đi lại trên đồng |
| 15 | cat | Mèo/thú nhỏ |
| 16 | dog | Chó |
| 17 | horse | Ngựa/gia súc lớn |
| 19 | cow | Bò |
| 20 | elephant | Voi (nếu relevant) |

Có thể fine-tune YOLOv8 với dataset nông nghiệp để phát hiện thêm:
- Máy móc nông nghiệp khác
- Hàng cây, rãnh tưới
- Người với trang phục bảo hộ

## Model Recommendations

| Model | Size | Speed (GPU) | mAP | Dùng khi |
|---|---|---|---|---|
| `yolov8n.pt` | 6 MB | ~45ms | 37.3 | Real-time, CPU only |
| `yolov8s.pt` | 22 MB | ~22ms | 44.9 | Cân bằng speed/accuracy |
| `yolov8m.pt` | 52 MB | ~36ms | 50.2 | GPU có VRAM ≥ 4GB |
| `yolov8l.pt` | 87 MB | ~56ms | 52.9 | GPU mạnh, độ chính xác cao |

**Khuyến nghị:** Bắt đầu với `yolov8n.pt` — sau đó upgrade nếu cần.

## Nav2 Costmap Integration

Để YOLO detections ảnh hưởng đến Nav2 path planning, thêm custom obstacle layer:

```yaml
# nav2_params.yaml — local_costmap section
local_costmap:
  local_costmap:
    ros__parameters:
      plugins: ["obstacle_layer", "yolo_obstacle_layer", "inflation_layer"]

      yolo_obstacle_layer:
        plugin: "nav2_costmap_2d::ObstacleLayer"
        observation_sources: yolo_obstacles
        yolo_obstacles:
          topic: /detected_obstacle_points  # PointCloud2 từ obstacle_publisher
          sensor_frame: camera_link
          observation_persistence: 0.5      # vật cản tồn tại 0.5s
          max_obstacle_height: 2.0
          clearing: true
          marking: true
```

## Thông số Safety

| Thông số | Giá trị | Ghi chú |
|---|---|---|
| Safety stop distance | 1.0 m | Dừng khẩn cấp nếu vật cản < 1m |
| Slow-down distance | 3.0 m | Giảm tốc khi vật cản < 3m |
| Obstacle persistence | 0.5 s | Giữ vật cản trong costmap 0.5s sau khi mất khỏi frame |
| Min confidence | 0.5 | Bỏ qua detection < 50% confidence |
