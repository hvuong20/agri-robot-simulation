import struct
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo, PointCloud2, PointField
from message_filters import ApproximateTimeSynchronizer, Subscriber
from cv_bridge import CvBridge

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# COCO class IDs that count as obstacles in an agricultural field
OBSTACLE_CLASSES = {
    0,           # person
    1, 2, 3, 5, 7,          # bicycle, car, motorcycle, bus, truck
    15, 16, 17, 18, 19, 20, # cat, dog, horse, sheep, cow, elephant
    21, 22, 23,              # bear, zebra, giraffe
}

MAX_DETECT_DIST = 5.0   # meters — ignore objects beyond this range
DEPTH_PATCH_HALF = 5    # pixels — median depth from this patch around bbox centre


class YoloObstacleNode(Node):
    def __init__(self):
        super().__init__('yolo_obstacle_node')

        self.bridge = CvBridge()
        self.camera_info = None
        self.model = None

        if YOLO_AVAILABLE:
            self.get_logger().info('Loading YOLOv8n model ...')
            self.model = YOLO('yolov8n.pt')
            self.get_logger().info('YOLOv8n ready.')
        else:
            self.get_logger().warn(
                'ultralytics not installed — obstacle detection disabled. '
                'Run: pip3 install ultralytics'
            )

        # Camera intrinsics
        self.create_subscription(CameraInfo, '/camera/camera_info',
                                 self._cam_info_cb, 1)

        # Synchronized RGB + depth (slop=0.1 s tolerates 10 Hz depth / 30 Hz RGB)
        rgb_sub   = Subscriber(self, Image, '/camera/image_raw')
        depth_sub = Subscriber(self, Image, '/camera/depth/image_raw')
        self._sync = ApproximateTimeSynchronizer(
            [rgb_sub, depth_sub], queue_size=5, slop=0.1)
        self._sync.registerCallback(self._images_cb)

        # Obstacle cloud consumed by Nav2 ObstacleLayer
        self._pc_pub = self.create_publisher(PointCloud2, '/yolo_obstacles', 10)

        self.get_logger().info('YoloObstacleNode started — listening on '
                               '/camera/image_raw + /camera/depth/image_raw')

    # ── callbacks ───────────────────────────────────────────────────────────

    def _cam_info_cb(self, msg: CameraInfo):
        self.camera_info = msg

    def _images_cb(self, rgb_msg: Image, depth_msg: Image):
        if self.camera_info is None or self.model is None:
            return

        rgb   = self.bridge.imgmsg_to_cv2(rgb_msg, 'bgr8')
        depth = self.bridge.imgmsg_to_cv2(depth_msg, '32FC1')

        fx = self.camera_info.k[0]
        fy = self.camera_info.k[4]
        cx = self.camera_info.k[2]
        cy = self.camera_info.k[5]

        obstacle_pts = []

        results = self.model(rgb, verbose=False, conf=0.4)
        for result in results:
            for box in result.boxes:
                if int(box.cls[0]) not in OBSTACLE_CLASSES:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                u = (x1 + x2) // 2
                v = (y1 + y2) // 2

                h, w = depth.shape
                patch = depth[
                    max(0, v - DEPTH_PATCH_HALF): min(h, v + DEPTH_PATCH_HALF),
                    max(0, u - DEPTH_PATCH_HALF): min(w, u + DEPTH_PATCH_HALF),
                ]
                valid = patch[np.isfinite(patch) & (patch > 0.1)]
                if len(valid) == 0:
                    continue

                d = float(np.median(valid))
                if d > MAX_DETECT_DIST:
                    continue

                # pixel → 3-D point in camera_optical_frame
                obs_x = (u - cx) * d / fx
                obs_y = (v - cy) * d / fy
                obs_z = d
                obstacle_pts.append((obs_x, obs_y, obs_z))

                label = result.names[int(box.cls[0])]
                self.get_logger().info(
                    f'Detected {label} at {d:.2f} m '
                    f'(camera frame x={obs_x:.2f} y={obs_y:.2f} z={obs_z:.2f})'
                )

        self._pc_pub.publish(
            self._make_pointcloud(obstacle_pts, rgb_msg.header)
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_pointcloud(self, points, header):
        msg = PointCloud2()
        msg.header = header
        msg.header.frame_id = 'camera_optical_frame'
        msg.height = 1
        msg.width = len(points)
        msg.fields = [
            PointField(name='x', offset=0,  datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4,  datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8,  datatype=PointField.FLOAT32, count=1),
        ]
        msg.is_bigendian = False
        msg.point_step = 12
        msg.row_step = 12 * len(points)
        msg.is_dense = True
        data = bytearray()
        for (x, y, z) in points:
            data += struct.pack('fff', x, y, z)
        msg.data = bytes(data)
        return msg


def main(args=None):
    rclpy.init(args=args)
    node = YoloObstacleNode()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
