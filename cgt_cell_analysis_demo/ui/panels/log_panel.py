from PySide6.QtWidgets import QSizePolicy, QTextEdit, QVBoxLayout, QWidget


class LogPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Reduce margins
        layout.setSpacing(0)  # Reduce spacing
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(150)

        # Set dark background with light text
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #14213D;
                color: #ffffff;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 9pt;
            }
        """)

        layout.addWidget(self.log_text)

    def append(self, msg: str):
        # Colorize [Done] messages to orange
        if msg.strip().startswith("[Done]"):
            self.log_text.append(f"<span style='color:#ff9800'>{msg}</span>")
        else:
            self.log_text.append(msg)

    def _copy(self):
        self.text.selectAll()
        self.text.copy()
