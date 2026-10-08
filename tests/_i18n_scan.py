"""DOM-level English check for dashboard.html.

`tests/_test_panel_english.js` proves statically that the panel's own copy is
English. It cannot see the strings the app builds at runtime out of server
payloads, and the panel is only half the story: a toast carrying `/accounts`
text, an upstream error hint, or a raw gateway log line all land in the DOM in
Chinese, by design (the gateway is a Chinese-language project).

This harness drives the real page instead: synthetic fixtures (fake accounts,
fake usage - never real credentials), the gateway on a loopback port, Firefox
via Playwright, every tab and a few interactive surfaces exercised, then the
whole DOM walked for text nodes and i18n attributes that still contain Han
characters. The surfaces that carry server text are skipped by id and listed in
`SERVER_TEXT` below - everything else must be English.

Usage:
    python3 tests/_i18n_scan.py            # scan every surface
    python3 tests/_i18n_scan.py settings   # only surfaces whose name contains "settings"

It is a hand-run harness like `_mobile_check.py`: it needs Playwright
(`pip install playwright && playwright install firefox`) and is not part of
`tests/run_all.py`.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

FIX = os.path.join(tempfile.gettempdir(), "i18n-fixtures")
PASSWORD = "testpass123"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 0
BASE = ""

# Walks the DOM and returns everything that still contains a Han character.
# Surfaces fed by the Python side are skipped on purpose - they are Chinese by
# design and out of scope for the panel's English copy:
#   logTerminalBody  raw gateway log lines
#   toastBox         toasts, most of which carry a server message
#   disabledList     the disabled overview's reason column (upstream errors)
#   [data-tip]       upstream error text on hover
SCAN_JS = r"""
(() => {
  const HAN = /[\u4e00-\u9fff]/;
  const ATTRS = ['title', 'placeholder', 'aria-label', 'data-label', 'alt'];
  const SKIP = {SCRIPT: 1, STYLE: 1, TEXTAREA: 1, NOSCRIPT: 1};
  const SERVER_TEXT = {logTerminalBody: 1, toastBox: 1, disabledList: 1};
  const out = [];
  const allowed = el => {
    while (el && el.nodeType === 1) {
      if (SKIP[el.tagName]) return false;
      if (SERVER_TEXT[el.id]) return false;
      if (el.hasAttribute && el.hasAttribute('data-tip')) return false;
      el = el.parentNode;
    }
    return true;
  };
  const path = el => {
    const bits = [];
    while (el && el.nodeType === 1 && bits.length < 4) {
      bits.unshift(el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''));
      el = el.parentNode;
    }
    return bits.join('>');
  };
  const walk = node => {
    if (node.nodeType === 3) {
      if (node.data && HAN.test(node.data) && allowed(node.parentNode)) {
        out.push({where: path(node.parentNode), text: node.data.replace(/\s+/g, ' ').trim()});
      }
      return;
    }
    if (node.nodeType !== 1 || !allowed(node)) return;
    for (const a of ATTRS) {
      if (node.hasAttribute(a)) {
        const v = node.getAttribute(a);
        if (HAN.test(v)) out.push({where: path(node) + '@' + a, text: v});
      }
    }
    for (const kid of node.childNodes) walk(kid);
  };
  walk(document.documentElement);
  if (document.title && HAN.test(document.title)) {
    out.push({where: 'title', text: document.title});
  }
  return out;
})()
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_fixtures():
    """Synthetic state that makes every conditional branch render.

    Disabled, cooling down, over the daily token limit, over the credit limit
    and a package about to expire: each one paints its own badge, and every
    badge carries Chinese copy built in JavaScript.
    """
    if os.path.isdir(FIX):
        shutil.rmtree(FIX)
    acc = os.path.join(FIX, "accounts")
    use = os.path.join(FIX, "usage")
    os.makedirs(acc)
    os.makedirs(use)
    now = time.time()

    def account(uid, nick, realm, **kw):
        row = {
            "uid": uid,
            "nickname": nick,
            "domain": "www.workbuddy.ai" if realm == "intl" else "www.codebuddy.cn",
            "realm": realm,
            "platform": "CLI",
            "enterpriseId": "",
            "accessToken": "",
            "refreshToken": "",
            "expiresAt": int(now) + 86400 * 30,
            "addedAt": now - 3600,
            "source": "oauth",
            "enabled": True,
            "lastError": "",
            "cooldownUntil": 0,
            "proxySlot": "",
            "proxy": "",
            "credits": {"remain": 42, "used": 8, "size": 50, "packages": []},
            "lastCheckin": None,
        }
        row.update(kw)
        return row

    accounts = [
        account("11111111-1111-1111-1111-111111111111", "test-user-a", "intl",
                proxySlot="slot-1"),
        account("22222222-2222-2222-2222-222222222222", "test-user-b", "intl",
                enabled=False, lastError="HTTP 403"),
        account("33333333-3333-3333-3333-333333333333", "test-user-cn", "cn"),
        account("44444444-4444-4444-4444-444444444444", "test-user-d", "intl",
                cooldownUntil=now + 45, lastError="HTTP 429"),
        account("55555555-5555-5555-5555-555555555555", "test-user-e", "cn",
                credits={"remain": 1, "used": 49, "size": 50, "packages": [
                    {"name": "monthly", "size": 50, "used": 49, "remain": 1,
                     "cycle_end_time": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                     time.localtime(now + 86400 * 2)),
                     "status": "active"}]}),
    ]
    for row in accounts:
        with open(os.path.join(acc, row["uid"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(row, fh, ensure_ascii=False, indent=2)

    settings = {
        "proxy_slots": [
            {"id": "slot-1", "name": "槽 1", "url": "http://test-proxy:17901", "enabled": True},
            {"id": "slot-2", "name": "槽 2", "url": "http://test-proxy:17902", "enabled": True},
        ],
        "limits": {
            "reserve_credits": {"global": 10, "intl": 3, "cn": None},
            "daily_token_limit": {"global": 1000, "intl": None, "cn": None},
            "daily_credit_limit": {"global": 0, "intl": None, "cn": None},
            "model_daily_token_limit": {"global": 0, "intl": None, "cn": None},
        },
    }
    with open(os.path.join(acc, "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(use, "usage.jsonl"), "w", encoding="utf-8") as fh:
        for i in range(40):
            ts = now - (40 - i) * 60
            fh.write(json.dumps({
                "at": ts,
                "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts)),
                "model": "deepseek-v4.1-flash" if i % 3 else "glm-5.3",
                "stream": i % 2 == 0,
                "reasoning_effort": "high" if i % 4 == 0 else "",
                "elapsed_ms": 4200 + i * 30,
                "ttft_ms": 1500 + i * 20,
                "gen_ms": 800,
                "prompt_tokens": 12000 + i * 50,
                "completion_tokens": 200 + i,
                "reasoning_tokens": i % 5,
                "cached_tokens": 9000 + i * 40,
                "total_tokens": 12200 + i * 51,
                "credit": 1.5 if i % 5 == 0 else 0,
                "cache_hit_pct": 75,
                "tokens_per_sec": 42.5,
                "account": "11111111-1111-1111-1111-111111111111" if i % 2
                           else "33333333-3333-3333-3333-333333333333",
                "realm": "intl" if i % 2 else "cn",
            }, ensure_ascii=False) + "\n")


def wait_identity(timeout=25):
    import urllib.request

    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "/panel/status", timeout=2) as r:
                if "panel_password_required" in json.loads(r.read().decode()):
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def start_server():
    for host in ("127.0.0.1", "::"):
        proc = subprocess.Popen(
            [sys.executable, "wb_proxy.py", "--host", host, "--port", str(PORT),
             "--accounts-dir", os.path.join(FIX, "accounts"),
             "--usage-dir", os.path.join(FIX, "usage"),
             "--panel-password", PASSWORD],
            cwd=ROOT, env=dict(os.environ),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if wait_identity():
            return proc
        proc.kill()
        proc.wait()
    raise SystemExit("gateway did not answer on port %d" % PORT)


def login(page):
    page.goto(BASE + "/", timeout=20000)
    page.wait_for_timeout(1200)
    if page.locator("#panelPwdInput").count():
        page.fill("#panelPwdInput", PASSWORD)
        page.click("button:has-text('Enter dashboard')")
        page.wait_for_timeout(1500)


def goto_tab(page, tab):
    page.click({"gateway": "#btnNavGateway", "analytics": "#btnNavAnalytics",
                "logs": "#btnNavLogs", "settings": "#btnNavSettings"}[tab])
    page.wait_for_timeout(900)


def scan(page, surface, found):
    for item in page.evaluate(SCAN_JS):
        found.append((surface, item["where"], item["text"]))


# Every Chinese string the panel endpoints hand to the page. Anything the page
# prints that contains one of these is server text, not the panel's own copy:
# the scheduler's description, a proxy slot's name, an API key's name, the
# unattributed bucket's label. Collected from the running gateway rather than
# listed by hand, so a new server-side label needs no change here.
SERVER_STRINGS_JS = r"""
(async () => {
  const urls = ['/accounts', '/scheduler', '/proxy/slots', '/usage/analytics',
                '/usage/recent', '/settings', '/pricing', '/models'];
  const out = [];
  const walk = (v) => {
    if (typeof v === 'string') { if (/[\u4e00-\u9fff]/.test(v)) out.push(v.replace(/\s+/g, ' ').trim()); return; }
    if (Array.isArray(v)) { v.forEach(walk); return; }
    if (v && typeof v === 'object') Object.keys(v).forEach(k => walk(v[k]));
  };
  for (const url of urls) {
    try { walk(await getJSON(url)); } catch (e) { /* endpoint optional */ }
  }
  return out;
})()
"""


def server_strings(page):
    try:
        return [s for s in page.evaluate(SERVER_STRINGS_JS) if s]
    except Exception:
        return []


def dom_click(page, selector):
    """Click through the DOM instead of the mouse.

    The capsule switches hide the real checkbox under a styled track, so a
    pointer click lands on the track and Playwright waits forever for it to
    become the hit target. A DOM click fires the same change handler.
    """
    return page.evaluate(
        "sel => { const el = document.querySelector(sel); if(!el) return false;"
        " el.click(); return true; }", selector)


def exercise_gateway(page, found):
    scan(page, "gateway", found)
    # Account cards: each state badge and the tooltip behind it are built in JS,
    # and every upstream call answers with an error under these fixtures - which
    # is the point, since those toasts carry the server's own text.
    for label in ("Test", "Refresh token", "Sync nickname"):
        btn = page.locator("#accounts button:has-text('%s')" % label).first
        if btn.count():
            btn.click()
            page.wait_for_timeout(1200)
            scan(page, "gateway/toast", found)


def exercise_analytics(page, found):
    scan(page, "analytics", found)
    btn = page.locator("button[onclick=\"loadCreditHistory(this)\"]").first
    if btn.count():
        btn.click()
        page.wait_for_timeout(1200)
    scan(page, "analytics/refresh", found)


def exercise_settings(page, found):
    scan(page, "settings", found)
    # The limits table renders its per-realm columns and badges on demand.
    if dom_click(page, "#setLimitsPerRealm"):
        page.wait_for_timeout(400)
        scan(page, "settings/limits-per-realm", found)
    # Turning estimation off swaps the section for its off-note.
    if dom_click(page, "#setPricingEnabled"):
        page.wait_for_timeout(900)
        scan(page, "settings/pricing-off", found)
        dom_click(page, "#setPricingEnabled")
        page.wait_for_timeout(900)


def exercise_logs(page, found):
    scan(page, "logs", found)


def main(argv):
    global PORT, BASE
    only = argv[1] if len(argv) > 1 else ""
    PORT = free_port()
    BASE = "http://127.0.0.1:%d" % PORT

    build_fixtures()
    sys.path.insert(0, ROOT)
    import wb_settings

    wb_settings.set_panel_password(os.path.join(FIX, "accounts"), PASSWORD)

    from playwright.sync_api import sync_playwright

    proc = start_server()
    found = []
    scanned = 0
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            login(page)
            page.wait_for_timeout(1200)
            # Collected twice: a value the page rendered early (the scheduler's
            # "not run yet" placeholder) is gone from the payload by the time the
            # scan is over, and vice versa.
            from_server = server_strings(page)

            for name, fn, tab in (("gateway", exercise_gateway, "gateway"),
                                  ("analytics", exercise_analytics, "analytics"),
                                  ("settings", exercise_settings, "settings"),
                                  ("logs", exercise_logs, "logs")):
                if only and only not in name:
                    continue
                goto_tab(page, tab)
                fn(page, found)
            scanned = page.evaluate("document.querySelectorAll('*').length")
            for text in server_strings(page):
                if text not in from_server:
                    from_server.append(text)
            browser.close()
    finally:
        proc.kill()
        proc.wait()

    print("scanned %d elements, %d Chinese string(s) known to come from the server"
          % (scanned, len(from_server)))
    # A string the page printed is not the panel's copy when it contains a
    # string the server sent (a composed line such as "Running · <server text>")
    # or when the server sent it verbatim.
    def server_text(text):
        return any(s in text or text in s for s in from_server)

    offenders = [(s, w, t) for s, w, t in found if not server_text(t)]
    if not offenders:
        print("  [PASS] no Chinese copy left in the panel")
        return 0
    seen = set()
    for surface, where, text in offenders:
        key = (where, text)
        if key in seen:
            continue
        seen.add(key)
        print("  [FAIL] %-22s %-28s %s" % (surface, where, text[:90]))
    print("  %d Chinese string(s) of panel copy still rendered" % len(seen))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
