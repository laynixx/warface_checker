from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot
from typing import Callable
from core.utils import check_proxy

class ProxyCheckSignals(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    result = pyqtSignal(str, bool)
    finished = pyqtSignal()

class ProxyCheckWorker(QRunnable):
    def __init__(self, proxy: str, idx: int, total: int, signals: ProxyCheckSignals, delay: float = 0, stop_flag: Callable[[], bool] = None):
        super().__init__()
        self.proxy = proxy
        self.idx = idx
        self.total = total
        self.signals = signals
        self.delay = delay
        self.stop_flag = stop_flag or (lambda: False)

    @pyqtSlot()
    def run(self):
        if self.stop_flag():
            return
        self.signals.log.emit("PROXY", f"Проверка {self.proxy}...")
        valid = check_proxy(self.proxy, self.delay, self.stop_flag)
        if valid:
            self.signals.log.emit("PROXY", f"✓ {self.proxy} - рабочий")
        else:
            self.signals.log.emit("PROXY", f"✗ {self.proxy} - не работает")
        self.signals.result.emit(self.proxy, valid)
        self.signals.progress.emit(1, self.total)