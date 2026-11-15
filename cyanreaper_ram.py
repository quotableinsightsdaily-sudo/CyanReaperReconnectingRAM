"""CyanReaper’s RAM - Roblox account manager (Windows).
pip install pywebview requests psutil websocket-client     then:  python cyanreaper_ram.py
Accounts live in cyanreaper_ram.json next to this file (an old bloxbox.json is copied over automatically).
Cookies are stored in plain text there - keep that file private."""
import json, os, random, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse
import requests, psutil, webview

TITLE = "CyanReaper’s RAM"
BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(BASE, "cyanreaper_ram.json")   # next to the .exe (or the script)
_old = os.path.join(BASE, "bloxbox.json")
if not os.path.exists(SAVE) and os.path.exists(_old): shutil.copy(_old, SAVE)   # carry your accounts over
S = {"accounts": [], "place": "8737899170", "click": {"x": None, "y": None, "label": "", "delay": 25}, "interval": 60, "theme": "blue", "style": "glass", "color": 0, "afk": {"on": False, "every": 10}}
if os.path.exists(SAVE):
    S.update(json.load(open(SAVE)))
S["theme"] = S["theme"] if S["theme"] in ("pink", "blue", "green", "purple", "red") else "blue"
procs, busy, stopped, launched, presence = {}, set(), set(), {}, {}
avatars = {}
game = {"place": None, "name": "", "icon": ""}
save_lock = threading.Lock()
meta, logs = {}, []
def m(n): return meta.setdefault(n, {"since": None, "rejoins": 0, "fails": 0, "expired": False, "next": 0})
def log(msg):
    logs.append((time.strftime("%H:%M:%S"), msg)); del logs[:-30]
click_lock = threading.Lock()
auto_on = False
window = None

multi = {"ok": False, "msg": "multi-instance unavailable (Windows only)"}
try:  # multi-instance: hold Roblox's singleton mutex
    import ctypes
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True); _k32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = _k32.CreateMutexW(None, True, "ROBLOX_singletonMutex"); _err = ctypes.get_last_error()
    ctypes.windll.user32.SetProcessDPIAware()
    _left = sorted({p.info["name"] for p in psutil.process_iter(["name"])
                    if "roblox" in (p.info["name"] or "").lower() or p.info["name"] == "Windows10Universal.exe"})
    if not _mutex: multi["msg"] = "couldn't create the Roblox lock"
    elif _err == 183 or _left:   # 183 = the lock already existed, i.e. a Roblox is already running
        multi["msg"] = "Roblox already running (" + ", ".join(_left or ["lock exists"]) + ") - close it fully and restart CyanReaper’s RAM"
    else: multi.update(ok=True, msg="")
except Exception:
    _mutex = None

def save():
    with save_lock:
        tmp = SAVE + ".tmp"
        with open(tmp, "w") as f: json.dump(S, f, indent=1)
        os.replace(tmp, SAVE)   # atomic: a crash can never leave a half-written save file

def sess(cookie):
    s = requests.Session()
    c = cookie.strip().strip("\"'")
    if c.upper().startswith(".ROBLOSECURITY="): c = c[15:]
    s.cookies[".ROBLOSECURITY"] = c.replace(" ", "").replace("\n", "")
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s

def user_id(a):
    if "id" not in a:
        a["id"] = sess(a["cookie"]).get("https://users.roblox.com/v1/users/authenticated", timeout=10).json()["id"]
        save()
    return a["id"]

def get_presence(a):
    """True = in a game, False = not, None = couldn't tell (network/API hiccup)."""
    try:
        s = sess(a["cookie"]); url = "https://presence.roblox.com/v1/presence/users"; body = {"userIds": [user_id(a)]}
        r = s.post(url, json=body, timeout=10)
        if r.status_code == 403 and r.headers.get("x-csrf-token"):
            r = s.post(url, json=body, timeout=10, headers={"X-CSRF-TOKEN": r.headers["x-csrf-token"]})
        return r.json()["userPresences"][0]["userPresenceType"] == 2
    except Exception:
        return None

def in_game(a):
    v = get_presence(a)
    return True if v is None else v   # on a hiccup assume fine, so we never launch duplicates

def alive(n):
    return n in procs and psutil.pid_exists(procs[n])

def roblox_pids():
    return {p.pid for p in psutil.process_iter(["name"]) if p.info["name"] == "RobloxPlayerBeta.exe"}

def roblox_cmds():
    """{pid: command line} of every running Roblox client."""
    out = {}
    for p in psutil.process_iter(["name", "cmdline"]):
        if p.info["name"] == "RobloxPlayerBeta.exe": out[p.pid] = " ".join(p.info["cmdline"] or [])
    return out

def bt_pid(bt, cmds=None):
    """The one Roblox client that was started with this launch id (every launch gets a unique id)."""
    for pid, c in (cmds if cmds is not None else roblox_cmds()).items():
        if str(bt) in c: return pid

def relink():
    """Re-match every account to ITS OWN window using the launch id, so a mix-up can never persist."""
    cmds = roblox_cmds()
    for a in list(S["accounts"]):
        n = a["name"]; mm = m(n)
        if mm.get("bt_ok") and n not in busy:
            pid = bt_pid(mm["bt"], cmds)
            if pid: procs[n] = pid
            else: procs.pop(n, None)

def launch(a, place):
    s = sess(a["cookie"])
    me = s.get("https://users.roblox.com/v1/users/authenticated", timeout=10)
    if me.status_code != 200: raise RuntimeError(f"Roblox rejected the cookie (HTTP {me.status_code}) - copy a fresh one")
    csrf = s.post("https://auth.roblox.com/v2/logout", timeout=10, json={}).headers.get("x-csrf-token")
    r = s.post("https://auth.roblox.com/v1/authentication-ticket", timeout=10, json={},
               headers={"X-CSRF-TOKEN": csrf, "Referer": f"https://www.roblox.com/games/{place}"})
    ticket = r.headers.get("rbx-authentication-ticket")
    if not ticket:
        raise RuntimeError(f"cookie is valid but Roblox refused the launch ticket (HTTP {r.status_code}): {r.text[:80]}")
    bt = random.randint(10**11, 10**12)
    url = ("https://assetgame.roblox.com/game/PlaceLauncher.ashx?request=RequestGame"
           f"&browserTrackerId={bt}&placeId={place}&isPlayTogetherGame=false")
    uri = (f"roblox-player:1+launchmode:play+gameinfo:{ticket}+launchtime:{int(time.time()*1000)}"
           f"+placelauncherurl:{urllib.parse.quote(url, safe='')}+browsertrackerid:{bt}"
           "+robloxLocale:en_us+gameLocale:en_us+channel:+LaunchExp:InApp")
    before = roblox_pids(); mm = m(a["name"]); mm["bt"] = bt; mm["bt_ok"] = False
    os.startfile(uri)
    for i in range(90):
        time.sleep(1)
        pid = bt_pid(bt)                    # exact: this launch's own id is in that client's command line
        if pid: procs[a["name"]] = pid; mm["bt_ok"] = True; return
        new = roblox_pids() - before - set(procs.values())
        if i > 40 and new:                  # fallback only if the command line can't be read
            procs[a["name"]] = new.pop(); return

def kill(n):
    pid = procs.pop(n, None); presence[n] = False; mm = m(n); mm["since"] = None
    if mm.get("bt_ok"): pid = bt_pid(mm["bt"])      # close ONLY the window that carries this account's own launch id
    if pid and psutil.pid_exists(pid):
        try:
            p = psutil.Process(pid)
            if p.name() == "RobloxPlayerBeta.exe": p.kill()   # never kill a reused PID
        except Exception: pass

def find_hwnd(pid):
    u = ctypes.windll.user32; found = []
    def cb(h, _):
        p = ctypes.c_ulong(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h): found.append(h)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
    def area(h):
        from ctypes import wintypes
        r = wintypes.RECT(); u.GetWindowRect(h, ctypes.byref(r)); return (r.right - r.left) * (r.bottom - r.top)
    return max(found, key=area) if found else None

def client_rect(h):
    from ctypes import wintypes
    u = ctypes.windll.user32
    r = wintypes.RECT(); u.GetClientRect(h, ctypes.byref(r))
    pt = wintypes.POINT(0, 0); u.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y, r.right, r.bottom

def window_at(x, y):
    """Top-level window under a screen point -> (hwnd, pid)."""
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.WindowFromPoint.argtypes = [wintypes.POINT]; u.WindowFromPoint.restype = wintypes.HWND
    u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]; u.GetAncestor.restype = wintypes.HWND
    h = u.GetAncestor(u.WindowFromPoint(wintypes.POINT(x, y)), 2)
    pid = ctypes.c_ulong(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return h, pid.value

def focus(h, pid):
    """Bring a window to the front and confirm that the foreground window belongs to that Roblox process."""
    u = ctypes.windll.user32
    if u.IsIconic(h): u.ShowWindow(h, 9)
    for _ in range(4):
        u.keybd_event(0x12, 0, 0, 0); u.SetForegroundWindow(h); u.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.4)
        p = ctypes.c_ulong(); u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(p))
        if p.value == pid: return True
    return False

def _fail(name, msg):
    log(f"{name}: click skipped - {msg}"); return False

def click_in(name):
    """Focus THIS account's Roblox window, then click the saved spot 3 times, one after the other.
    Before every click it re-checks that the right window is in front and is the one under the cursor."""
    c = S["click"]
    if c["x"] is None: return False
    pid = procs.get(name)
    try: ok = pid and psutil.Process(pid).name() == "RobloxPlayerBeta.exe"
    except Exception: ok = False
    h = ok and find_hwnd(pid)
    if not h: return _fail(name, "its Roblox window wasn't found")
    from ctypes import wintypes
    u = ctypes.windll.user32
    with click_lock:                       # one account at a time, one click at a time
        if not focus(h, pid): return _fail(name, "couldn't bring its window to the front")
        old = wintypes.POINT(); u.GetCursorPos(ctypes.byref(old))
        try:
            for i in range(3):
                x0, y0, w, hh = client_rect(h)                      # re-measured each click, in case the window moved
                tx, ty = int(x0 + c["x"] * w), int(y0 + c["y"] * hh)
                if window_at(tx, ty)[1] != pid:                     # lost focus or something is covering the spot
                    if not focus(h, pid) or window_at(tx, ty)[1] != pid: return _fail(name, "another window is covering the button")
                if i == 0: log(f"{name}: clicking at {tx},{ty} (window {w}x{hh})")
                u.SetCursorPos(tx, ty); time.sleep(0.1)
                u.mouse_event(1, 2, 2, 0, 0); time.sleep(0.05); u.mouse_event(1, -2, -2, 0, 0)   # real move events: Roblox only updates its hover on these
                time.sleep(0.4 if i == 0 else 0.15)
                u.SetCursorPos(tx, ty); time.sleep(0.05)
                u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.15); u.mouse_event(4, 0, 0, 0, 0)
                time.sleep(0.6)                                     # finish this click before the next
        finally:
            u.SetCursorPos(old.x, old.y)
    return True

def nudge(pid):
    """Focus a Roblox window and tap the spacebar twice (plus a tiny mouse move) so Roblox sees real activity."""
    h = find_hwnd(pid)
    if not h: return False
    u = ctypes.windll.user32
    with click_lock:
        prev = u.GetForegroundWindow()
        if not focus(h, pid): return False
        for _ in range(2):
            u.keybd_event(0x20, 0x39, 0, 0); time.sleep(0.12); u.keybd_event(0x20, 0x39, 2, 0); time.sleep(0.3)   # space (with scan code)
        u.mouse_event(1, 3, 0, 0, 0); time.sleep(0.05); u.mouse_event(1, -3, 0, 0, 0)
        time.sleep(0.2)
        if prev and prev != h:                                       # give focus back to what you were using
            u.keybd_event(0x12, 0, 0, 0); u.SetForegroundWindow(prev); u.keybd_event(0x12, 0, 2, 0)
    return True

def afk_loop():
    last = 0
    while True:
        time.sleep(5)
        if not S["afk"]["on"] or time.time() - last < S["afk"]["every"] * 60: continue
        last = time.time(); k = 0
        for pid in sorted(roblox_pids()):                           # every Roblox window, tracked or not
            if nudge(pid): k += 1
        if k: log(f"anti-AFK: pressed space in {k} window{'s' if k > 1 else ''}")

def after_join(a):
    """Event-on accounts: wait for the game to load, then click the saved button."""
    if a.get("event") and S["click"]["x"] is not None and alive(a["name"]):
        t0 = time.time()
        while time.time() - t0 < 120 and not get_presence(a): time.sleep(5)   # wait until Roblox confirms we're in
        time.sleep(max(5, int(S["click"]["delay"])))
        if click_in(a["name"]): log(f"{a['name']}: clicked the saved button (x3)")
        else: toast(f"{a['name']}: couldn't click - window not found")

def toast(msg):
    try: window.evaluate_js(f"toast({json.dumps(msg)})")
    except Exception: pass

login_state = {"on": False}

def find_browser():
    pf, pf86, la = (os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"))
    for path in (pf + r"\Google\Chrome\Application\chrome.exe", pf86 + r"\Google\Chrome\Application\chrome.exe",
                 la + r"\Google\Chrome\Application\chrome.exe", pf86 + r"\Microsoft\Edge\Application\msedge.exe",
                 pf + r"\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(path): return path

def add_cookie(cookie, d):
    """d = Roblox's /users/authenticated reply. Adds the account, or refreshes the cookie if we already have it."""
    for a in S["accounts"]:
        if a.get("id") == d["id"]:
            a.update(cookie=cookie, user=d["name"]); meta.pop(a["name"], None); stopped.discard(a["name"]); avatars.pop(a["name"], None)
            save(); log(f"{a['name']}: cookie refreshed"); api.push(); return toast(f"updated {a['name']}")
    name, i = d["name"], 2
    while api.get(name): name = f"{d['name']} {i}"; i += 1
    S["accounts"].append({"name": name, "cookie": cookie, "id": d["id"], "user": d["name"], "rejoin": True, "event": False})
    save(); log(f"added {name} (@{d['name']})"); api.push(); toast(f"added {name}")

def browser_login():
    """Opens a brand-new browser (clean temporary profile) on Roblox's login page, waits until you are logged in,
    reads the .ROBLOSECURITY cookie, adds the account, then closes the browser and deletes the temporary profile."""
    if login_state["on"]: return toast("a login window is already open")
    exe = find_browser()
    if not exe: return toast("Chrome or Edge wasn't found - use Paste cookie instead")
    try: import websocket
    except ImportError: return toast("missing package - run: pip install websocket-client")
    login_state["on"] = True
    tmp = tempfile.mkdtemp(prefix="ram_login_")
    sk = socket.socket(); sk.bind(("127.0.0.1", 0)); port = sk.getsockname()[1]; sk.close()
    proc = subprocess.Popen([exe, f"--remote-debugging-port={port}", f"--user-data-dir={tmp}", "--no-first-run",
                             "--no-default-browser-check", "https://www.roblox.com/login"])
    toast("Log in to Roblox in the window that just opened"); log("waiting for browser login...")
    cookie = info = None; t0 = time.time()
    try:
        while time.time() - t0 < 600 and proc.poll() is None and not cookie:
            time.sleep(1.5)
            try:
                ws = websocket.create_connection(requests.get(f"http://127.0.0.1:{port}/json/version", timeout=3).json()["webSocketDebuggerUrl"], timeout=5)
                ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
                while True:
                    msg = json.loads(ws.recv())
                    if msg.get("id") == 1: break
                ws.close()
                for ck in msg.get("result", {}).get("cookies", []):
                    if ck["name"] == ".ROBLOSECURITY" and ck["value"] and "roblox.com" in ck["domain"]:
                        r = sess(ck["value"]).get("https://users.roblox.com/v1/users/authenticated", timeout=10)
                        if r.status_code == 200: cookie, info = ck["value"], r.json()   # only accept a cookie Roblox confirms
            except Exception: pass
    finally:
        try:                                    # close the browser and everything it started
            parent = psutil.Process(proc.pid)
            for c in parent.children(recursive=True): c.kill()
            parent.kill()
        except Exception: pass
        time.sleep(1); shutil.rmtree(tmp, ignore_errors=True); login_state["on"] = False
    if cookie: add_cookie(cookie, info)
    else: toast("login window closed - nothing added")

class Api:
    last = None
    def get(self, n):
        return next((a for a in S["accounts"] if a["name"] == n), None)
    def state(self):
        return {"accounts": [{"name": a["name"], "rejoin": a.get("rejoin", False), "event": a.get("event", False), "avatar": avatars.get(a["name"], ""), "user": a.get("user", ""), "since": m(a["name"])["since"], "rejoins": m(a["name"])["rejoins"], "expired": m(a["name"])["expired"],
                              "status": "working" if a["name"] in busy else ("playing" if (alive(a["name"]) or presence.get(a["name"])) else "offline")}
                             for a in S["accounts"]],
                "place": S["place"], "multi": multi, "afk": S["afk"], "game": game, "logs": logs[-8:][::-1], "interval": S["interval"], "click": {"set": S["click"]["x"] is not None, "label": S["click"]["label"], "delay": S["click"]["delay"]},
                "style": S["style"], "color": S["color"], "auto": auto_on}
    def push(self, force=False):
        s = json.dumps(self.state())
        if force or s != self.last:
            self.last = s
            try: window.evaluate_js(f"render({s})")
            except Exception: pass
    def init(self): self.push(True)
    def _run(self, a, place, click=False):
        def w():
            busy.add(a["name"]); self.push()
            try:
                stopped.discard(a["name"]); launch(a, place); launched[a["name"]] = time.time()
                mm = m(a["name"]); mm["since"] = time.time(); mm["fails"] = 0; log(f"{a['name']}: joined")
                if click: after_join(a)
            except Exception as e:
                mm = m(a["name"]); mm["fails"] += 1; log(f"{a['name']}: {e}"); toast(f"{a['name']}: {e}")
                if "rejected the cookie" in str(e): mm["expired"] = True; stopped.add(a["name"])
            busy.discard(a["name"]); self.push()
        threading.Thread(target=w, daemon=True).start()
    def join(self, n):
        a = self.get(n)
        if a and n not in busy: self._run(a, S["place"])
    def leave(self, n): stopped.add(n); kill(n); self.push()
    def join_all(self):
        def w():
            for a in list(S["accounts"]):
                if a["name"] not in busy and not alive(a["name"]) and not m(a["name"])["expired"]:
                    self._run(a, S["place"]); time.sleep(8)  # stagger launches
        threading.Thread(target=w, daemon=True).start()
    def leave_all(self):
        stopped.update(a["name"] for a in S["accounts"])
        for n in list(procs): kill(n)
        self.push()
    def add(self, name, cookie):
        name, cookie = name.strip(), cookie.strip()
        if not name or not cookie or self.get(name): return toast("name missing or already used")
        def w():
            try:
                r = sess(cookie).get("https://users.roblox.com/v1/users/authenticated", timeout=10)
                if r.status_code != 200: return toast("Roblox rejected that cookie - copy a fresh one")
                d = r.json()
            except Exception as e: return toast(f"couldn't reach Roblox: {e}")
            S["accounts"].append({"name": name, "cookie": cookie, "id": d["id"], "user": d["name"], "rejoin": True, "event": False})
            save(); log(f"added {name} (@{d['name']})"); self.push()
        threading.Thread(target=w, daemon=True).start()
    def login(self): threading.Thread(target=browser_login, daemon=True).start()
    def edit(self, old, name, cookie):
        a = self.get(old); name, cookie = name.strip(), cookie.strip()
        if not a or not name or (name != old and self.get(name)): return toast("name missing or already used")
        def w():
            if cookie:
                try:
                    r = sess(cookie).get("https://users.roblox.com/v1/users/authenticated", timeout=10)
                    if r.status_code != 200: return toast("Roblox rejected that cookie")
                    d = r.json(); a.update(cookie=cookie, id=d["id"], user=d["name"])
                    meta.pop(old, None); stopped.discard(old); avatars.pop(old, None)
                except Exception as e: return toast(f"couldn't reach Roblox: {e}")
            if name != old:
                for dd in (procs, presence, avatars, meta):
                    if old in dd: dd[name] = dd.pop(old)
                stopped.discard(old); a["name"] = name
            save(); log(f"updated {name}"); self.push()
        threading.Thread(target=w, daemon=True).start()
    def remove(self, n):
        avatars.pop(n, None); kill(n); S["accounts"] = [a for a in S["accounts"] if a["name"] != n]; save(); self.push()
    def toggle(self, n, k):
        a = self.get(n)
        if a: a[k] = not a.get(k, False); save(); self.push()
    def set_place(self, v):
        if str(v).strip().isdigit(): S["place"] = str(v).strip(); save(); self.push(True); threading.Thread(target=fetch_game, daemon=True).start()
        else: toast("place ID must be a number")
    def set_click_label(self, v): S["click"]["label"] = str(v).strip(); save()
    def set_click_delay(self, v): S["click"]["delay"] = max(5, int(v)); save()
    def pick_click(self):
        def w():
            from ctypes import wintypes
            for i in (5, 4, 3, 2, 1):
                toast(f"Hover the button in a Roblox window... {i}"); time.sleep(1)
            u = ctypes.windll.user32; p = wintypes.POINT(); u.GetCursorPos(ctypes.byref(p))
            u.WindowFromPoint.argtypes = [wintypes.POINT]; u.WindowFromPoint.restype = wintypes.HWND
            u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]; u.GetAncestor.restype = wintypes.HWND
            h = u.GetAncestor(u.WindowFromPoint(p), 2)
            pid = ctypes.c_ulong(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            try: pname = psutil.Process(pid.value).name()
            except Exception: pname = "unknown"
            if pname != "RobloxPlayerBeta.exe": return toast(f"Cursor was over {pname}, not Roblox - try again")
            x0, y0, cw, ch = client_rect(h)
            S["click"]["x"], S["click"]["y"] = (p.x - x0) / cw, (p.y - y0) / ch
            save(); self.push(True); toast("Button saved ✓")
        threading.Thread(target=w, daemon=True).start()
    def test_click(self):
        def w():
            for a in list(S["accounts"]):
                if a.get("event") and alive(a["name"]): click_in(a["name"])
        threading.Thread(target=w, daemon=True).start()
    def set_auto(self, v):
        global auto_on; auto_on = bool(v); toast("auto reconnect " + ("on" if v else "off"))
    def set_interval(self, v): S["interval"] = int(v); save()
    def set_afk(self, on): S["afk"]["on"] = bool(on); save(); toast("anti-AFK " + ("on" if on else "off"))
    def set_afk_every(self, v): S["afk"]["every"] = max(2, min(18, int(v))); save()
    def set_style(self, v):
        if v in ("glass", "glossy", "cartoon", "retro", "neon", "clean"): S["style"] = v; save()
    def set_color(self, i): S["color"] = max(0, min(4, int(i))); save()
    def tile(self):
        try:
            u = ctypes.windll.user32
            sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
            pids = [p for p in procs.values() if psutil.pid_exists(p)]
            if not pids: return toast("nothing to tile")
            cols = int(len(pids) ** .5 + .99); rows = -(-len(pids) // cols); w, h = sw // cols, sh // rows
            for i, pid in enumerate(pids):
                def cb(hwnd, _, i=i, pid=pid):
                    p = ctypes.c_ulong(); u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
                    if p.value == pid and u.IsWindowVisible(hwnd):
                        u.MoveWindow(hwnd, (i % cols) * w, (i // cols) * h, w, h, True)
                    return True
                u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
        except Exception as e:
            toast(f"tile failed: {e}")

api = Api()

def loops():
    t = 0
    while True:
        time.sleep(2); t += 2
        for n in [n for n in procs if not psutil.pid_exists(procs[n])]: procs.pop(n)
        api.push()                       # cheap: only pushes when something changed
        if auto_on and t >= max(10, S["interval"]):
            t = 0
            for a in list(S["accounts"]):
                n = a["name"]
                if not a.get("rejoin") or n in busy or n in stopped or time.time() - launched.get(n, 0) < 120: continue
                if time.time() < m(n)["next"]: continue          # backing off after failed attempts
                if not in_game(a):   # dropped, crashed, or stuck on the disconnect screen
                    m(n)["rejoins"] += 1; m(n)["next"] = time.time() + min(600, 20 * 2 ** m(n)["fails"])
                    log(f"{n}: disconnected - rejoining"); toast(f"{n} disconnected - rejoining")
                    kill(n); api._run(a, S["place"], click=True); time.sleep(8)

def fetch_game():
    """Looks up the game's name and icon from its place ID."""
    place = S["place"]; g = {"place": place, "name": "", "icon": ""}
    try:
        uni = requests.get(f"https://apis.roblox.com/universes/v1/places/{place}/universe", timeout=10).json()["universeId"]
        g["icon"] = requests.get("https://thumbnails.roblox.com/v1/games/icons", timeout=10,
            params={"universeIds": uni, "size": "150x150", "format": "Png"}).json()["data"][0].get("imageUrl") or ""
        g["name"] = requests.get("https://games.roblox.com/v1/games", timeout=10, params={"universeIds": uni}).json()["data"][0]["name"]
    except Exception: pass
    game.update(g); api.push()

def presence_loop():
    """Keeps the status dots honest using Roblox presence, and re-links windows we lost track of."""
    while True:
        for a in list(S["accounts"]):
            n = a["name"]
            if n in busy: continue
            if n not in avatars:   # profile picture (headshot), retried until Roblox has it ready
                try:
                    d = requests.get("https://thumbnails.roblox.com/v1/users/avatar-headshot", timeout=10,
                        params={"userIds": user_id(a), "size": "150x150", "format": "Png"}).json()["data"][0]
                    if d.get("imageUrl"): avatars[n] = d["imageUrl"]
                except Exception: pass
            v = get_presence(a)
            if v is not None and not (n in stopped and v): presence[n] = v
        if game["place"] != S["place"] or not game["name"]: fetch_game()
        relink()
        lost = [n for n, v in presence.items() if v and n not in procs and n not in busy and not m(n).get("bt_ok")]
        free = roblox_pids() - set(procs.values())
        if len(lost) == 1 and len(free) == 1: procs[lost[0]] = free.pop()
        api.push()
        time.sleep(12)

def dark_title():
    try:
        h = ctypes.windll.user32.FindWindowW(None, TITLE)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(h, 20, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception: pass

HTML = r"""<!doctype html><html data-s="glass"><head><meta charset="utf-8"><style>
:root{--a:#4f8cff;--b:#7fd0ff;--txt:#eef1ff;--mut:#9aa3c7}
*{box-sizing:border-box;margin:0;font-family:'Segoe UI Variable','Segoe UI',system-ui,sans-serif}
html,body{height:100%;overflow:hidden;background:#090b16;color:var(--txt)}
.bg{position:fixed;inset:0;background:
 radial-gradient(560px 460px at 12% 8%,color-mix(in srgb,var(--a) 55%,transparent),transparent 70%),
 radial-gradient(620px 520px at 92% 30%,color-mix(in srgb,var(--b) 38%,transparent),transparent 70%),
 radial-gradient(700px 520px at 40% 108%,color-mix(in srgb,var(--a) 40%,transparent),transparent 70%),#090b16}
.app{position:relative;height:100%;display:grid;grid-template-columns:1fr 310px;gap:16px;padding:16px}
.glass{background:rgba(255,255,255,.07);backdrop-filter:blur(22px) saturate(150%);-webkit-backdrop-filter:blur(22px) saturate(150%);
 border:1px solid rgba(255,255,255,.13);border-radius:20px;box-shadow:0 10px 36px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.12)}
.main{display:flex;flex-direction:column;min-height:0;padding:18px}
.head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
h1{font-size:20px;font-weight:700;letter-spacing:.2px}h1 span{background:linear-gradient(90deg,var(--a),var(--b));-webkit-background-clip:text;color:transparent}
.sub{font-size:12px;color:var(--mut)}
.list{flex:1;overflow:auto;display:flex;flex-direction:column;gap:10px;padding-right:4px;min-height:0}
.list::-webkit-scrollbar{width:6px}.list::-webkit-scrollbar-thumb{background:rgba(255,255,255,.18);border-radius:9px}
.acc{display:flex;align-items:center;gap:14px;padding:12px 14px;border-radius:16px;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.09);transition:transform .15s,background .15s,border-color .15s}
.acc:hover{transform:translateY(-1px);background:rgba(255,255,255,.09);border-color:color-mix(in srgb,var(--a) 60%,transparent)}
.av{width:44px;height:44px;border-radius:14px;display:grid;place-items:center;font-weight:700;font-size:18px;color:#fff;background:linear-gradient(135deg,var(--a),var(--b));flex:none;position:relative;overflow:hidden}
.av img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.gm{display:flex;gap:12px;align-items:center;margin-bottom:12px}.gi{width:52px;height:52px;border-radius:14px;flex:none;display:grid;place-items:center;font-size:24px;background:rgba(255,255,255,.1);overflow:hidden}.gi img{width:100%;height:100%;object-fit:cover}
.gm .big{font-size:16px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.info{flex:1;min-width:0}.nm{font-weight:600;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.st{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--mut);margin-top:3px}
.dot{width:8px;height:8px;border-radius:50%;background:#6b7391}
.playing .dot{background:#3be08a;box-shadow:0 0 10px #3be08a}.working .dot{background:#ffc94d;animation:p 1s infinite}
@keyframes p{50%{opacity:.3}}
.tg{display:flex;flex-direction:column;gap:6px}
.sw{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;color:var(--mut);cursor:pointer;user-select:none}
.sw i{width:34px;height:19px;border-radius:20px;background:rgba(255,255,255,.16);position:relative;transition:background .2s;flex:none}
.sw i:after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;border-radius:50%;background:#fff;transition:transform .2s}
.sw.on i{background:linear-gradient(90deg,var(--a),var(--b))}.sw.on i:after{transform:translateX(15px)}.sw.on{color:var(--txt)}
button{border:0;cursor:pointer;color:var(--txt);font-size:13px;font-weight:600;padding:9px 16px;border-radius:12px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.12);transition:transform .12s,background .15s,filter .15s}
button:hover{background:rgba(255,255,255,.18)}button:active{transform:scale(.96)}
.pri{background:linear-gradient(135deg,var(--a),var(--b));border:0;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.25)}.pri:hover{filter:brightness(1.1);background:linear-gradient(135deg,var(--a),var(--b))}
.ic{padding:8px 10px;color:var(--mut)}.ic:hover{color:#ff7a7a}
.foot{display:flex;gap:10px;align-items:center;margin-top:14px}
.pill{flex:1;font-size:12px;color:var(--mut);padding:10px 14px;border-radius:12px;background:rgba(0,0,0,.22);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.side{display:flex;flex-direction:column;gap:16px;min-height:0}
.card{padding:16px}.card h3{font-size:11px;letter-spacing:1.3px;text-transform:uppercase;color:var(--mut);margin-bottom:12px;font-weight:600}
.big{font-size:22px;font-weight:700;margin-bottom:12px}.row{display:flex;gap:8px;flex-wrap:wrap}
input[type=text],input[type=password]{width:100%;padding:10px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.25);color:var(--txt);outline:0;font-size:13px;transition:border-color .15s}
input:focus{border-color:var(--a)}
input[type=range]{-webkit-appearance:none;width:100%;height:6px;border-radius:9px;background:rgba(255,255,255,.15);outline:0;margin:10px 0}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 0 0 4px color-mix(in srgb,var(--a) 55%,transparent)}
label.l{font-size:12px;color:var(--mut);display:block;margin:8px 0 6px}
.sws{display:flex;gap:12px;flex-wrap:wrap}.sws b{width:30px;height:30px;border-radius:50%;cursor:pointer;border:2px solid transparent;transition:transform .15s}
.sws b:hover{transform:scale(1.15)}.sws b.sel{border-color:var(--txt)}
.empty{margin:auto;text-align:center;color:var(--mut);font-size:14px;line-height:1.7}
.modal{position:fixed;inset:0;display:none;place-items:center;background:rgba(5,6,14,.55);z-index:9}.modal.show{display:grid}
.modal .glass{width:340px;padding:20px;background:rgba(30,34,60,.75)}.modal h3{font-size:16px;margin-bottom:14px;text-transform:none;letter-spacing:0;color:var(--txt)}
.modal input{margin-bottom:10px}
#toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,30px);opacity:0;pointer-events:none;padding:11px 18px;border-radius:14px;background:rgba(20,24,46,.92);border:1px solid rgba(255,255,255,.15);font-size:13px;transition:.25s;z-index:20}
#toast.show{opacity:1;transform:translate(-50%,0)}
.badge{font-size:10px;font-weight:700;letter-spacing:.5px;padding:2px 7px;border-radius:20px;background:rgba(255,90,90,.2);color:#ff9a9a;margin-left:8px;vertical-align:middle}
.meta{font-size:11px;color:var(--mut);margin-top:3px;min-height:14px}
.side{overflow-y:auto}.side>*{flex:none}.side::-webkit-scrollbar{width:0}
.log{font-size:12px;color:var(--mut);display:flex;flex-direction:column;gap:7px;max-height:140px;overflow:auto}.log b{color:var(--txt);font-weight:600;margin-right:8px;font-variant-numeric:tabular-nums}
.acc.working{border-color:color-mix(in srgb,#ffc94d 55%,transparent)}

:root{--s1:rgba(255,255,255,.07);--s2:rgba(255,255,255,.1);--s3:rgba(255,255,255,.18);--ln:rgba(255,255,255,.13);--inp:rgba(0,0,0,.25);--shadow:0 10px 36px rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.12);--r:20px;--bgc:#090b16;--modal:rgba(30,34,60,.78);--font:'Segoe UI Variable','Segoe UI',system-ui,sans-serif}
*{font-family:var(--font)}html,body{background:var(--bgc);color:var(--txt)}
.glass{background:var(--s1);border-color:var(--ln);box-shadow:var(--shadow);border-radius:var(--r)}
.acc{background:var(--s1);border-color:var(--ln)}.acc:hover{background:var(--s2)}
button:not(.pri){background:var(--s2);border-color:var(--ln)}button:not(.pri):hover{background:var(--s3)}
input[type=text],input[type=password]{background:var(--inp);border-color:var(--ln)}
.pill{background:var(--inp)}.sw i{background:var(--s3)}.modal .glass{background:var(--modal)}
#toast{background:var(--modal);color:var(--txt);border-color:var(--ln)}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{padding:6px 12px;font-size:12px;border-radius:10px}
.chip.sel{background:linear-gradient(135deg,var(--a),var(--b));color:#fff;border-color:transparent}
/* ---- CLEAN (light) ---- */
html[data-s=clean]{--txt:#1e293b;--mut:#64748b;--s1:rgba(255,255,255,.72);--s2:#fff;--s3:rgba(100,116,139,.28);--ln:rgba(100,116,139,.2);--inp:rgba(255,255,255,.9);--shadow:0 8px 28px rgba(60,80,130,.14);--bgc:#edf1f9;--modal:rgba(255,255,255,.96)}
html[data-s=clean] .bg{background:radial-gradient(600px 420px at 8% 0,color-mix(in srgb,var(--a) 24%,transparent),transparent 70%),radial-gradient(620px 460px at 100% 100%,color-mix(in srgb,var(--b) 26%,transparent),transparent 70%),#edf1f9}
html[data-s=clean] .modal{background:rgba(30,41,59,.28)}
/* ---- GLOSSY ---- */
html[data-s=glossy]{--s1:linear-gradient(180deg,rgba(255,255,255,.2),rgba(255,255,255,.05) 48%,rgba(0,0,0,.2) 52%,rgba(255,255,255,.06));--s2:linear-gradient(180deg,rgba(255,255,255,.3),rgba(255,255,255,.08) 48%,rgba(0,0,0,.2) 52%,rgba(255,255,255,.1));--s3:rgba(255,255,255,.28);--ln:rgba(255,255,255,.28);--shadow:0 12px 30px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.55);--bgc:#06080e;--modal:#161a2c}
html[data-s=glossy] .bg{background:radial-gradient(520px 420px at 15% 0,color-mix(in srgb,var(--a) 50%,transparent),transparent 70%),radial-gradient(560px 460px at 100% 100%,color-mix(in srgb,var(--b) 32%,transparent),transparent 70%),#06080e}
html[data-s=glossy] .pri,html[data-s=glossy] .av{background:linear-gradient(180deg,color-mix(in srgb,var(--b) 85%,#fff),var(--a) 50%,color-mix(in srgb,var(--a) 72%,#000) 51%,var(--a));box-shadow:inset 0 1px 0 rgba(255,255,255,.7),0 4px 14px color-mix(in srgb,var(--a) 45%,transparent)}
/* ---- CARTOON ---- */
html[data-s=cartoon]{--txt:#1b1b2f;--mut:#585878;--s1:#fff;--s2:#fff1b8;--s3:#ffd96b;--ln:#1b1b2f;--inp:#fff;--shadow:5px 5px 0 #1b1b2f;--bgc:#ffe9a8;--modal:#fff;--font:'Trebuchet MS','Comic Sans MS','Segoe UI',sans-serif}
html[data-s=cartoon] .bg{background:radial-gradient(color-mix(in srgb,var(--a) 40%,transparent) 2.5px,transparent 3px) 0 0/24px 24px,#ffe9a8}
html[data-s=cartoon] .glass{border-width:3px;backdrop-filter:none;-webkit-backdrop-filter:none}
html[data-s=cartoon] .acc,html[data-s=cartoon] .pill,html[data-s=cartoon] input[type=text],html[data-s=cartoon] input[type=password],html[data-s=cartoon] button{border-width:3px;border-color:#1b1b2f}
html[data-s=cartoon] .acc{box-shadow:3px 3px 0 #1b1b2f}
html[data-s=cartoon] button{box-shadow:3px 3px 0 #1b1b2f;font-weight:800}
html[data-s=cartoon] button:active{transform:translate(2px,2px);box-shadow:1px 1px 0 #1b1b2f}
html[data-s=cartoon] .pri{background:var(--a);color:#1b1b2f;text-shadow:none;border:3px solid #1b1b2f}
html[data-s=cartoon] .pri:hover{background:var(--b)}
html[data-s=cartoon] .chip.sel{color:#1b1b2f;border-color:#1b1b2f}
html[data-s=cartoon] .av{border:3px solid #1b1b2f;color:#1b1b2f;background:var(--b)}
html[data-s=cartoon] #toast{box-shadow:4px 4px 0 #1b1b2f;border-width:3px}
html[data-s=cartoon] .modal{background:rgba(27,27,47,.45)}
html[data-s=cartoon] h1 span,html[data-s=clean] h1 span{background:none;-webkit-text-fill-color:var(--a)}
/* ---- RETRO ---- */
html[data-s=retro]{--txt:var(--b);--mut:color-mix(in srgb,var(--a) 62%,#000);--s1:rgba(0,0,0,.5);--s2:color-mix(in srgb,var(--a) 16%,transparent);--s3:color-mix(in srgb,var(--a) 32%,transparent);--ln:var(--a);--inp:rgba(0,0,0,.55);--shadow:0 0 0 1px var(--a),0 0 18px color-mix(in srgb,var(--a) 22%,transparent);--r:2px;--bgc:#0b0905;--modal:#0b0905;--font:'Cascadia Mono',Consolas,'Courier New',monospace}
html[data-s=retro] .bg{background:#0b0905}
html[data-s=retro] .bg:after{content:"";position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(0,0,0,.3) 0 1px,transparent 1px 3px)}
html[data-s=retro] .glass{backdrop-filter:none;-webkit-backdrop-filter:none}
html[data-s=retro] .acc,html[data-s=retro] button,html[data-s=retro] input,html[data-s=retro] .pill,html[data-s=retro] .av,html[data-s=retro] .gi,html[data-s=retro] #toast,html[data-s=retro] .badge,html[data-s=retro] .sw i,html[data-s=retro] .sw i:after{border-radius:2px}
html[data-s=retro] .pri,html[data-s=retro] .chip.sel{background:var(--a);color:#000;text-shadow:none}
html[data-s=retro] .pri:hover{background:var(--b)}
html[data-s=retro] .av{color:#000;background:var(--a)}
html[data-s=retro] h1,html[data-s=retro] .nm{text-transform:uppercase;letter-spacing:1px}
html[data-s=retro] h1 span{background:none;-webkit-text-fill-color:var(--a)}
/* ---- NEON ---- */
html[data-s=neon]{--txt:#f6f3ff;--mut:#aaa6cf;--s1:rgba(12,9,30,.72);--s2:rgba(255,255,255,.08);--s3:rgba(255,255,255,.22);--ln:color-mix(in srgb,var(--a) 65%,transparent);--inp:rgba(0,0,0,.45);--shadow:0 0 0 1px color-mix(in srgb,var(--a) 35%,transparent),0 0 26px color-mix(in srgb,var(--a) 30%,transparent),inset 0 0 26px color-mix(in srgb,var(--a) 9%,transparent);--bgc:#05030f;--modal:rgba(12,8,32,.96)}
html[data-s=neon] .bg{background:radial-gradient(520px 420px at 12% 0,color-mix(in srgb,var(--a) 32%,transparent),transparent 70%),radial-gradient(520px 420px at 100% 100%,color-mix(in srgb,var(--b) 30%,transparent),transparent 70%),#05030f}
html[data-s=neon] .pri{box-shadow:0 0 18px color-mix(in srgb,var(--a) 70%,transparent)}
html[data-s=neon] h1{text-shadow:0 0 18px color-mix(in srgb,var(--a) 80%,transparent)}
html[data-s=neon] .acc:hover{box-shadow:0 0 16px color-mix(in srgb,var(--a) 40%,transparent)}
h1{display:flex;align-items:center;gap:10px}
.lg{width:36px;height:36px;border-radius:12px;display:grid;place-items:center;font-style:normal;font-size:19px;color:#fff;background:linear-gradient(135deg,var(--a),var(--b));box-shadow:0 4px 16px color-mix(in srgb,var(--a) 45%,transparent)}
#count{display:flex;gap:8px;margin-top:8px}
.stat{font-size:12px;padding:4px 11px;border-radius:20px;background:var(--s2);border:1px solid var(--ln);color:var(--mut)}.stat b{color:var(--txt);margin-right:2px}.stat.on b{color:#3be08a}
#q{margin-bottom:10px}
.tag{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;background:var(--s2);border:1px solid var(--ln)}
.tag.playing{color:#2fcf7f;background:rgba(59,224,138,.13);border-color:rgba(59,224,138,.38)}
.tag.working{color:#e0a820;background:rgba(255,201,77,.13);border-color:rgba(255,201,77,.4)}
.acc{position:relative}.acc.playing:before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:3px;background:#3be08a;box-shadow:0 0 10px #3be08a}
.eico{font-size:38px;margin-bottom:8px;opacity:.7}
.empty{padding:30px 0}
</style></head><body><div class="bg"></div>
<div class="app">
 <div class="glass main">
  <div class="head"><div><h1><i class="lg">☠</i>CyanReaper’s <span>RAM</span></h1><div class="sub" id="count">0 accounts</div><div class="sub" id="multi" style="margin-top:2px"></div></div>
   <div class="row"><button onclick="openAdd()" title="Add an account by pasting its cookie">Paste cookie</button><button class="pri" onclick="api.login()" title="Opens a fresh browser to log in">+ Account</button></div></div>
  <input type="text" id="q" placeholder="Search accounts…   Ctrl+F"><div class="list" id="list"></div>
  <div class="foot"><button onclick="api.leave_all()">Leave all</button><div class="pill" id="still">nobody playing</div><button class="pri" onclick="api.join_all()">♥ Join</button></div>
 </div>
 <div class="side">
  <div class="glass card"><h3>Game</h3><div class="gm"><div class="gi" id="gicon">🎮</div><div style="min-width:0"><div class="big" id="gname">Game</div><div class="sub" id="place">—</div></div></div>
   <div class="row"><button onclick="document.getElementById('pm').classList.add('show');pid.value=cur.place;pid.focus()">Change</button><button onclick="api.tile()">Tile</button></div></div>
  <div class="glass card"><h3>Auto reconnect</h3>
   <div class="sw" id="auto" onclick="api.set_auto(!this.classList.contains('on'));this.classList.toggle('on')"><span>Rejoin accounts that drop</span><i></i></div>
   <label class="l">Check every <b id="ivl">60</b>s</label><input type="range" id="iv" min="10" max="600" step="5">
   <label class="l">After reconnect, click (Event on)</label><input type="text" id="cl" placeholder="Button name, e.g. Pumpkin Tycoon">
   <label class="l">Wait <b id="dll">25</b>s after reconnecting</label><input type="range" id="dl" min="5" max="90">
   <div class="row" style="margin-top:10px"><button class="pri" id="pk" onclick="api.pick_click()" style="flex:1">Pick button</button><button onclick="api.test_click()">Test</button></div></div>
  <div class="glass card"><h3>Anti-AFK</h3>
   <div class="sw" id="afk" onclick="api.set_afk(!this.classList.contains('on'));this.classList.toggle('on')"><span>Stop the 20-min idle kick</span><i></i></div>
   <label class="l">Nudge every <b id="afl">10</b> min</label><input type="range" id="af" min="2" max="18"></div>
  <div class="glass card"><h3>Style</h3><div class="chips" id="sty"></div><h3 style="margin-top:14px">Colour</h3><div class="sws" id="sws"></div></div>
  <div class="glass card"><h3>Activity</h3><div class="log" id="log"><span>Nothing yet</span></div></div>
 </div>
</div>
<div class="modal" id="am"><div class="glass"><h3 id="amt">Add account</h3><input type="text" id="an" placeholder="Name"><input type="password" id="ac" placeholder=".ROBLOSECURITY cookie">
 <div class="row" style="justify-content:flex-end"><button onclick="am.classList.remove('show')">Cancel</button><button class="pri" onclick="doAdd()">Add</button></div></div></div>
<div class="modal" id="pm"><div class="glass"><h3>Place ID</h3><input type="text" id="pid">
 <div class="row" style="justify-content:flex-end"><button onclick="pm.classList.remove('show')">Cancel</button><button class="pri" onclick="api.set_place(pid.value);pm.classList.remove('show')">Save</button></div></div></div>
<div id="toast"></div>
<script>
const P={
glass:[['Cyan','#06b6d4','#67e8f9'],['Rose','#ff5fa2','#ff9ad0'],['Mint','#2fd48a','#8af0c0'],['Violet','#9a6bff','#d0a8ff'],['Ruby','#ff5a5a','#ffa0a0']],
glossy:[['Sapphire','#2f6bff','#6fb1ff'],['Ruby','#e0204a','#ff7a8f'],['Emerald','#10b870','#6fe8b0'],['Amethyst','#8a3fe0','#c58bff'],['Gold','#e8a410','#ffd86b']],
cartoon:[['Mango','#ff9f1c','#ffd166'],['Bubblegum','#ff5d9e','#ffa3c8'],['Mint','#2ec4b6','#8be8de'],['Sky','#3a86ff','#8ecbff'],['Grape','#8338ec','#c19bff']],
retro:[['Amber','#ffb000','#ffd36b'],['Phosphor','#33ff66','#9dffb8'],['Cyan','#2fe6ff','#9af3ff'],['Magenta','#ff3df0','#ff9af7'],['Paper','#e8e2d0','#ffffff']],
neon:[['Cyan','#00f0ff','#7a5cff'],['Magenta','#ff2bd6','#ff8a3d'],['Lime','#b6ff00','#00ff9d'],['Violet','#a855ff','#ff4fd8'],['Orange','#ff7a00','#ffd000']],
clean:[['Sky','#3b82f6','#60a5fa'],['Rose','#f43f5e','#fb7185'],['Sage','#10b981','#6ee7b7'],['Lavender','#8b5cf6','#c4b5fd'],['Peach','#fb923c','#fdba74']]};
const STY=[['glass','Glass'],['glossy','Glossy'],['cartoon','Cartoon'],['retro','Retro'],['neon','Neon'],['clean','Clean']];
let cs='glass',cc=0;
let cur={place:''},api=null,last='';
const $=id=>document.getElementById(id),esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function look(st,ci){const c=P[st][ci],r=document.documentElement;r.dataset.s=st;r.style.setProperty('--a',c[1]);r.style.setProperty('--b',c[2]);
 $('sty').innerHTML=STY.map(x=>`<button class="chip ${x[0]==st?'sel':''}" data-st="${x[0]}">${x[1]}</button>`).join('');
 $('sws').innerHTML=P[st].map((x,i)=>`<b data-c="${i}" title="${x[0]}" class="${i==ci?'sel':''}" style="background:linear-gradient(135deg,${x[1]},${x[2]})"></b>`).join('')}
$('sty').onclick=e=>{const st=e.target.dataset.st;if(st){cs=st;look(cs,cc);api.set_style(st)}};
$('sws').onclick=e=>{const c=e.target.dataset.c;if(c!==undefined){cc=+c;look(cs,cc);api.set_color(cc)}};
function render(s){cur=s;if(s.style!=cs||s.color!=cc||!$('sws').children.length){cs=s.style;cc=s.color;look(cs,cc)}$('place').textContent='place '+s.place;$('gname').textContent=s.game.name||'Game';if($('gicon').dataset.u!==s.game.icon){$('gicon').dataset.u=s.game.icon;$('gicon').innerHTML=s.game.icon?`<img src="${esc(s.game.icon)}" onerror="this.remove()">`:'🎮'}$('auto').classList.toggle('on',s.auto);$('afk').classList.toggle('on',s.afk.on);$('multi').innerHTML=s.multi.ok?'<span style="color:#3be08a">● Multi-instance ready</span>':'<span style="color:#ff9a9a">● '+esc(s.multi.msg)+'</span>';if(document.activeElement!==$('af')){$('af').value=s.afk.every;$('afl').textContent=s.afk.every}
 if(document.activeElement!==$('iv')){$('iv').value=s.interval;$('ivl').textContent=s.interval}
 if(document.activeElement!==$('cl'))$('cl').value=s.click.label;if(document.activeElement!==$('dl')){$('dl').value=s.click.delay;$('dll').textContent=s.click.delay}$('pk').textContent=s.click.set?'Re-pick button ✓':'Pick button';
 const on=s.accounts.filter(a=>a.status=='playing').length;const rj=s.accounts.reduce((t,x)=>t+x.rejoins,0),n=s.accounts.length;$('count').innerHTML=`<span class="stat on"><b>${on}</b> online</span><span class="stat"><b>${n}</b> account${n==1?'':'s'}</span><span class="stat"><b>${rj}</b> rejoin${rj==1?'':'s'}</span>`;
 $('log').innerHTML=s.logs.length?s.logs.map(l=>`<div><b>${l[0]}</b>${esc(l[1])}</div>`).join(''):'<span>Nothing yet</span>';
 const p=s.accounts.filter(a=>a.status=='playing').map(a=>a.name);$('still').textContent=p.length?'still playing: '+p.join(', '):'nobody playing';
 const q=$('q').value.trim().toLowerCase(),L=s.accounts.filter(a=>!q||a.name.toLowerCase().includes(q)||(a.user||'').toLowerCase().includes(q));const k=JSON.stringify(L)+q;if(k===last)return;last=k;
 $('list').innerHTML=L.length?L.map(a=>`<div class="acc ${a.status}"><div class="av">${esc(a.name[0].toUpperCase())}${a.avatar?`<img src="${esc(a.avatar)}" onerror="this.remove()">`:''}</div>
 <div class="info"><div class="nm">${esc(a.name)}${a.expired?'<span class="badge">COOKIE EXPIRED</span>':''}</div><div class="st"><span class="tag ${a.status}"><span class="dot"></span>${a.status=='playing'?'Playing':a.status=='working'?'Joining…':'Offline'}</span>${a.user?' · @'+esc(a.user):''}</div><div class="meta">${a.status=='playing'&&a.since?'⏱ <span data-since="'+a.since+'"></span>':''}${a.rejoins?' · '+a.rejoins+' rejoin'+(a.rejoins>1?'s':''):''}</div></div>
 <div class="tg"><div class="sw ${a.rejoin?'on':''}" data-n="${esc(a.name)}" data-k="rejoin"><span>Rejoin</span><i></i></div><div class="sw ${a.event?'on':''}" data-n="${esc(a.name)}" data-k="event"><span>Event</span><i></i></div></div>
 <button class="${a.status=='playing'?'':'pri'}" data-n="${esc(a.name)}" data-a="${a.status=='playing'?'leave':'join'}">${a.status=='playing'?'Leave':'Join'}</button>
 <button class="ic" data-n="${esc(a.name)}" data-a="edit">✎</button><button class="ic" data-n="${esc(a.name)}" data-a="remove">🗑</button></div>`).join(''):
 (s.accounts.length?'<div class="empty">No matching accounts</div>':'<div class="empty"><div class="eico">☠</div>No accounts yet<br>Click <b>+ Account</b> to log in and add one</div>')}
$('list').onclick=e=>{const sw=e.target.closest('.sw');if(sw)return api.toggle(sw.dataset.n,sw.dataset.k);
 const b=e.target.closest('button');if(!b)return;const n=b.dataset.n,a=b.dataset.a;
 if(a=='remove'){if(confirm('Remove '+n+'?'))api.remove(n)}else if(a=='edit')openEdit(n);else api[a](n)};
$('iv').oninput=()=>$('ivl').textContent=$('iv').value;$('iv').onchange=()=>api.set_interval(+$('iv').value);
$('af').oninput=()=>$('afl').textContent=$('af').value;$('af').onchange=()=>api.set_afk_every(+$('af').value);
$('cl').onchange=()=>api.set_click_label($('cl').value);$('dl').oninput=()=>$('dll').textContent=$('dl').value;$('dl').onchange=()=>api.set_click_delay(+$('dl').value);
let editing=null;
function openAdd(){editing=null;amt.textContent='Add account';ac.placeholder='.ROBLOSECURITY cookie';an.value=ac.value='';am.classList.add('show');an.focus()}
function openEdit(n){editing=n;amt.textContent='Edit account';ac.placeholder='New cookie (leave empty to keep current)';an.value=n;ac.value='';am.classList.add('show');ac.focus()}
function doAdd(){editing?api.edit(editing,an.value,ac.value):api.add(an.value,ac.value);am.classList.remove('show')}
let tt;function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>t.classList.remove('show'),3200)}
$('q').oninput=()=>{last='';render(cur)};
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key=='f'){e.preventDefault();$('q').focus()}if(e.key=='Escape')document.querySelectorAll('.modal.show').forEach(x=>x.classList.remove('show'));
 if(e.key=='Enter'&&am.classList.contains('show'))doAdd();if(e.key=='Enter'&&pm.classList.contains('show')){api.set_place(pid.value);pm.classList.remove('show')}});
const fmt=s=>{const h=s/3600|0,mi=s%3600/60|0;return h?h+'h '+mi+'m':mi?mi+'m '+(s%60)+'s':s+'s'};
setInterval(()=>document.querySelectorAll('[data-since]').forEach(e=>e.textContent=fmt(Math.max(0,Math.floor(Date.now()/1000-e.dataset.since)))),1000);
window.addEventListener('pywebviewready',()=>{api=pywebview.api;api.init()});
</script></body></html>"""

if __name__ == "__main__":
    window = webview.create_window(TITLE, html=HTML, js_api=api, width=1040, height=720,
                                   min_size=(820, 540), background_color="#090b16")
    window.events.shown += dark_title
    threading.Thread(target=loops, daemon=True).start()
    threading.Thread(target=presence_loop, daemon=True).start()
    threading.Thread(target=afk_loop, daemon=True).start()
    webview.start()
