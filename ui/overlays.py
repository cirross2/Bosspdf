"""
문서 뷰어 위에 떠 있는 오버레이 위젯
- FloatingBar: 페이지 이동·줌 컨트롤. 마우스를 가만히 두면 흐려지고, 움직이면 다시 선명해집니다.
- ToastLabel: 상태 표시줄 대신 잠깐 나타났다 사라지는 알림 (QStatusBar.showMessage와 같은 호출 방식)
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QCursor

IDLE_OPACITY = 0.35
IDLE_DELAY_MS = 2500


class FloatingBar(QFrame):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.setObjectName("floatingBar")
        self._host = host
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 3, 10, 3)
        self._layout.setSpacing(4)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 커서 위치를 가볍게 확인 (뷰어 마우스 이벤트를 가로채지 않음)
        self._last_cursor = QPoint()
        self._idle_ms = 0
        self._poll = QTimer(self)
        self._poll.setInterval(250)
        self._poll.timeout.connect(self._on_poll)
        self._poll.start()

    def add_widget(self, w: QWidget):
        self._layout.addWidget(w)

    def add_separator(self):
        line = QFrame(self)
        line.setFixedSize(1, 16)
        line.setStyleSheet("background-color: rgba(128,128,128,0.35);")
        self._layout.addWidget(line)

    def reposition(self):
        self.adjustSize()
        host = self._host
        vp = getattr(host, "viewport", None)
        area = vp().geometry() if callable(vp) else host.rect()
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + area.height() - self.height() - 16
        self.move(max(area.x() + 4, x), max(area.y() + 4, y))
        self.raise_()

    def _fade_to(self, value: float):
        if abs(self._effect.opacity() - value) < 0.01:
            return
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(value)
        self._anim.start()

    def wake(self):
        self._idle_ms = 0
        self._fade_to(1.0)

    def _on_poll(self):
        if not self.isVisible():
            return
        pos = QCursor.pos()
        over_bar = self.rect().contains(self.mapFromGlobal(pos))
        moved = pos != self._last_cursor
        self._last_cursor = pos
        inside_host = self._host.rect().contains(self._host.mapFromGlobal(pos))
        if over_bar or (moved and inside_host and self.window().isActiveWindow()):
            self.wake()
            return
        self._idle_ms += self._poll.interval()
        focus = self.window().focusWidget()
        if self._idle_ms >= IDLE_DELAY_MS and not over_bar and not (focus and self.isAncestorOf(focus)):
            self._fade_to(IDLE_OPACITY)


class ToastLabel(QLabel):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self.setObjectName("toastLabel")
        self._host = host
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(False)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.bottom_margin = 64

    def showMessage(self, text: str, timeout: int = 3000):
        if not text:
            self.hide()
            return
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(max(1200, int(timeout or 3000)))

    def clearMessage(self):
        self.hide()

    def reposition(self):
        host = self._host
        vp = getattr(host, "viewport", None)
        area = vp().geometry() if callable(vp) else host.rect()
        w = min(self.sizeHint().width(), max(120, area.width() - 40))
        self.setFixedWidth(w)
        x = area.x() + (area.width() - w) // 2
        y = area.y() + area.height() - self.height() - self.bottom_margin
        self.move(x, max(area.y() + 4, y))
