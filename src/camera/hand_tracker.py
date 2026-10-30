"""
MediaPipe Hand Landmarker Tracking Engine for GESTUREDRIVE X.
Tracks two hands independently, normalizes handedness with mirroring compensation,
stabilizes landmarks with temporal filtering, and provides racing-styled visualization.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from src.utils.logger import logger


@dataclass
class HandData:
    """Encapsulates tracking data for a single hand."""
    handedness: str  # "Left" or "Right" (corrected for camera mirroring)
    landmarks: np.ndarray  # (21, 3) normalized coordinates [0..1]
    pixel_landmarks: np.ndarray  # (21, 2) pixel coordinates
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x_min, y_min, width, height)
    wrist_px: Tuple[int, int]
    index_tip_px: Tuple[int, int]
    thumb_tip_px: Tuple[int, int]


@dataclass
class FrameHandResult:
    """Results of hand tracking for a single processed frame."""
    left_hand: Optional[HandData] = None
    right_hand: Optional[HandData] = None
    annotated_frame: Optional[np.ndarray] = None
    timestamp: float = 0.0

    @property
    def both_hands_detected(self) -> bool:
        return self.left_hand is not None and self.right_hand is not None

    @property
    def any_hand_detected(self) -> bool:
        return self.left_hand is not None or self.right_hand is not None


class HandTracker:
    """High-performance two-hand tracker using Google MediaPipe Hand Landmarker Task."""

    # Hand landmark indices
    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_PIP = 6
    INDEX_DIP = 7
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_PIP = 14
    RING_DIP = 15
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20

    # Skeleton connections
    CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
        (0, 5), (5, 6), (6, 7), (7, 8),        # Index
        (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
        (9, 13), (13, 14), (14, 15), (15, 16), # Ring
        (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
        (0, 17)                                # Palm base
    ]

    def __init__(
        self,
        model_path: str = "assets/models/hand_landmarker.task",
        min_detection_confidence: float = 0.55,
        min_tracking_confidence: float = 0.50,
        max_num_hands: int = 2,
        smoothing_alpha: float = 0.85,
        mirrored: bool = True
    ):
        self.model_path = model_path
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.max_num_hands = max_num_hands
        self.smoothing_alpha = smoothing_alpha
        self.mirrored = mirrored

        if not os.path.isabs(self.model_path):
            # Resolve relative to project root
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.model_path = os.path.join(base_dir, self.model_path)

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"MediaPipe Hand Landmarker model not found at {self.model_path}")

        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=self.max_num_hands,
            min_hand_detection_confidence=self.min_detection_confidence,
            min_hand_presence_confidence=self.min_tracking_confidence,
            min_tracking_confidence=self.min_tracking_confidence
        )

        self._detector = vision.HandLandmarker.create_from_options(options)
        self._previous_landmarks: Dict[str, np.ndarray] = {}
        logger.info(f"HandTracker initialized with model {self.model_path} (max_hands={max_num_hands})")

    def process_frame(self, frame: np.ndarray, timestamp: float = 0.0) -> FrameHandResult:
        """
        Executes MediaPipe inference on the input BGR frame.
        Applies mirroring correction, smoothing, and landmark extraction.
        """
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        results = self._detector.detect(mp_image)

        left_hand_data: Optional[HandData] = None
        right_hand_data: Optional[HandData] = None

        detected_hands: List[HandData] = []

        if results.hand_landmarks and results.handedness:
            for hand_landmarks, handedness_categories in zip(
                results.hand_landmarks, results.handedness
            ):
                cat = handedness_categories[0]
                raw_label = cat.category_name or cat.display_name
                confidence = float(cat.score)

                # In mirrored mode, MediaPipe's "Left" is the user's physical "Right" hand and vice versa
                if self.mirrored:
                    corrected_label = "Right" if raw_label == "Left" else "Left"
                else:
                    corrected_label = raw_label

                # Extract normalized coordinates (21, 3)
                raw_coords = np.array(
                    [[lm.x, lm.y, lm.z] for lm in hand_landmarks],
                    dtype=np.float32
                )

                # Pixel coordinates
                pixel_coords = np.zeros((21, 2), dtype=np.int32)
                pixel_coords[:, 0] = np.clip(raw_coords[:, 0] * w, 0, w - 1).astype(np.int32)
                pixel_coords[:, 1] = np.clip(raw_coords[:, 1] * h, 0, h - 1).astype(np.int32)

                # Compute Bounding Box
                x_min = int(np.min(pixel_coords[:, 0]))
                y_min = int(np.min(pixel_coords[:, 1]))
                x_max = int(np.max(pixel_coords[:, 0]))
                y_max = int(np.max(pixel_coords[:, 1]))
                bbox = (x_min, y_min, x_max - x_min, y_max - y_min)

                hand_obj = HandData(
                    handedness=corrected_label,
                    landmarks=raw_coords,
                    pixel_landmarks=pixel_coords,
                    confidence=confidence,
                    bbox=bbox,
                    wrist_px=(pixel_coords[0, 0], pixel_coords[0, 1]),
                    index_tip_px=(pixel_coords[8, 0], pixel_coords[8, 1]),
                    thumb_tip_px=(pixel_coords[4, 0], pixel_coords[4, 1]),
                )
                detected_hands.append(hand_obj)

        # Spatial sorting: In steering position, Left Hand is ALWAYS on the left (smaller X),
        # and Right Hand is ALWAYS on the right (larger X). This permanently prevents
        # MediaPipe from misclassifying clenched fists as the same hand!
        if len(detected_hands) >= 2:
            # Sort by horizontal center position
            detected_hands.sort(key=lambda h_data: h_data.bbox[0] + h_data.bbox[2] / 2.0)
            left_hand_data = detected_hands[0]
            left_hand_data.handedness = "Left"

            right_hand_data = detected_hands[1]
            right_hand_data.handedness = "Right"
        elif len(detected_hands) == 1:
            h_data = detected_hands[0]
            center_x = h_data.bbox[0] + h_data.bbox[2] / 2.0
            if center_x < w / 2.0:
                h_data.handedness = "Left"
                left_hand_data = h_data
            else:
                h_data.handedness = "Right"
                right_hand_data = h_data

        # Apply temporal smoothing with correct spatial labels
        for hand_data in [left_hand_data, right_hand_data]:
            if hand_data is not None:
                lbl = hand_data.handedness
                if lbl in self._previous_landmarks:
                    prev = self._previous_landmarks[lbl]
                    hand_data.landmarks = self.smoothing_alpha * hand_data.landmarks + (1.0 - self.smoothing_alpha) * prev
                    hand_data.pixel_landmarks[:, 0] = np.clip(hand_data.landmarks[:, 0] * w, 0, w - 1).astype(np.int32)
                    hand_data.pixel_landmarks[:, 1] = np.clip(hand_data.landmarks[:, 1] * h, 0, h - 1).astype(np.int32)
                self._previous_landmarks[lbl] = hand_data.landmarks

        # Clear smoothing buffer for hands not seen in current frame
        active_labels = []
        if left_hand_data:
            active_labels.append("Left")
        if right_hand_data:
            active_labels.append("Right")
        for stored_label in list(self._previous_landmarks.keys()):
            if stored_label not in active_labels:
                del self._previous_landmarks[stored_label]

        return FrameHandResult(
            left_hand=left_hand_data,
            right_hand=right_hand_data,
            annotated_frame=None,
            timestamp=timestamp
        )

    def draw_landmarks(
        self,
        frame: np.ndarray,
        hand_result: FrameHandResult,
        steering_wheel_active: bool = False
    ) -> np.ndarray:
        """
        Renders racing-styled visual overlays on top of the webcam frame.
        """
        output = frame.copy()

        # Draw steering wheel axle line if steering is active
        if hand_result.both_hands_detected and steering_wheel_active:
            palm_indices = [0, 5, 9, 13, 17]
            p1_x = int(np.mean(hand_result.left_hand.pixel_landmarks[palm_indices, 0]))
            p1_y = int(np.mean(hand_result.left_hand.pixel_landmarks[palm_indices, 1]))
            p2_x = int(np.mean(hand_result.right_hand.pixel_landmarks[palm_indices, 0]))
            p2_y = int(np.mean(hand_result.right_hand.pixel_landmarks[palm_indices, 1]))
            p1 = (p1_x, p1_y)
            p2 = (p2_x, p2_y)
            center = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)

            # Steering axle line (Racing Red & Cyan glow) connecting fist centroids
            cv2.line(output, p1, p2, (30, 30, 220), 4, cv2.LINE_AA)
            cv2.circle(output, p1, 8, (255, 200, 0), -1, cv2.LINE_AA)
            cv2.circle(output, p2, 8, (50, 50, 255), -1, cv2.LINE_AA)
            cv2.circle(output, center, 14, (0, 220, 255), -1, cv2.LINE_AA)
            cv2.circle(output, center, 18, (0, 180, 220), 2, cv2.LINE_AA)

        for hand in [hand_result.left_hand, hand_result.right_hand]:
            if hand is None:
                continue

            # Theme: Left hand = Cyan, Right hand = Racing Red
            color_primary = (255, 200, 0) if hand.handedness == "Left" else (50, 50, 255)
            color_joints = (0, 255, 255) if hand.handedness == "Left" else (100, 150, 255)

            # Draw bones
            for start_idx, end_idx in self.CONNECTIONS:
                pt1 = tuple(hand.pixel_landmarks[start_idx])
                pt2 = tuple(hand.pixel_landmarks[end_idx])
                cv2.line(output, pt1, pt2, color_primary, 2, cv2.LINE_AA)

            # Draw joints
            for i, pt in enumerate(hand.pixel_landmarks):
                radius = 5 if i in [4, 8, 12, 16, 20] else 3
                cv2.circle(output, tuple(pt), radius, color_joints, -1, cv2.LINE_AA)

            # Draw bounding box and label badge
            x, y, w, h = hand.bbox
            cv2.rectangle(output, (x - 8, y - 8), (x + w + 8, y + h + 8), color_primary, 1, cv2.LINE_AA)

            badge_text = f"{hand.handedness.upper()} ({int(hand.confidence * 100)}%)"
            badge_pos = (x - 8, max(y - 14, 20))
            cv2.putText(
                output,
                badge_text,
                badge_pos,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

        return output

    def release(self):
        """Releases MediaPipe resources."""
        if self._detector:
            self._detector.close()
            self._detector = None
        self._previous_landmarks.clear()
        logger.info("HandTracker released.")
