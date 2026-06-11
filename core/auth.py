import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, Tuple, Callable
from core.utils import console_log, _sleep_check
from core.bypass import WarfaceBypass


class WarfaceAuth:
    BASE_URL = "https://account.astrum-play.ru"
    AUTH_API_URL = "https://auth-ac.astrum-play.ru/api/v3/pub/auth"
    WARFACE_BASE = "https://ru.warface.com"

    def __init__(self, email: str, password: str, proxy: Optional[str] = None, delay: float = 0,
                 stop_flag: Callable[[], bool] = None):
        self.email = email
        self.password = password
        self._tag = email.split("@")[0]
        self.delay = delay
        self.stop_flag = stop_flag or (lambda: False)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        self.csrf_token = None
        self.init_token = None
        self.oauth_params = {}
        self.account_info = {}

    def _sleep(self, seconds: float):
        _sleep_check(seconds, self.stop_flag)

    def _get_oauth_page(self) -> Tuple[str, str]:
        self._sleep(self.delay)
        oauth_url = "https://account.astrum-play.ru/app/oauth/login"
        continue_param = (
            "https://account.astrum-play.ru/oauth2/"
            "?response_type=code"
            "&client_id=ru.warface.com"
            "&redirect_uri=https%3A%2F%2Fru.warface.com%2Fdynamic%2Fauth%2F%3Fo2%3D1%26forward%3Dhttps%253A%252F%252Fru.warface.com%252Fprofile%252F"
            "&aacid=egK8pV_3"
            "&aaref=ru.warface.com%2Fprofile%2F"
            "&skip_grants=1"
        )
        resp = self.session.get(oauth_url, params={"continue": continue_param})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"name": "csrfmiddlewaretoken"})
        if meta and meta.get("content"):
            self.csrf_token = meta["content"]
        else:
            inp = soup.find("input", attrs={"name": "csrfmiddlewaretoken"})
            if inp and inp.get("value"):
                self.csrf_token = inp["value"]
        if not self.csrf_token:
            self.csrf_token = "kHMc0Nkps2AxV40Wmu8wYedpep4oiSHu"
        parsed = urlparse(continue_param)
        qs = parse_qs(parsed.query)
        self.oauth_params = {
            "aacid": qs.get("aacid", ["KBbeNM_4"])[0],
            "aaref": qs.get("aaref", ["ru.warface.com%2Fprofile%2F"])[0],
            "redirect_uri": qs.get("redirect_uri", [""])[0],
            "continue_url": continue_param,
        }
        return self.csrf_token, continue_param

    def init_auth(self) -> Dict[str, Any]:
        url = f"{self.AUTH_API_URL}/init"
        payload = {
            "login": self.email,
            "continue": self.oauth_params["continue_url"],
            "source": "web",
            "csrfmiddlewaretoken": self.csrf_token,
        }
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        self.init_token = data.get("token")
        return data

    def verify_auth(self, captcha_token: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.AUTH_API_URL}/verify"
        if not self.init_token:
            raise RuntimeError("Call init_auth first")
        payload = {
            "login": self.email,
            "password": self.password,
            "token": self.init_token,
            "csrfmiddlewaretoken": self.csrf_token,
        }
        if captcha_token:
            payload["smart-captcha"] = captcha_token
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def _execute_ajax_chain(self, referer_url: str):
        headers = {
            "Referer": referer_url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        }
        base = self.WARFACE_BASE
        self.session.get(f"{base}/dynamic/auth/?a=checkuser", headers=headers)
        self.session.get(f"{base}/dynamic/site-notification/?a=badge", headers=headers)
        self.session.get(f"{base}/dynamic/site-notification/?a=titles", headers=headers)
        self.session.get(f"{base}/dynamic/profile/?a=profile_json", headers=headers)
        self.session.get(f"{base}/dynamic/bonus/?a=progress&json=true", headers=headers)
        self.session.post(f"{base}/dynamic/user/?a=getapiblacklist", headers=headers)
        self.session.get(f"{base}/dynamic/all/time.php", headers=headers)

    def _finalize_warface_session(self) -> bool:
        console_log(self._tag, "Инициализация warface-сессии...")
        profile_url = f"{self.WARFACE_BASE}/profile/"
        njs_url = f"{self.WARFACE_BASE}/n.js"
        njs_resp = self.session.get(
            njs_url,
            headers={"Referer": profile_url, "Accept": "*/*"},
            allow_redirects=True,
        )
        if njs_resp.status_code != 200 or "n_js_once_lock" not in njs_resp.text:
            console_log(self._tag, " n.js не вернул скрипт защиты")
            return False
        try:
            njs = WarfaceBypass.solve_njs_from_script(njs_resp.text, self._tag)
            console_log(self._tag, f" Защита решена: n_js_t={njs['n_js_t']}, n_js_d={njs['n_js_d']}")
        except Exception as e:
            console_log(self._tag, f" Ошибка решения защиты: {e}")
            return False

        self.session.cookies.set("n_js_t", njs["n_js_t"], domain="ru.warface.com", path="/")
        self.session.cookies.set("n_js_d", njs["n_js_d"], domain="ru.warface.com", path="/")
        self.session.cookies.set("has_js", "1", domain="ru.warface.com", path="/")
        self.session.cookies.set("mrcurrentpath", "/profile/", domain="ru.warface.com", path="/")
        self.session.cookies.set("mrreferer", "", domain="ru.warface.com", path="/")
        self.session.cookies.set("login_event_tracked", "true", domain="ru.warface.com", path="/")

        self.session.get(profile_url, allow_redirects=True)
        self._execute_ajax_chain(profile_url)

        test_resp = self.session.get(
            f"{self.WARFACE_BASE}/dynamic/bonus/?a=progress&json=true",
            headers={"Referer": profile_url, "X-Requested-With": "XMLHttpRequest"},
        )
        if test_resp.status_code != 200:
            console_log(self._tag, f" HTTP {test_resp.status_code}")
            return False
        data = test_resp.json()
        if data.get("reload") is True:
            console_log(self._tag, " reload=true — n_js_d неверный или куки не приняты")
            return False

        if data.get("message") and data["message"].get("data"):
            user_info = data["message"].get("user", {})
            acc_data = data["message"]["data"]
            self.account_info = {
                "name": user_info.get("name", ""),
                "donat": acc_data.get("donat", ""),
                "category": acc_data.get("category", ""),
                "bk": acc_data.get("bk", ""),
                "rename_discount": acc_data.get("rename_discount", ""),
                "item_discount": acc_data.get("item_discount", ""),
                "csaid": acc_data.get("csaid", ""),
            }
            console_log(self._tag, f" Данные: donat={self.account_info['donat']}, name={self.account_info['name']}")
        else:
            console_log(self._tag, "️ Не удалось получить данные аккаунта")
            return False

        console_log(self._tag, " Сессия готова!")
        return True

    def finalize_session(self, auth_redirect_url: str) -> bool:
        resp = self.session.get(auth_redirect_url, allow_redirects=True)
        if resp.status_code not in (200, 302):
            console_log(self._tag, f" Ошибка финализации: {resp.status_code}")
            return False
        return self._finalize_warface_session()

    def login(self) -> bool:
        try:
            self._get_oauth_page()
            init_resp = self.init_auth()
            if init_resp.get("status") == "captcha_required" or "sitekey" in init_resp:
                console_log(self._tag, " Требуется капча")
                return False
            verify_resp = self.verify_auth(None)
            if "auth_redirect" not in verify_resp:
                console_log(self._tag, f" Ошибка verify: {verify_resp.get('error', verify_resp)}")
                return False
            auth_redirect = verify_resp["auth_redirect"]
            if not self.finalize_session(auth_redirect):
                return False
            return True
        except InterruptedError:
            console_log(self._tag, "Остановлено пользователем")
            return False
        except Exception as e:
            console_log(self._tag, f" Исключение: {e}")
            return False

    def get_cookies(self) -> Dict[str, str]:
        return {c.name: c.value for c in self.session.cookies if "warface.com" in (c.domain or "")}