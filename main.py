import sys
from PyQt6.QtWidgets import QApplication
from player.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Clipcara")
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(filepath)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
