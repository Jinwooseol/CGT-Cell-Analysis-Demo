from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class QueuePanel(QWidget):
    sig_run_all = Signal()
    sig_abort_all = Signal()
    sig_row_double_clicked = Signal(str)  # job_id

    COLS = ["JobID", "SampleID", "Opt", "PCR", "Status", "Step", "Progress"]

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._emit_row_double_clicked)
        layout.addWidget(self.table)

        # job_id -> (row, progressbar)
        self._rows = {}

    def add_or_update_row(
        self,
        job_id: str,
        sample_id: str,
        has_opt: bool,
        has_pcr: bool,
        status: str,
        step: int,
        percent: int,
    ):
        if job_id not in self._rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            # text column
            self.table.setItem(r, 0, QTableWidgetItem(job_id))
            self.table.setItem(r, 1, QTableWidgetItem(sample_id))
            self.table.setItem(r, 2, QTableWidgetItem("✓" if has_opt else "✗"))
            self.table.setItem(r, 3, QTableWidgetItem("✓" if has_pcr else "✗"))
            self.table.setItem(r, 4, QTableWidgetItem(status))
            self.table.setItem(r, 5, QTableWidgetItem(str(step)))
            # progress column
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(percent)
            self.table.setCellWidget(r, 6, bar)
            self._rows[job_id] = (r, bar)
        else:
            r, bar = self._rows[job_id]
            self.table.item(r, 4).setText(status)
            self.table.item(r, 5).setText(str(step))
            bar.setValue(percent)

    def _emit_row_double_clicked(self, index):
        r = index.row()
        job_id = self.table.item(r, 0).text()
        self.sig_row_double_clicked.emit(job_id)
