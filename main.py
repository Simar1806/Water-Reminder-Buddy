"""
WaterBuddy - A Cute Desktop Hydration Companion for Windows
Runs quietly in the background and periodically reminds the user to drink water.
Every 10 minutes, the mascot enters smoothly from the right edge,
plays the hydration video / animation for ~5 seconds with cute reactions,
and glides back off-screen automatically.
"""

import sys
import os
import time
import math
import argparse
import ctypes
from typing import List, Optional

from PySide6.QtCore import (
    Qt, QTimer, QRect, QRectF, QPoint, QPropertyAnimation,
    QEasingCurve, Property, Signal, QSize
)
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QFont, QLinearGradient,
    QPainterPath, QPen, QIcon, QAction, QFontMetrics, QBrush,
    QMovie
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu
)

# Constants & Defaults
DEFAULT_INTERVAL_SECONDS = 600  # 10 minutes between reminders
DEFAULT_VISIBLE_SECONDS = 5.0   # ~5 seconds visible duration
ANIM_FPS = 12                   # Fallback sprite FPS
SPRITE_SHEET_COLS = 6
SPRITE_SHEET_ROWS = 6

# Sprite sheet frame ranges (used if running in sprite-sheet mode)
WALK_FRAME_RANGE = list(range(0, 12))
DRINK_FRAME_RANGE = [12, 13, 14, 15, 16, 17, 18, 15, 16, 17, 18, 17, 18, 16, 19, 20, 21, 22]
SPARKLE_FRAME_RANGE = [23, 24, 25, 26, 27, 28, 25, 26, 27, 28, 26, 27]
WAVE_FRAME_RANGE = [29, 30, 31, 32, 33, 34, 35, 34, 33, 32, 31, 30]


def setup_windows_non_activating(widget: QWidget):
    """
    Applies Windows extended window flags (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    so the overlay never steals keyboard/mouse focus from full-screen games,
    browsers, VS Code, or other applications.
    """
    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = int(widget.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception:
            pass


def create_tray_icon() -> QIcon:
    """Generates a cute pastel water droplet tray icon."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Water droplet shape
    path = QPainterPath()
    path.moveTo(32, 6)
    path.cubicTo(46, 22, 54, 34, 54, 44)
    path.cubicTo(54, 55, 44, 62, 32, 62)
    path.cubicTo(20, 62, 10, 55, 10, 44)
    path.cubicTo(10, 34, 18, 22, 32, 6)
    path.closeSubpath()

    grad = QLinearGradient(16, 10, 48, 60)
    grad.setColorAt(0.0, QColor(140, 210, 255))
    grad.setColorAt(1.0, QColor(50, 130, 200))

    painter.setBrush(grad)
    painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
    painter.drawPath(path)

    # Highlight glint
    painter.setBrush(QColor(255, 255, 255, 210))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(22, 28, 8, 14)

    painter.end()
    return QIcon(pix)


class WaterBuddySpeechBubble(QWidget):
    """
    A polished, modern speech card with soft pastel styling,
    gentle elevation drop shadow, and smooth spring pop-in.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._opacity = 0.0
        self._offset_y = 10.0
        self.message = "Hey! Time for some water 💧"
        self.badge_text = "💧 HYDRATION CHECK"
        self.setFixedSize(260, 84)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, val: float):
        self._opacity = max(0.0, min(1.0, val))
        self.update()

    opacity = Property(float, get_opacity, set_opacity)

    def get_offset_y(self) -> float:
        return self._offset_y

    def set_offset_y(self, val: float):
        self._offset_y = val
        self.update()

    offset_y = Property(float, get_offset_y, set_offset_y)

    def paintEvent(self, event):
        if self._opacity <= 0.005:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)

        # Bubble geometry
        bubble_rect = QRectF(12, 6 + self._offset_y, self.width() - 24, 60)
        radius = 16.0

        # Draw soft shadow (dual-pass for realistic elevation)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 45, 75, int(22 * self._opacity)))
        painter.drawRoundedRect(bubble_rect.translated(0, 4), radius, radius)
        painter.setBrush(QColor(30, 60, 95, int(15 * self._opacity)))
        painter.drawRoundedRect(bubble_rect.translated(0, 8), radius + 2, radius + 2)

        # Speech bubble body + pointer tail path
        path = QPainterPath()
        path.addRoundedRect(bubble_rect, radius, radius)

        # Tail pointing down toward mascot head
        tail_x = bubble_rect.right() - 48
        tail_top = bubble_rect.bottom()
        tail = QPainterPath()
        tail.moveTo(tail_x - 9, tail_top - 1)
        tail.lineTo(tail_x, tail_top + 10)
        tail.lineTo(tail_x + 9, tail_top - 1)
        tail.closeSubpath()
        path = path.united(tail)

        # Crisp pastel gradient fill
        gradient = QLinearGradient(bubble_rect.topLeft(), bubble_rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(255, 255, 255, 252))
        gradient.setColorAt(0.5, QColor(248, 252, 255, 252))
        gradient.setColorAt(1.0, QColor(234, 246, 255, 252))

        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(135, 195, 245, int(240 * self._opacity)), 1.8))
        painter.drawPath(path)

        # Pill badge background ("HYDRATION CHECK")
        badge_rect = QRectF(bubble_rect.x() + 14, bubble_rect.y() + 8, 126, 17)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(215, 238, 255, int(230 * self._opacity)))
        painter.drawRoundedRect(badge_rect, 8.5, 8.5)

        # Badge text
        sub_font = QFont("Segoe UI", 7, QFont.Weight.Bold)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        painter.setFont(sub_font)
        painter.setPen(QColor(26, 110, 185))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.badge_text)

        # Main reminder text
        main_font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(main_font)
        painter.setPen(QColor(28, 44, 62))  # Crisp navy charcoal
        text_rect = QRectF(bubble_rect.x() + 14, bubble_rect.y() + 27, bubble_rect.width() - 28, 26)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.message)

        painter.end()


class WaterBuddyOverlay(QWidget):
    """
    Frameless, per-pixel transparent, topmost overlay window.
    Positions near the bottom-right corner and orchestrates:
    1. Mascot walking in from off-screen right
    2. Message popping up upon settling
    3. Direct transparent video playback of mascot drinking water & smiling
    4. Smooth exit off-screen to the right
    """
    reminder_finished = Signal()

    def __init__(self, base_dir: str, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir

        # Window flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Widget size: bubble (260x84) + mascot (208x408)
        self.overlay_width = 280
        self.overlay_height = 490
        self.setFixedSize(self.overlay_width, self.overlay_height)

        # Speech bubble
        self.bubble = WaterBuddySpeechBubble(self)
        self.bubble.move((self.overlay_width - self.bubble.width()) // 2, 0)

        # Mascot layout inside overlay
        self.mascot_target_w = 208
        self.mascot_target_h = 408
        self.mascot_x = (self.overlay_width - self.mascot_target_w) // 2
        self.mascot_y = 82

        # Video / Animation states
        self.movie: Optional[QMovie] = None
        self.mode = "VIDEO"  # "VIDEO" or "SPRITE"
        self.frames: List[QPixmap] = []
        self.frame_index = 0
        self.float_tick = 0.0

        # Load mascot (prefers transparent video buddy.webp, fallback to buddy.png)
        self.load_mascot()

        # Position animation for sliding in/out
        self.move_anim = QPropertyAnimation(self, b"pos")
        self.move_anim.finished.connect(self._on_move_anim_finished)
        self._target_move_action: Optional[str] = None
        self._saved_duration_sec = DEFAULT_VISIBLE_SECONDS

        # Bubble animations
        self.bubble_fade = QPropertyAnimation(self.bubble, b"opacity")
        self.bubble_slide = QPropertyAnimation(self.bubble, b"offset_y")

        # Duration timer for staying ~5s
        self.duration_timer = QTimer(self)
        self.duration_timer.setSingleShot(True)
        self.duration_timer.timeout.connect(self.start_exit)

        # Subtle floating breathing timer
        self.float_timer = QTimer(self)
        self.float_timer.timeout.connect(self.on_float_tick)
        self.float_timer.start(50)

    def load_mascot(self):
        """Loads transparent video buddy.webp if available, or buddy.png sprite."""
        webp_path = os.path.join(self.base_dir, "buddy.webp")
        png_path = os.path.join(self.base_dir, "buddy.png")

        if os.path.exists(webp_path):
            self.movie = QMovie(webp_path)
            if self.movie.isValid():
                self.mode = "VIDEO"
                self.movie.frameChanged.connect(self.on_movie_frame_changed)
                print(f"Loaded transparent mascot video: buddy.webp ({self.movie.frameCount()} frames).")
                return

        # Fallback to PNG
        if os.path.exists(png_path):
            master_pixmap = QPixmap(png_path)
            if not master_pixmap.isNull():
                pw, ph = master_pixmap.width(), master_pixmap.height()
                if pw >= 1200 and ph >= 2000:
                    frame_w = pw // SPRITE_SHEET_COLS
                    frame_h = ph // SPRITE_SHEET_ROWS
                    self.frames = []
                    for r in range(SPRITE_SHEET_ROWS):
                        for c in range(SPRITE_SHEET_COLS):
                            f_pix = master_pixmap.copy(c * frame_w, r * frame_h, frame_w, frame_h)
                            self.frames.append(f_pix)
                    self.mode = "SPRITE"
                    print(f"Loaded sprite sheet fallback: {len(self.frames)} frames.")
                    return
                else:
                    self.frames = [master_pixmap]
                    self.mode = "STATIC"
                    print("Loaded single mascot image.")
                    return

        print("Warning: Neither buddy.webp nor buddy.png found.")

    def on_movie_frame_changed(self, frame_no):
        self.update()

    def on_float_tick(self):
        if not self.isVisible():
            return
        self.float_tick += 0.1
        if self.bubble.get_opacity() > 0.9:
            float_offset = math.sin(self.float_tick) * 1.5
            self.bubble.set_offset_y(float_offset)

    def showEvent(self, event):
        super().showEvent(event)
        setup_windows_non_activating(self)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        target_rect = QRectF(self.mascot_x, self.mascot_y, self.mascot_target_w, self.mascot_target_h)

        if self.mode == "VIDEO" and self.movie:
            current_pix = self.movie.currentPixmap()
            if not current_pix.isNull():
                painter.drawPixmap(target_rect, current_pix, QRectF(current_pix.rect()))
        elif self.frames:
            pix = self.frames[self.frame_index % len(self.frames)]
            painter.drawPixmap(target_rect, pix, QRectF(pix.rect()))

        painter.end()

    def start_reminder(self, duration_sec: float = DEFAULT_VISIBLE_SECONDS):
        """Starts entrance motion from off-screen right with natural easing."""
        screen = QApplication.primaryScreen()
        work_area = screen.availableGeometry()

        settled_x = work_area.right() - self.overlay_width - 25
        settled_y = work_area.bottom() - self.overlay_height - 8
        offscreen_x = work_area.right() + 45

        # Place initially outside visible screen on the right
        self.move(offscreen_x, settled_y)
        self.bubble.set_opacity(0.0)
        self.bubble.set_offset_y(15.0)

        # Reset video to beginning
        if self.movie:
            self.movie.jumpToFrame(0)
            self.movie.start()

        self.show()
        setup_windows_non_activating(self)

        self._target_move_action = "ARRIVE"
        self._saved_duration_sec = duration_sec

        # Smooth glide into position (1500ms, OutCubic)
        self.move_anim.stop()
        self.move_anim.setDuration(1500)
        self.move_anim.setStartValue(QPoint(offscreen_x, settled_y))
        self.move_anim.setEndValue(QPoint(settled_x, settled_y))
        self.move_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.move_anim.start()

    def _on_move_anim_finished(self):
        """Handles completion of entrance or exit slide."""
        if self._target_move_action == "ARRIVE":
            # Reached position: pop in message bubble
            self.bubble_fade.stop()
            self.bubble_fade.setDuration(450)
            self.bubble_fade.setStartValue(0.0)
            self.bubble_fade.setEndValue(1.0)
            self.bubble_fade.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.bubble_fade.start()

            self.bubble_slide.stop()
            self.bubble_slide.setDuration(450)
            self.bubble_slide.setStartValue(12.0)
            self.bubble_slide.setEndValue(0.0)
            self.bubble_slide.setEasingCurve(QEasingCurve.Type.OutBack)
            self.bubble_slide.start()

            # Stay visible for duration (~5 seconds)
            self.duration_timer.start(int(self._saved_duration_sec * 1000))

        elif self._target_move_action == "EXIT":
            # Exited screen: stop video, hide window, and reset
            if self.movie:
                self.movie.stop()
            self.hide()
            self.reminder_finished.emit()

    def start_exit(self):
        """Smoothly leaves toward the right edge and disappears."""
        screen = QApplication.primaryScreen()
        work_area = screen.availableGeometry()

        settled_x = self.x()
        settled_y = self.y()
        offscreen_x = work_area.right() + 45

        # Bubble fades out
        self.bubble_fade.stop()
        self.bubble_fade.setDuration(300)
        self.bubble_fade.setStartValue(self.bubble.get_opacity())
        self.bubble_fade.setEndValue(0.0)
        self.bubble_fade.setEasingCurve(QEasingCurve.Type.InQuad)
        self.bubble_fade.start()

        self._target_move_action = "EXIT"

        # Smooth glide out to right (1400ms, InCubic)
        self.move_anim.stop()
        self.move_anim.setDuration(1400)
        self.move_anim.setStartValue(QPoint(settled_x, settled_y))
        self.move_anim.setEndValue(QPoint(offscreen_x, settled_y))
        self.move_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.move_anim.start()


class WaterBuddyApp:
    """
    Unobtrusive background coordinator running the 10-minute cycle.
    Provides tray controls for testing or quitting.
    """
    def __init__(self, interval_sec: int, duration_sec: float, test_mode: bool):
        self.interval_sec = interval_sec
        self.duration_sec = duration_sec
        self.test_mode = test_mode
        self.next_reminder_timestamp = time.time() + self.interval_sec

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.overlay = WaterBuddyOverlay(self.base_dir)
        self.overlay.reminder_finished.connect(self.on_reminder_finished)

        self.cycle_timer = QTimer()
        self.cycle_timer.setSingleShot(True)
        self.cycle_timer.timeout.connect(self.trigger_reminder)

        self.setup_tray()

        if self.test_mode:
            print("WaterBuddy started in test mode: Activating reminder immediately...")
            QTimer.singleShot(350, self.trigger_reminder)
        else:
            print(f"WaterBuddy is running quietly in background. Next reminder in {self.interval_sec // 60} minutes.")
            self.schedule_next(self.interval_sec)

    def setup_tray(self):
        """Discreet tray icon with quick actions."""
        self.tray = QSystemTrayIcon(create_tray_icon(), QApplication.instance())
        self.tray.setToolTip("WaterBuddy - Hydration Companion")

        menu = QMenu()

        action_now = QAction("💧 Drink Water Now (Test)", menu)
        action_now.triggered.connect(self.trigger_reminder)
        menu.addAction(action_now)

        self.action_status = QAction("⏱ Next: Calculating...", menu)
        self.action_status.setEnabled(False)
        menu.addAction(self.action_status)

        menu.addSeparator()

        action_exit = QAction("❌ Exit WaterBuddy", menu)
        action_exit.triggered.connect(QApplication.instance().quit)
        menu.addAction(action_exit)

        menu.aboutToShow.connect(self.update_tray_status)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def update_tray_status(self):
        remaining = int(max(0, self.next_reminder_timestamp - time.time()))
        mins = remaining // 60
        secs = remaining % 60
        self.action_status.setText(f"⏱ Next reminder: {mins}m {secs:02d}s")

    def trigger_reminder(self):
        """Triggers the hydration reminder overlay."""
        self.cycle_timer.stop()
        self.overlay.start_reminder(self.duration_sec)

    def on_reminder_finished(self):
        """Called automatically after mascot exits off-screen."""
        self.schedule_next(self.interval_sec)

    def schedule_next(self, seconds: int):
        self.next_reminder_timestamp = time.time() + seconds
        self.cycle_timer.start(seconds * 1000)


def main():
    parser = argparse.ArgumentParser(description="WaterBuddy - Cute Desktop Hydration Companion")
    parser.add_argument("--test", "--now", action="store_true", help="Trigger a reminder immediately upon launch")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
                        help=f"Reminder interval in seconds (default: {DEFAULT_INTERVAL_SECONDS}s = 10m)")
    parser.add_argument("--duration", type=float, default=DEFAULT_VISIBLE_SECONDS,
                        help=f"Visible reminder duration in seconds (default: {DEFAULT_VISIBLE_SECONDS}s)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    water_buddy = WaterBuddyApp(
        interval_sec=args.interval,
        duration_sec=args.duration,
        test_mode=args.test
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
