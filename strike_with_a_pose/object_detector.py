import cv2
import moderngl
import numpy as np
import os
import pkg_resources
import urllib

from PIL import Image
from PyQt5.QtWidgets import QPushButton

YOLO_CLASSES = pkg_resources.resource_filename("strike_with_a_pose", "data/yolov3.txt")
YOLO_WEIGHTS = pkg_resources.resource_filename(
    "strike_with_a_pose", "data/yolov3.weights"
)
YOLO_CONFIG = pkg_resources.resource_filename("strike_with_a_pose", "data/yolov3.cfg")
YOLO_CLASSES_F = "yolo_classes.png"
SCENE_DIR = pkg_resources.resource_filename("strike_with_a_pose", "scene_files/")


class ObjectDetector:
    def __init__(self):
        self.classes = open(YOLO_CLASSES, "r").readlines()
        classes_num = len(self.classes)

        self.yolo_rgbs = np.random.uniform(0, 255, size=(classes_num, 3)) / 255.0

        if not os.path.isfile(YOLO_WEIGHTS):
            print("Downloading YOLOv3 weights...")
            url = "https://pjreddie.com/media/files/yolov3.weights"
            urllib.request.urlretrieve(url, YOLO_WEIGHTS)

        self.net = cv2.dnn.readNet(YOLO_WEIGHTS, YOLO_CONFIG)
        layer_names = self.net.getLayerNames()
        self.yolo_output_layers = [
            layer_names[i[0] - 1] for i in self.net.getUnconnectedOutLayers()
        ]

    @staticmethod
    def get_gui_comps():
        # Detect button.
        detect = QPushButton("Detect")
        # Order matters. Prediction button must be named "predict" in tuple.
        return [("predict", detect)]

    def init_scene_comps(self):
        yolo_classes_f = "{0}{1}".format(SCENE_DIR, YOLO_CLASSES_F)
        yolo_classes_img = (
            Image.open(yolo_classes_f).transpose(Image.FLIP_TOP_BOTTOM).convert("RGBA")
        )
        self.YOLO_LABELS = self.CTX.texture(
            yolo_classes_img.size, 4, yolo_classes_img.tobytes()
        )
        self.YOLO_LABELS.build_mipmaps()

        self.YOLO_BOX_VBOS = []
        self.YOLO_BOX_VAOS = []
        self.YOLO_LABEL_VBOS = []
        self.YOLO_LABEL_VAOS = []

    def predict(self, image):
        boxes = []
        class_ids = []

        bboxes = []
        confidences = []
        conf_threshold = 0.5
        nms_threshold = 0.4

        image = np.array(image)
        width = image.shape[1]
        height = image.shape[0]
        scale = 0.00392

        # Magic number.
        yolo_size = (416, 416)
        blob = cv2.dnn.blobFromImage(
            image, scale, yolo_size, (0, 0, 0), True, crop=False
        )
        self.net.setInput(blob)
        outs = self.net.forward(self.yolo_output_layers)

        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                if confidence > conf_threshold:
                    orig_center_x = int(detection[0] * width)
                    orig_center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)
                    x = orig_center_x - w / 2
                    y = orig_center_y - h / 2
                    bboxes.append([x, y, w, h])

                    center_x = detection[0] * 2 - 1
                    center_y = 1 - detection[1] * 2
                    half_w = detection[2]
                    half_h = detection[3]

                    class_ids.append(class_id)
                    confidences.append(float(confidence))
                    boxes.append(
                        np.array(
                            [
                                [center_x - half_w, center_y + half_h],
                                [center_x + half_w, center_y + half_h],
                                [center_x - half_w, center_y + half_h],
                                [center_x - half_w, center_y - half_h],
                                [center_x + half_w, center_y + half_h],
                                [center_x + half_w, center_y - half_h],
                                [center_x + half_w, center_y - half_h],
                                [center_x - half_w, center_y - half_h],
                            ]
                        )
                    )

        return self.create_box_and_label_arrays(
            cv2.dnn.NMSBoxes(bboxes, confidences, conf_threshold, nms_threshold),
            class_ids,
            boxes,
        )

    def create_box_and_label_arrays(self, indices, class_ids, boxes):
        box_arrays = []
        label_arrays = []
        box_rgbs = []
        for index in indices:

            idx = index[0]
            class_id = class_ids[idx]
            box = boxes[idx]
            classes_per_col = 20
            row_num = class_id % classes_per_col
            col_num = int(class_id / classes_per_col)
            box_x = box[0][0]
            box_y = box[0][1]

            box_array = np.zeros((8, 8))
            box_array[:, :2] = box
            box_arrays.append(box_array)
            label_length = len(self.classes[class_id]) / 15.0

            vertices_yolo = np.array(
                [
                    [box_x, box_y, 0.0],
                    [box_x, box_y - 0.1, 0.0],
                    [box_x + 0.5 * label_length, box_y, 0.0],
                    [box_x + 0.5 * label_length, box_y - 0.1, 0.0],
                    [box_x + 0.5 * label_length, box_y, 0.0],
                    [box_x, box_y - 0.1, 0.0],
                ]
            )

            normals = np.repeat([[0.0, 0.0, 1.0]], len(vertices_yolo), axis=0)

            label_height_pix = 48.96
            img_size_pix = 1024
            num_cols = 4

            yolo_coords = np.array(
                [
                    [
                        col_num / num_cols,
                        1.0 - row_num * (label_height_pix / img_size_pix),
                    ],
                    [
                        col_num / num_cols,
                        1.0
                        - (row_num + 1) * (label_height_pix / img_size_pix)
                        + 1.0 / img_size_pix,
                    ],
                    [
                        (col_num + 1) / num_cols * label_length,
                        1.0 - row_num * (label_height_pix / img_size_pix),
                    ],
                    [
                        (col_num + 1) / num_cols * label_length,
                        1.0
                        - (row_num + 1) * (label_height_pix / img_size_pix)
                        + 1.0 / img_size_pix,
                    ],
                    [
                        (col_num + 1) / num_cols * label_length,
                        1.0 - row_num * (label_height_pix / img_size_pix),
                    ],
                    [
                        col_num / num_cols,
                        1.0
                        - (row_num + 1) * (label_height_pix / img_size_pix)
                        + 1.0 / img_size_pix,
                    ],
                ]
            )
            label_array = np.hstack((vertices_yolo, normals, yolo_coords))
            label_arrays.append(label_array)

            box_rgbs.append(self.yolo_rgbs[class_id])

        self.add_boxes_and_labels(box_arrays, label_arrays, box_rgbs)

    def add_boxes_and_labels(self, box_arrays, label_arrays, box_rgbs):
        self.BOX_RGBS = box_rgbs
        for i in range(len(box_arrays)):
            box_array = box_arrays[i]
            box_vbo = self.CTX.buffer(box_array.astype("f4").tobytes())
            box_vao = self.CTX.simple_vertex_array(
                self.PROG, box_vbo, "in_vert", "in_norm", "in_text"
            )
            self.YOLO_BOX_VBOS.append(box_vbo)
            self.YOLO_BOX_VAOS.append(box_vao)

            label_array = label_arrays[i]
            label_vbo = self.CTX.buffer(label_array.flatten().astype("f4").tobytes())
            label_vao = self.CTX.simple_vertex_array(
                self.PROG, label_vbo, "in_vert", "in_norm", "in_text"
            )
            self.YOLO_LABEL_VBOS.append(label_vbo)
            self.YOLO_LABEL_VAOS.append(label_vao)

    def render(self):
        for i in range(len(self.YOLO_BOX_VAOS)):
            self.CTX.disable(moderngl.DEPTH_TEST)
            self.PROG["mode"].value = 2
            self.PROG["box_rgb"].value = tuple(self.BOX_RGBS[i])
            self.YOLO_BOX_VAOS[i].render(moderngl.LINES)

            self.PROG["mode"].value = 1
            self.YOLO_LABELS.use()
            self.YOLO_LABEL_VAOS[i].render()
            self.CTX.enable(moderngl.DEPTH_TEST)
            self.PROG["mode"].value = 0

    def clear(self):
        for i in range(len(self.YOLO_BOX_VAOS)):
            self.YOLO_BOX_VBOS[i].release()
            self.YOLO_BOX_VAOS[i].release()
            self.YOLO_LABEL_VBOS[i].release()
            self.YOLO_LABEL_VAOS[i].release()

        self.YOLO_BOX_VBOS = []
        self.YOLO_BOX_VAOS = []

        self.YOLO_LABEL_VBOS = []
        self.YOLO_LABEL_VAOS = []
