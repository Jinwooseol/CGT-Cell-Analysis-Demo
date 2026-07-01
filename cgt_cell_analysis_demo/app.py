import os
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from cgt_cell_analysis_demo import __resource_path__
from cgt_cell_analysis_demo.ui.widgets.splash_screen import SplashScreen

QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)


def _configure_qt_plugins() -> None:
    """Set Qt plugin path from venv (dev) or PyInstaller bundle (frozen)."""
    try:
        if getattr(sys, "frozen", False):
            base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            plugin_dir = base / "PySide6" / "plugins"
            if not plugin_dir.exists():
                plugin_dir = base / "_internal" / "PySide6" / "plugins"
        else:
            import PySide6

            plugin_dir = Path(PySide6.__file__).parent / "plugins"

        if plugin_dir.exists():
            QCoreApplication.setLibraryPaths([str(plugin_dir)])
            os.environ["QT_PLUGIN_PATH"] = str(plugin_dir)
    except Exception:
        pass


class StartupLoader(QThread):
    """Background thread for loading heavy components during startup"""

    progress_updated = Signal(str)  # Signal for progress updates
    loading_complete = Signal()  # Signal when loading is complete

    def __init__(self):
        super().__init__()

    def run(self):
        """Load heavy components in background"""
        try:
            # Step 1: Load configuration
            self.progress_updated.emit("Loading configuration...")
            self.msleep(100)  # Small delay for visual feedback

            # Step 2: Initialize PyTorch (if needed)
            self.progress_updated.emit("Initializing AI components...")
            self.msleep(200)

            # Step 3: Load reference data paths
            self.progress_updated.emit("Loading reference data...")
            self.msleep(150)

            # Step 4: Initialize OpenCV (if needed)
            self.progress_updated.emit("Initializing image processing...")
            self.msleep(200)

            # Step 5: Final setup
            self.progress_updated.emit("Finalizing setup...")
            self.msleep(100)

            # Signal completion
            self.loading_complete.emit()

        except Exception as e:
            print(f"Error during startup loading: {e}")
            self.loading_complete.emit()


def _set_windows_appusermodel_id(app_id: str) -> None:
    """Set explicit AppUserModelID so Windows taskbar uses our icon/grouping.

    Safe no-op on non-Windows platforms or if the API is unavailable.
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        # If this fails, we still proceed; the window icon is set below.
        pass


def _set_windows_taskbar_icon(hwnd, icon_path: Path) -> None:
    """Set Windows taskbar icon using multiple methods for maximum compatibility."""
    if platform.system() != "Windows":
        return

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        # Constants
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040

        LoadImageW = user32.LoadImageW
        LoadImageW.restype = wintypes.HANDLE
        LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]

        SendMessageW = user32.SendMessageW
        SendMessageW.restype = wintypes.LPARAM
        SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

        # Convert path to absolute path and ensure it exists
        icon_path_abs = icon_path.resolve()
        if not icon_path_abs.exists():
            return

        # Load icons with proper error handling
        hicon_big = LoadImageW(
            None, str(icon_path_abs), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        hicon_small = LoadImageW(None, str(icon_path_abs), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)

        if hicon_big and hicon_big != 0:
            SendMessageW(int(hwnd), WM_SETICON, ICON_BIG, hicon_big)
        if hicon_small and hicon_small != 0:
            SendMessageW(int(hwnd), WM_SETICON, ICON_SMALL, hicon_small)

        # Also set class icons as a fallback
        try:
            GCLP_HICON = -14
            GCLP_HICONSM = -34
            SetClassLongPtrW = user32.SetClassLongPtrW
            SetClassLongPtrW.restype = wintypes.LONG_PTR
            SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG_PTR]
            if hicon_big and hicon_big != 0:
                SetClassLongPtrW(int(hwnd), GCLP_HICON, hicon_big)
            if hicon_small and hicon_small != 0:
                SetClassLongPtrW(int(hwnd), GCLP_HICONSM, hicon_small)
        except Exception:
            pass
    except Exception:
        # Best-effort only; ignore if platform API unavailable.
        pass


def main() -> int:
    # Ensure Qt plugin directory is configured before creating QApplication
    _configure_qt_plugins()
    app = QApplication(sys.argv)

    # Optional: Windows AppUserModelID & taskbar icon setters
    try:
        _set_windows_appusermodel_id("cgt_cell_analysis_demo.Jinwoo Seol")
    except Exception:
        pass

    try:
        app.setApplicationName("CGT Cell Analysis Demo")
        app.setApplicationDisplayName("CGT Cell Analysis Demo")
        app.setOrganizationName("Jinwoo Seol")
    except Exception:
        pass

    icon_path = __resource_path__ / "icn_app_logo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Show splash screen immediately
    splash = SplashScreen()
    splash.update_message("Starting application...")

    # Process events to ensure splash screen is visible
    app.processEvents()

    # Start background loading
    loader = StartupLoader()

    def on_progress_update(message):
        splash.update_message(message)

    def on_loading_complete():
        # Import MainWindow only when needed (lazy loading)
        from cgt_cell_analysis_demo.ui.main_window import MainWindow

        # Create main window
        global _MAIN_WINDOW
        _MAIN_WINDOW = MainWindow()

        # Set taskbar icon if available
        if icon_path.exists():
            try:
                _set_windows_taskbar_icon(_MAIN_WINDOW.winId(), icon_path)
            except Exception:
                pass

        # Finish splash screen and show main window
        splash.finish_loading(_MAIN_WINDOW)

    # Connect signals
    loader.progress_updated.connect(on_progress_update)
    loader.loading_complete.connect(on_loading_complete)

    # Start background loading
    loader.start()

    # IMPORTANT: return the event loop result; don't sys.exit() here
    return app.exec()


if __name__ == "__main__":
    import multiprocessing as mp

    mp.freeze_support()  # required for frozen apps that might spawn processes
    sys.exit(main())
