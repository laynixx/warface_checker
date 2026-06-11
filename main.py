import sys
import os
import warnings
from typing import List

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QTableWidgetItem, QTableWidget,
    QPlainTextEdit, QPushButton, QLineEdit, QSpinBox, QCheckBox, QMessageBox, QLabel
)
from PyQt5.QtCore import QThreadPool, QTimer

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Импортируем сгенерированный UI интерфейс
from ui.ui_mainwindow import Ui_MainWindow

# Импортируем наши новые модули
from core.utils import load_accounts, load_proxies
from workers.proxy_worker import ProxyCheckWorker, ProxyCheckSignals
from workers.account_worker import AccountChecker, WorkerSignals

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.edit_accounts = self.findChild(QLineEdit, "edit_accounts")
        self.edit_proxies = self.findChild(QLineEdit, "edit_proxies")
        self.spin_threads = self.findChild(QSpinBox, "spin_threads")
        self.spin_delay = self.findChild(QSpinBox, "spin_delay")
        self.btn_start = self.findChild(QPushButton, "btn_start")
        self.btn_browse_accounts = self.findChild(QPushButton, "btn_browse_accounts")
        self.btn_browse_proxies = self.findChild(QPushButton, "btn_browse_proxies")
        self.txt_log = self.findChild(QPlainTextEdit, "txt_log")
        self.table_results = self.findChild(QTableWidget, "table_results")
        self.btn_save = self.findChild(QPushButton, "btn_save")
        self.check_verify_proxy = self.findChild(QCheckBox, "check_verify_proxy")
        self.lbl_good = self.findChild(QLabel, "lbl_good")
        self.lbl_bad = self.findChild(QLabel, "lbl_bad")
        self.lbl_threads = self.findChild(QLabel, "lbl_threads")
        self.lbl_proxies_count = self.findChild(QLabel, "lbl_proxies_count")
        self.lbl_remaining = self.findChild(QLabel, "lbl_remaining")

        self.spin_threads.setMaximum(9999)

        self.table_results.setColumnCount(4)
        self.table_results.setHorizontalHeaderLabels(["Email", "Proxy", "Name", "Donat"])
        self.table_results.horizontalHeader().setStretchLastSection(True)

        self.btn_browse_accounts.clicked.connect(self.browse_accounts)
        self.btn_browse_proxies.clicked.connect(self.browse_proxies)
        self.btn_start.clicked.connect(self.toggle_checking)
        self.btn_save.clicked.connect(self.save_valid_accounts)

        self.accounts = []
        self.proxies = []
        self.results = []
        self.is_running = False
        self.stop_requested = False
        self.total_accounts = 0
        self.processed = 0
        self.timer = None
        self.proxy_check_timer = None
        self.worker_signals = None
        self.stop_timeout_timer = None

    def browse_accounts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите файл аккаунтов", "", "Text files (*.txt)")
        if path:
            self.edit_accounts.setText(path)

    def browse_proxies(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите файл прокси", "", "Text files (*.txt)")
        if path:
            self.edit_proxies.setText(path)

    def log_message(self, tag: str, msg: str):
        self.txt_log.appendPlainText(f"[{tag}] {msg}")

    def add_valid_result(self, result: dict):
        row = self.table_results.rowCount()
        self.table_results.insertRow(row)
        self.table_results.setItem(row, 0, QTableWidgetItem(result["email"]))
        self.table_results.setItem(row, 1, QTableWidgetItem(result["proxy"]))
        self.table_results.setItem(row, 2, QTableWidgetItem(result.get("name", "")))
        self.table_results.setItem(row, 3, QTableWidgetItem(result.get("donat", "")))
        self.results.append(result)
        self.update_stats()

    def on_progress(self, increment: int):
        self.processed += increment
        self.update_stats()

    def update_stats(self):
        good = len(self.results)
        bad = self.processed - good
        remaining = self.total_accounts - self.processed
        if remaining < 0:
            remaining = 0
        self.lbl_good.setText(f"Good: {good}")
        self.lbl_bad.setText(f"Bad: {bad}")
        self.lbl_remaining.setText(f"Осталось: {remaining}")

    def toggle_checking(self):
        if self.is_running:
            self.stop_checking()
        else:
            self.start_checking()

    def stop_checking(self):
        if not self.is_running:
            return
        self.stop_requested = True
        self.log_message("GUI", "Остановка... (дождитесь завершения текущих задач)")
        self.btn_start.setText("Стоп")
        self.btn_start.setEnabled(False)
        self.stop_timeout_timer = QTimer()
        self.stop_timeout_timer.setSingleShot(True)
        self.stop_timeout_timer.timeout.connect(self.force_stop)
        self.stop_timeout_timer.start(10000)

    def force_stop(self):
        if self.is_running:
            self.log_message("GUI", "Принудительный сброс состояния")
            self.is_running = False
            self.btn_start.setText("Запустить")
            self.btn_start.setEnabled(True)
            if self.timer:
                self.timer.stop()
            if self.proxy_check_timer:
                self.proxy_check_timer.stop()

    def start_checking(self):
        if self.is_running:
            return

        accounts_path = self.edit_accounts.text().strip()
        if not accounts_path or not os.path.exists(accounts_path):
            QMessageBox.critical(self, "Ошибка", "Укажите существующий файл аккаунтов")
            return

        proxies_path = self.edit_proxies.text().strip()
        if proxies_path and not os.path.exists(proxies_path):
            QMessageBox.critical(self, "Ошибка", "Файл прокси не найден")
            return

        self.accounts = load_accounts(accounts_path)
        all_proxies = load_proxies(proxies_path) if proxies_path else []

        if not self.accounts:
            QMessageBox.critical(self, "Ошибка", "Файл аккаунтов пуст")
            return

        delay = self.spin_delay.value()
        self.lbl_threads.setText(f"Потоки: {self.spin_threads.value()}")
        self.lbl_proxies_count.setText(f"Количество Прокси: {len(all_proxies)}")
        self.lbl_good.setText("Good: 0")
        self.lbl_bad.setText("Bad: 0")
        self.lbl_remaining.setText("Осталось: 0")

        if self.check_verify_proxy.isChecked() and all_proxies:
            self.start_proxy_checking(all_proxies, delay)
        else:
            self.proxies = all_proxies
            self.start_account_checking(delay)

    def start_proxy_checking(self, all_proxies: List[str], delay: float):
        self.stop_requested = False
        self.is_running = True
        self.btn_start.setText("Стоп")
        self.btn_start.setEnabled(True)

        self.log_message("PROXY", f"Проверка {len(all_proxies)} прокси в {self.spin_threads.value()} потоков...")

        max_threads = self.spin_threads.value()
        QThreadPool.globalInstance().setMaxThreadCount(max_threads)

        self.proxy_check_signals = ProxyCheckSignals()
        self.proxy_check_signals.log.connect(self.log_message)
        self.proxy_check_signals.result.connect(self.on_proxy_result)
        self.proxy_check_signals.progress.connect(self.on_proxy_progress)
        self.proxy_check_signals.finished.connect(self.on_proxy_check_finished)

        self.proxy_check_valid = []
        self.proxy_check_done = 0
        self.proxy_check_total = len(all_proxies)

        def get_stop_flag():
            return self.stop_requested

        for idx, proxy in enumerate(all_proxies):
            if self.stop_requested:
                break
            worker = ProxyCheckWorker(proxy, idx, self.proxy_check_total, self.proxy_check_signals, delay, get_stop_flag)
            QThreadPool.globalInstance().start(worker)

        self.proxy_check_timer = QTimer()
        self.proxy_check_timer.timeout.connect(self.check_proxy_finished)
        self.proxy_check_timer.start(500)

    def on_proxy_result(self, proxy: str, is_valid: bool):
        if is_valid and not self.stop_requested:
            self.proxy_check_valid.append(proxy)

    def on_proxy_progress(self, increment: int, total: int):
        self.proxy_check_done += increment
        if self.proxy_check_done >= total:
            self.proxy_check_signals.finished.emit()

    def check_proxy_finished(self):
        active = QThreadPool.globalInstance().activeThreadCount()
        if self.stop_requested:
            if active == 0:
                self.proxy_check_timer.stop()
                self.cleanup_stop()
            return
        if self.proxy_check_done >= self.proxy_check_total:
            self.proxy_check_timer.stop()
            self.on_proxy_check_finished()

    def on_proxy_check_finished(self):
        if self.stop_requested:
            return
        total_checked = self.proxy_check_total
        valid_count = len(self.proxy_check_valid)
        invalid_count = total_checked - valid_count
        self.log_message("PROXY", f" Проверка завершена: всего {total_checked} прокси")
        self.log_message("PROXY", f"    Валидных: {valid_count}")
        self.log_message("PROXY", f"    Невалидных: {invalid_count}")
        if valid_count == 0:
            QMessageBox.critical(self, "Ошибка", f"Нет рабочих прокси!")
            self.is_running = False
            self.btn_start.setText("Запустить")
            self.btn_start.setEnabled(True)
            return
        self.proxies = self.proxy_check_valid
        delay = self.spin_delay.value()
        self.start_account_checking(delay)

    def start_account_checking(self, delay: float):
        self.stop_requested = False
        self.table_results.setRowCount(0)
        self.txt_log.clear()
        self.results = []
        self.processed = 0
        self.total_accounts = len(self.accounts)
        self.update_stats()
        self.is_running = True
        self.btn_start.setText("Стоп")
        self.btn_start.setEnabled(True)

        threads = self.spin_threads.value()
        QThreadPool.globalInstance().setMaxThreadCount(threads)

        self.worker_signals = WorkerSignals()
        self.worker_signals.log.connect(self.log_message)
        self.worker_signals.result.connect(self.add_valid_result)
        self.worker_signals.progress.connect(self.on_progress)

        def get_stop_flag():
            return self.stop_requested

        for idx, (email, password) in enumerate(self.accounts):
            if self.stop_requested:
                break
            proxy = self.proxies[idx % len(self.proxies)] if self.proxies else None
            worker = AccountChecker(idx, email, password, proxy, self.worker_signals, get_stop_flag, delay)
            QThreadPool.globalInstance().start(worker)

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_accounts_finished)
        self.timer.start(500)

    def check_accounts_finished(self):
        active = QThreadPool.globalInstance().activeThreadCount()
        if self.stop_requested:
            if active == 0:
                self.timer.stop()
                self.cleanup_stop()
            return
        if self.processed >= self.total_accounts:
            self.timer.stop()
            self.is_running = False
            self.btn_start.setText("Запустить")
            self.btn_start.setEnabled(True)
            good = len(self.results)
            self.log_message("GUI", f"Проверка завершена. Успешно: {good}/{self.total_accounts}")
            QMessageBox.information(self, "Готово", f"Проверка завершена.\nУспешно: {good}")

    def cleanup_stop(self):
        if self.stop_timeout_timer:
            self.stop_timeout_timer.stop()
        self.is_running = False
        self.btn_start.setText("Запустить")
        self.btn_start.setEnabled(True)
        self.log_message("GUI", "Проверка остановлена.")

    def save_valid_accounts(self):
        if not self.results:
            QMessageBox.warning(self, "Предупреждение", "Нет валидных аккаунтов для сохранения.")
            return
        os.makedirs("result", exist_ok=True)
        goods_path = os.path.join("result", "goods.txt")
        with open(goods_path, "w", encoding="utf-8") as f:
            for acc in self.results:
                f.write(f"{acc['email']}:{acc['password']}\n")
        self.log_message("GUI", f"Сохранено в {goods_path}")
        QMessageBox.information(self, "Сохранение", f"Сохранено в файл:\n{goods_path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())