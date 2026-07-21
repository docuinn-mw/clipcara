import sys

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow


class ClipcaraApp(QApplication):
    """Forwards FileOpen events (macOS double-click/dock drop) to the
    main window. Other platforms never send them."""

    def __init__(self, argv):
        super().__init__(argv)
        self.window = None

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen and self.window is not None:
            self.window._open_file(event.file())
            return True
        return super().event(event)


def main():
    app = ClipcaraApp(sys.argv)
    app.setApplicationName("Clipcara")
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(filepath)
    app.window = window
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
