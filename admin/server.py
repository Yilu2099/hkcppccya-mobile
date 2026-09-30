#!/usr/bin/env python3
"""Small authenticated editor for the static 政青 website."""
import base64
import binascii
from contextlib import contextmanager
import sys
import hashlib
import hmac
import io
import json
import os
import secrets
import auth
import shutil
import subprocess
import tempfile
import threading
import time
import fcntl
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError
from media import available_manifest, draft_root, draft_manifest_path, promote_referenced
from schema import ROOT, DATASETS, load, path_for, validate

PREFIX = "/cms"
ASSETS = ROOT / "assets"
PUBLIC = Path(os.environ.get("ZQ_CMS_PUBLIC_ROOT", "")).resolve() if os.environ.get("ZQ_CMS_PUBLIC_ROOT") else None
PASSWORD = os.environ.get("ZQ_CMS_PASSWORD", "")
ACCOUNT = os.environ.get("ZQ_CMS_ACCOUNT", "")
ATTEMPT_LOCK = threading.Lock()
class EditLock:
    """Serialize edits and maintenance builds without stopping the service."""
    def __init__(self):
        self.thread = threading.Lock()

    def __enter__(self):
        self.thread.acquire()
        try:
            directory = ROOT / 'admin' / 'private'
            directory.mkdir(parents=True, exist_ok=True)
            self.file = (directory / 'edit.lock').open('a')
            fcntl.flock(self.file, fcntl.LOCK_EX)
        except Exception:
            self.thread.release()
            raise

    def __exit__(self, *args):
        try:
            self.file.close()
        finally:
            self.thread.release()


LOCK = EditLock()
ATTEMPTS = {}
MAX_BODY = 18 * 1024 * 1024


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    backups = ROOT / "admin" / "backups"
    backups.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if path.exists(): shutil.copy2(path, backups / f"{path.stem}-{stamp}-{secrets.token_hex(2)}.json")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(data)
        temp = Path(f.name)
    os.replace(temp, path)


def update_site():
    subprocess.run([sys.executable, "build.py"], cwd=ROOT, check=True, timeout=240)
    if PUBLIC:
        subprocess.run([sys.executable, "admin/publish.py", str(PUBLIC)], cwd=ROOT, check=True, timeout=300)


@contextmanager
def updating(path):
    """Keep the editor revision retryable when a build or copy fails."""
    paths = path if isinstance(path, tuple) else (path,)
    previous = {p: p.read_bytes() if p.exists() else None for p in paths}
    try:
        yield
        update_site()
    except Exception:
        for p, raw in previous.items():
            if raw is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(raw)
        # Restore generated/public files too if the copy had already started.
        try:
            update_site()
        except Exception as exc:
            print("CMS restore failed:", exc, flush=True)
        raise


def optimize_image(encoded, destination=ASSETS):
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError("图片请控制在 12 MB 以内")
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > 36_000_000:
            raise ValueError("图片尺寸过大")
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(source.format)
        if not suffix:
            raise ValueError("只支持 JPG、PNG、WebP 图片")
        im = ImageOps.exif_transpose(source).copy()
    im.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    sha = hashlib.sha256(raw).hexdigest()[:24]
    original = destination / "originals" / "uploads" / f"{sha}{suffix}"
    original.parent.mkdir(parents=True, exist_ok=True)
    if not original.exists(): original.write_bytes(raw)
    result = {"original": original.relative_to(destination).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "originalBytes": len(raw)}
    web = destination / "web"
    web.mkdir(parents=True, exist_ok=True)
    for name, width in (("small", 800), ("large", 1600), ("thumb", 480)):
        resized = im.copy()
        resized.thumbnail((width, int(width * 1.5)), Image.Resampling.LANCZOS)
        dest = web / f"{sha}-{width}.webp"
        if not dest.exists(): resized.save(dest, "WEBP", quality=84, method=4)
        result[name] = dest.relative_to(destination).as_posix()
        result[name + "Width"] = resized.width
        result[name + "Height"] = resized.height
        result[name + "Bytes"] = dest.stat().st_size
    return f"uploads/{sha}.webp", result, im


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("CMS", self.address_string(), fmt % args, flush=True)

    def send_bytes(self, data, mime, status=200, extra=None, preview=False):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        policy = "default-src 'self' data:; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; base-uri 'none'" if preview else "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'none'; form-action 'self'"
        self.send_header("Content-Security-Policy", policy)
        for key, value in (extra or {}).items(): self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def result(self, value, status=200, extra=None):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status, extra)

    def error(self, status, message):
        self.result({"error": message}, status)

    def session(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get("Cookie", ""))
        except Exception: return None
        return auth.session(cookie["zq_session"].value) if "zq_session" in cookie else None

    def require(self, write=False, admin=False):
        user = self.session()
        if not user:
            self.error(401, "请先登录")
            return False
        if write and not hmac.compare_digest(self.headers.get("X-CSRF", ""), user["csrf"]):
            self.error(403, "安全校验失败，请重新登录")
            return False
        if admin and user["role"] != "admin":
            self.error(403, "只有管理员可以管理邀请")
            return False
        return True

    def signed_in(self, credentials):
        signed, csrf = credentials
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return self.result({"csrf": csrf}, extra={"Set-Cookie": f"zq_session={signed}; HttpOnly; SameSite=Strict; Path={PREFIX}; Max-Age=43200{secure}"})

    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= MAX_BODY:
            raise ValueError("上传内容过大或为空")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict): raise ValueError("请求格式不正确")
        return value

    def file(self, path, base):
        rel = unquote(path).lstrip("/")
        target = (base / rel).resolve()
        if not target.is_file() or not target.is_relative_to(base.resolve()):
            return self.error(404, "文件不存在")
        ext = target.suffix.lower()
        mime = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}.get(ext, "application/octet-stream")
        self.send_bytes(target.read_bytes(), mime, preview=base.resolve() == (ROOT / "dist").resolve())

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == PREFIX or route == PREFIX + "/":
            return self.file("index.html", ROOT / "admin")
        if route.startswith(PREFIX + "/static/"):
            return self.file(route[len(PREFIX + "/static/"):], ROOT / "admin" / "static")
        if route == PREFIX + "/api/session":
            user = self.session()
            return self.result({"loggedIn": bool(user), "csrf": user["csrf"] if user else None, "user": {k:user[k] for k in ("account", "role")} if user else None, "public": bool(PUBLIC)})
        if not self.require(): return
        if route == PREFIX + "/api/invites":
            if not self.require(admin=True): return
            return self.result(auth.invitations())
        if route == PREFIX + "/api/datasets":
            return self.result({name: {"label": label, "count": len(load(name))} for name, (label, _) in DATASETS.items()})
        if route == PREFIX + "/api/people":
            structure = load("structure")
            names = set()
            for rows in structure.values():
                for row in rows:
                    names.update(row.get("names", []))
                    for field in ("chair", "name"):
                        if row.get(field): names.add(row[field].replace("(兼)", "").replace("（兼）", "").strip())
            return self.result(sorted(names))
        if route == PREFIX + "/api/media":
            with LOCK:
                manifest = available_manifest(ROOT)
                return self.result({k: v["thumb"] if "thumb" in v else v["small"] for k, v in manifest.items()})
        if route.startswith(PREFIX + "/api/data/"):
            name = route.rsplit("/", 1)[-1]
            if name not in DATASETS: return self.error(404, "内容分类不存在")
            with LOCK:
                return self.result({"data": load(name), "revision": digest(path_for(name))})
        if route.startswith(PREFIX + "/media/"):
            rel = route[len(PREFIX + "/media/"):]
            staged = draft_root(ROOT) / rel
            if staged.is_file() and staged.resolve().is_relative_to(draft_root(ROOT).resolve()):
                return self.file(rel, draft_root(ROOT))
            if PUBLIC and rel.startswith(("web/", "originals/", "people/", "tici/", "hexin/", "files/")) and not (ASSETS / rel).is_file():
                return self.file(rel, PUBLIC)
            return self.file(rel, ASSETS)
        if route.startswith(PREFIX + "/preview/"):
            rel = route[len(PREFIX + "/preview/"):] or "index.html"
            if PUBLIC and rel.startswith(("web/", "originals/", "people/", "tici/", "hexin/", "files/")) and not (ROOT / "dist" / rel).exists():
                return self.file(rel, PUBLIC)
            return self.file(rel, ROOT / "dist")
        self.error(404, "页面不存在")

    def do_POST(self):
        route = urlsplit(self.path).path
        try:
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self.error(403, "请求来源不正确")
            value = self.body()
            if route in (PREFIX + "/api/login", PREFIX + "/api/register", PREFIX + "/api/invite-check"):
                ip = self.headers.get("X-Real-IP", self.client_address[0]) if self.client_address[0] in ("127.0.0.1", "::1") or self.client_address[0].startswith("172.") else self.client_address[0]
                with ATTEMPT_LOCK:
                    now = time.time()
                    for key in list(ATTEMPTS):
                        ATTEMPTS[key] = [t for t in ATTEMPTS[key] if now-t<900]
                        if not ATTEMPTS[key]: del ATTEMPTS[key]
                    account = value.get("account") if route.endswith('/login') else value.get("phone") if route.endswith('/register') else value.get("token")
                    account = account.strip() if isinstance(account, str) else ''
                    attempt_key = (route, ip, account)
                    ip_key = ('all', ip)
                    failures = ATTEMPTS.setdefault(attempt_key, [])
                    total = ATTEMPTS.setdefault(ip_key, [])
                    if len(failures) >= 30 or len(total) >= 120:
                        return self.error(429, "尝试次数太多，请 15 分钟后重试")
                    failures.append(now)
                    total.append(now)
                with LOCK:
                    if route.endswith('/invite-check'):
                        return self.result(auth.check_invite(str(value.get("token", ""))))
                    if route.endswith('/register'):
                        credentials = auth.register(str(value.get("token", "")), value.get("phone"), value.get("password"))
                    else:
                        credentials = auth.login(value.get("account"), value.get("password"))
                        if not credentials: return self.error(401, "账号或密码不正确")
                with ATTEMPT_LOCK: ATTEMPTS.pop(attempt_key, None)
                return self.signed_in(credentials)
            if not self.require(write=True): return
            if route == PREFIX + "/api/logout":
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                with LOCK: auth.logout(cookie["zq_session"].value)
                return self.result({"ok": True}, extra={"Set-Cookie": f"zq_session=; HttpOnly; SameSite=Strict; Path={PREFIX}; Max-Age=0"})
            if route in (PREFIX + "/api/invites", PREFIX + "/api/invites/revoke"):
                if not self.require(write=True, admin=True): return
                if route.endswith('/revoke'):
                    with LOCK: auth.revoke(int(value.get("id", 0)))
                    return self.result({"ok": True})
                with LOCK: return self.result(auth.invite(self.session()["id"]))
            if route.startswith(PREFIX + "/api/data/"):
                name = route.rsplit("/", 1)[-1]
                if name not in DATASETS: return self.error(404, "内容分类不存在")
                validate(name, value.get("data"))
                with LOCK:
                    path = path_for(name)
                    if value.get("revision") != digest(path): return self.error(409, "内容已被别人修改，请刷新后再编辑")
                    manifest_path = ASSETS / "image-variants.json"
                    with updating((path, manifest_path)):
                        save_json(path, value["data"])
                        promoted = promote_referenced(ROOT)
                        if promoted != json.loads(manifest_path.read_text()):
                            save_json(manifest_path, promoted)
                    return self.result({"revision": digest(path), "ok": True})
            if route == PREFIX + "/api/upload":
                with LOCK:
                    role = value.get("role", "content")
                    if role != "content" and role != "person" and role not in ("image:hero", "image:logo", "image:emblem", "image:chair", "image:ship"):
                        raise ValueError("图片位置不正确")
                    key, variant, im = optimize_image(value["base64"], draft_root(ROOT) if role == "content" else ASSETS)
                    if role == "person":
                        name = str(value.get("name", "")).strip()
                        if not name or "/" in name or "\\" in name or name in (".", ".."):
                            raise ValueError("请填写正确的人物姓名")
                        dest = ASSETS / "people" / f"{name}.webp"
                        if dest.exists():
                            backup = ROOT / "admin" / "backups" / "people"
                            backup.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(dest, backup / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.webp")
                        im.thumbnail((1000, 1500), Image.Resampling.LANCZOS)
                        key = f"people/{name}.webp"
                        path = ASSETS / "image-variants.json"
                        manifest = json.loads(path.read_text())
                        manifest[key] = variant
                        with updating((dest, path)):
                            im.save(dest, "WEBP", quality=84, method=4)
                            save_json(path, manifest)
                    else:
                        if role.startswith("image:"):
                            if role not in ("image:hero", "image:logo", "image:emblem", "image:chair", "image:ship"):
                                raise ValueError("图片位置不正确")
                            key = "image:chair_custom" if role == "image:chair" else role
                        path = ASSETS / "image-variants.json" if role.startswith("image:") else draft_manifest_path(ROOT)
                        manifest = json.loads(path.read_text()) if path.exists() else {}
                        manifest[key] = variant
                        if role.startswith("image:"):
                            with updating(path):
                                save_json(path, manifest)
                        else:
                            save_json(path, manifest)
                    return self.result({"key": key, "preview": PREFIX + "/media/" + (key if role == "person" else variant["small"])})
            if route == PREFIX + "/api/upload-pdf":
                raw = base64.b64decode(value["base64"], validate=True)
                if len(raw) > 12 * 1024 * 1024 or not raw.startswith(b"%PDF-"):
                    raise ValueError("请选择 12 MB 以内的 PDF 文件")
                with LOCK:
                    dest = ASSETS / "files" / "membership-form.pdf"
                    backup = ROOT / "admin" / "backups" / "files"
                    backup.mkdir(parents=True, exist_ok=True)
                    if dest.exists(): shutil.copy2(dest, backup / f"membership-form-{time.strftime('%Y%m%d-%H%M%S')}.pdf")
                    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as f:
                        f.write(raw)
                        temp = Path(f.name)
                    with updating(dest):
                        os.replace(temp, dest)
                return self.result({"ok": True})
            if route == PREFIX + "/api/build":
                with LOCK:
                    subprocess.run(["python3", "build.py"], cwd=ROOT, check=True, timeout=240)
                return self.result({"ok": True, "preview": PREFIX + "/preview/index.html"})
            if route == PREFIX + "/api/publish":
                if not PUBLIC: return self.error(400, "本机未配置正式站发布目录")
                with LOCK:
                    update_site()
                return self.result({"ok": True})
            self.error(404, "接口不存在")
        except (ValueError, KeyError, TypeError, binascii.Error, UnidentifiedImageError) as exc:
            self.error(400, str(exc))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            print("CMS update failed:", exc, flush=True)
            self.error(500, "网站更新未完成，修改仍保留在编辑框中，请稍后重试；若持续失败请联系管理员。")


if __name__ == "__main__":
    with LOCK: auth.initialize(ACCOUNT, PASSWORD)
    port = int(os.environ.get("ZQ_CMS_PORT", "8788"))
    host = os.environ.get("ZQ_CMS_BIND", "127.0.0.1")
    print(f"CMS listening at http://{host}:{port}{PREFIX}/", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
