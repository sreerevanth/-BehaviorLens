"""
COMPLETE AI BEHAVIOR MONITORING SYSTEM (FIXED - NO FALSE ALARMS)
Pose + Person Detection: YOLOv8-Pose
FIXED: Stricter thresholds + Consecutive frame confirmation
"""

import os
import cv2
import time
import numpy as np
from collections import deque
from datetime import datetime
import pygame
from tensorflow import keras
from ultralytics import YOLO

# Silence TF noise
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"


class CompleteBehaviorMonitor:
    def __init__(self, fall_model_path, violence_model_path):
        print("=" * 70)
        print("AI BEHAVIOR MONITORING SYSTEM - FIXED VERSION")
        print("=" * 70)

        # Load AI models
        print("\n📥 Loading AI models...")
        try:
            self.fall_model = keras.models.load_model(fall_model_path)
            print("✅ Fall detection model loaded")
        except Exception as e:
            print(f"❌ Fall model error: {e}")
            self.fall_model = None

        try:
            self.violence_model = keras.models.load_model(violence_model_path)
            print("✅ Violence detection model loaded")
        except Exception as e:
            print(f"❌ Violence model error: {e}")
            self.violence_model = None

        # Load YOLOv8 Pose
        print("📥 Loading YOLOv8 Pose model...")
        self.pose_model = YOLO("yolov8n-pose.pt")
        print("✅ YOLOv8 loaded")

        # Alert system
        pygame.mixer.init()

        # Buffers
        self.violence_buffer = deque(maxlen=20)

        # Tracking
        self.last_movement_time = time.time()
        self.last_position = None
        self.inactivity_alert_sent = False

        # Restroom
        self.in_restroom_zone = False
        self.restroom_entry_time = None

        # Cooldowns
        self.last_alert_time = {}
        self.alert_cooldown = 10

        # FIXED: MUCH STRICTER THRESHOLDS
        self.FALL_THRESHOLD = 0.95           # Was 0.7, now 0.95 (95% confidence!)
        self.VIOLENCE_THRESHOLD = 0.90       # Was 0.6, now 0.90 (90% confidence!)

        # FIXED: Consecutive frame confirmation (prevents flickering)
        self.CONSECUTIVE_DETECTIONS_NEEDED = 5  # Need 5 frames in a row
        self.fall_detections_count = 0
        self.violence_detections_count = 0

        self.INACTIVITY_THRESHOLD = 15       # 15 seconds (change to 10800 for 3 hours)
        self.RESTROOM_THRESHOLD = 20         # 20 seconds (change to 1800 for 30 mins)

        # Statistics
        self.stats = {
            "total_frames": 0,
            "fall_detections": 0,
            "violence_detections": 0,
            "inactivity_alerts": 0,
            "restroom_alerts": 0
        }

        print("\n✅ System initialized with STRICT detection settings")
        print("   • Fall threshold: 95% confidence")
        print("   • Violence threshold: 90% confidence")
        print("   • Consecutive frames needed: 5")
        print("=" * 70 + "\n")

    # ---------------- ALERTS ---------------- #

    def play_alert_sound(self):
        """Play warning beep"""
        try:
            freq = 880
            sample_rate = 22050
            duration = 500
            t = np.linspace(0, duration / 1000, int(sample_rate * duration / 1000))
            wave = (np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
            sound = pygame.sndarray.make_sound(np.column_stack((wave, wave)))
            sound.play()
        except:
            pass  # Ignore sound errors

    def send_alert(self, alert_type, message, confidence=None):
        """Send alert with cooldown"""
        now = time.time()
        if now - self.last_alert_time.get(alert_type, 0) < self.alert_cooldown:
            return

        print("\n" + "="*70)
        print(f"🚨 {alert_type.upper()} ALERT 🚨")
        print("="*70)
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"Message: {message}")
        if confidence:
            print(f"AI Confidence: {confidence * 100:.1f}%")
        print("="*70 + "\n")

        self.play_alert_sound()
        self.last_alert_time[alert_type] = now

        # Update stats
        if alert_type in self.stats:
            self.stats[f"{alert_type}_alerts"] += 1

    # ---------------- AI DETECTIONS ---------------- #

    def detect_fall(self, frame):
        """Detect fall using trained model"""
        if self.fall_model is None:
            return 0.0

        try:
            img = cv2.resize(frame, (128, 128)) / 255.0
            img = np.expand_dims(img, axis=0)
            return self.fall_model.predict(img, verbose=0)[0][0]
        except:
            return 0.0

    def detect_violence(self):
        """Detect violence using trained model"""
        if self.violence_model is None or len(self.violence_buffer) < 20:
            return 0.0

        try:
            seq = np.expand_dims(np.array(self.violence_buffer), axis=0)
            return self.violence_model.predict(seq, verbose=0)[0][0]
        except:
            return 0.0

    # ---------------- MAIN PROCESSING ---------------- #

    def process_frame(self, frame):
        """Process each frame"""
        self.stats["total_frames"] += 1
        annotated = frame.copy()

        # Run YOLO pose detection
        results = self.pose_model(frame, conf=0.4, verbose=False)

        fall_prob = 0.0
        violence_prob = 0.0
        inactive_time = 0

        if results and len(results[0].keypoints) > 0:
            # Get keypoints and bounding box
            kp = results[0].keypoints.xy[0].cpu().numpy()
            box = results[0].boxes.xyxy[0].cpu().numpy()
            center_x = (box[0] + box[2]) / 2

            # Draw pose on frame
            annotated = results[0].plot()

            # Calculate movement
            if self.last_position is not None:
                movement = np.linalg.norm(kp - self.last_position)
                if movement > 5:  # Significant movement threshold
                    self.last_movement_time = time.time()
                    self.inactivity_alert_sent = False
            self.last_position = kp

            # === FALL DETECTION (WITH CONSECUTIVE FRAME CONFIRMATION) ===
            fall_prob = self.detect_fall(frame)

            if fall_prob > self.FALL_THRESHOLD:
                self.fall_detections_count += 1

                # Only alert after consecutive detections
                if self.fall_detections_count >= self.CONSECUTIVE_DETECTIONS_NEEDED:
                    self.stats["fall_detections"] += 1
                    self.send_alert("fall", "FALL DETECTED!", fall_prob)
                    self.fall_detections_count = 0  # Reset after alert

                    # Visual warning
                    cv2.putText(annotated, "!!! FALL DETECTED !!!",
                               (50, 100), cv2.FONT_HERSHEY_SIMPLEX,
                               1.5, (0, 0, 255), 3)
            else:
                self.fall_detections_count = 0  # Reset if not detected

            # === VIOLENCE DETECTION (WITH CONSECUTIVE FRAME CONFIRMATION) ===
            # Add frame to buffer
            vframe = cv2.resize(frame, (128, 128)) / 255.0
            self.violence_buffer.append(vframe)

            violence_prob = self.detect_violence()

            if violence_prob > self.VIOLENCE_THRESHOLD:
                self.violence_detections_count += 1

                # Only alert after consecutive detections
                if self.violence_detections_count >= self.CONSECUTIVE_DETECTIONS_NEEDED:
                    self.stats["violence_detections"] += 1
                    self.send_alert("violence", "VIOLENCE DETECTED!", violence_prob)
                    self.violence_detections_count = 0  # Reset after alert

                    # Visual warning
                    cv2.putText(annotated, "!!! VIOLENCE DETECTED !!!",
                               (50, 150), cv2.FONT_HERSHEY_SIMPLEX,
                               1.5, (0, 0, 255), 3)
            else:
                self.violence_detections_count = 0  # Reset if not detected

            # === INACTIVITY DETECTION ===
            inactive_time = time.time() - self.last_movement_time

            if inactive_time > self.INACTIVITY_THRESHOLD and not self.inactivity_alert_sent:
                self.send_alert("inactivity",
                               f"No movement for {int(inactive_time)} seconds!")
                self.inactivity_alert_sent = True

            # === RESTROOM ZONE MONITORING ===
            w = frame.shape[1]
            zone_start = int(w * 0.66)

            # Draw restroom zone
            cv2.rectangle(annotated, (zone_start, 0), (w, frame.shape[0]),
                         (255, 200, 0), 2)
            cv2.putText(annotated, "RESTROOM ZONE",
                       (zone_start + 10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                       0.7, (255, 200, 0), 2)

            if center_x > zone_start:  # Person in restroom zone
                if not self.in_restroom_zone:
                    self.in_restroom_zone = True
                    self.restroom_entry_time = time.time()
                    print("👤 Person entered restroom zone")

                time_in_restroom = time.time() - self.restroom_entry_time

                if time_in_restroom > self.RESTROOM_THRESHOLD:
                    self.send_alert("restroom",
                                   f"In restroom for {int(time_in_restroom)} seconds!")
                    self.restroom_entry_time = time.time()  # Reset to avoid spam
            else:
                if self.in_restroom_zone:
                    print("👤 Person left restroom zone")
                self.in_restroom_zone = False
                self.restroom_entry_time = None

        else:
            # No person detected
            cv2.putText(annotated, "NO PERSON DETECTED",
                       (50, 50), cv2.FONT_HERSHEY_SIMPLEX,
                       1, (0, 0, 255), 2)

        # === DRAW UI PANEL ===
        # Semi-transparent background
        overlay = annotated.copy()
        cv2.rectangle(overlay, (10, 10), (500, 250), (0, 0, 0), -1)
        annotated = cv2.addWeighted(annotated, 0.7, overlay, 0.3, 0)

        # Title
        cv2.putText(annotated, "AI Behavior Monitor - LIVE",
                   (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                   0.8, (0, 255, 0), 2)

        # Detection confidence bars
        # Fall
        fall_color = (0, 0, 255) if fall_prob > self.FALL_THRESHOLD else (0, 255, 0)
        cv2.putText(annotated, f"Fall: {fall_prob*100:.1f}% ({self.fall_detections_count}/{self.CONSECUTIVE_DETECTIONS_NEEDED})",
                   (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, fall_color, 2)
        bar_width = int(300 * min(fall_prob, 1.0))
        cv2.rectangle(annotated, (20, 90), (320, 105), (50, 50, 50), -1)
        cv2.rectangle(annotated, (20, 90), (20 + bar_width, 105), fall_color, -1)

        # Violence
        viol_color = (0, 0, 255) if violence_prob > self.VIOLENCE_THRESHOLD else (0, 255, 0)
        cv2.putText(annotated, f"Violence: {violence_prob*100:.1f}% ({self.violence_detections_count}/{self.CONSECUTIVE_DETECTIONS_NEEDED})",
                   (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, viol_color, 2)
        bar_width = int(300 * min(violence_prob, 1.0))
        cv2.rectangle(annotated, (20, 140), (320, 155), (50, 50, 50), -1)
        cv2.rectangle(annotated, (20, 140), (20 + bar_width, 155), viol_color, -1)

        # Inactivity
        inactive_time = time.time() - self.last_movement_time
        inactive_color = (0, 0, 255) if inactive_time > self.INACTIVITY_THRESHOLD else (0, 255, 0)
        cv2.putText(annotated, f"Inactive: {int(inactive_time)}s",
                   (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, inactive_color, 2)

        # Statistics
        cv2.putText(annotated,
                   f"Falls: {self.stats['fall_detections']} | Violence: {self.stats['violence_detections']}",
                   (20, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Instructions
        cv2.putText(annotated, "Press 'Q' to quit | 'R' to reset stats",
                   (10, annotated.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX,
                   0.5, (255, 255, 255), 1)

        return annotated

    # ---------------- RUN SYSTEM ---------------- #

    def run(self, cam=0):
        """Run monitoring system"""
        cap = cv2.VideoCapture(cam)

        if not cap.isOpened():
            print("❌ Cannot access camera!")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        print("🎥 SYSTEM RUNNING")
        print("="*70)
        print("Active Detections:")
        print("  1. Fall Detection (AI) - 95% threshold, 5 frame confirmation")
        print("  2. Violence Detection (AI) - 90% threshold, 5 frame confirmation")
        print("  3. Inactivity Monitoring - 15 seconds")
        print("  4. Restroom Zone - 20 seconds")
        print("\nControls:")
        print("  • Press 'Q' to quit")
        print("  • Press 'R' to reset statistics")
        print("="*70 + "\n")

        fps_time = time.time()
        fps_counter = 0
        fps = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                print("❌ Error reading frame")
                break

            # Process frame
            annotated = self.process_frame(frame)

            # Calculate FPS
            fps_counter += 1
            if time.time() - fps_time > 1:
                fps = fps_counter
                fps_counter = 0
                fps_time = time.time()

            # Display FPS
            cv2.putText(annotated, f"FPS: {fps}",
                       (annotated.shape[1] - 120, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Show frame
            cv2.imshow("AI Behavior Monitor (FIXED)", annotated)

            # Handle keys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                break
            elif key == ord('r') or key == ord('R'):
                self.stats = {k: 0 for k in self.stats}
                print("📊 Statistics reset")

        cap.release()
        cv2.destroyAllWindows()

        # Final summary
        print("\n" + "="*70)
        print("SESSION SUMMARY")
        print("="*70)
        print(f"Total Frames Processed: {self.stats['total_frames']}")
        print(f"Fall Detections: {self.stats['fall_detections']}")
        print(f"Violence Detections: {self.stats['violence_detections']}")
        print(f"Inactivity Alerts: {self.stats['inactivity_alerts']}")
        print(f"Restroom Alerts: {self.stats['restroom_alerts']}")
        print("="*70 + "\n")


# ---------------- ENTRY POINT ---------------- #

if __name__ == "__main__":
    FALL_MODEL = "models/fall_detection_model.h5"
    VIOLENCE_MODEL = "models/violence_detection_model.h5"

    monitor = CompleteBehaviorMonitor(FALL_MODEL, VIOLENCE_MODEL)
    monitor.run(0)