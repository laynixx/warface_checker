import os
import time
import threading
import requests
from typing import List, Tuple, Callable

_print_lock = threading.Lock()

def console_log(prefix: str, msg: str):
    with _print_lock:
        print(f"[{prefix}] {msg}")

def load_accounts(path: str) -> List[Tuple[str, str]]:
    accounts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":", 1)
            if len(parts) == 2:
                accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

def load_proxies(path: str) -> List[str]:
    proxies = []
    if not os.path.exists(path):
        return proxies
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" not in line:
                line = "http://" + line
            proxies.append(line)
    return proxies

def check_proxy(proxy: str, delay: float = 0, stop_flag: Callable[[], bool] = None) -> bool:
    if delay > 0:
        _sleep_check(delay, stop_flag)
    try:
        proxies = {"http": proxy, "https": proxy}
        test_url = "https://account.astrum-play.ru/app/oauth/login"
        resp = requests.get(test_url, proxies=proxies, timeout=10, verify=False)
        return resp.status_code in (200, 302)
    except Exception as e:
        console_log("PROXY_CHECK", f"{proxy} ошибка: {e}")
        return False

def _sleep_check(seconds: float, stop_flag: Callable[[], bool] = None):
    if seconds <= 0:
        return
    if stop_flag is None:
        time.sleep(seconds)
        return
    step = 0.1
    elapsed = 0.0
    while elapsed < seconds:
        if stop_flag():
            raise InterruptedError("Остановка по запросу")
        time.sleep(min(step, seconds - elapsed))
        elapsed += step