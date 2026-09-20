# -*- coding: utf-8 -*-
"""check_webui.py — 无头 Edge + CDP 验证 DrugAgent Web UI 并产出截图。

用法（先确保 web.py 已在 8077 端口运行）:
    .venv/Scripts/python.exe check_webui.py
产物:
    docs/screenshot_webui_start.png  初始界面
    docs/screenshot_webui_done.png   完整跑完后的结果界面
依赖: websockets（开发环境已装）
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CDP_PORT = 9799
URL = os.environ.get("DRUGAGENT_WEB", "http://127.0.0.1:8077")
BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, "docs")
TEMP = os.environ.get("TEMP", ".")


def save_png(res, path):
    data = base64.b64decode(res["data"])
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


async def main():
    import websockets

    ud = os.path.join(TEMP, f"edge_cdp_{CDP_PORT}")
    shutil.rmtree(ud, ignore_errors=True)
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
         f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={ud}",
         "--window-size=1440,2400", URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                targets = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{CDP_PORT}/json", timeout=2))
            except Exception:
                continue
            for t in targets:
                if t.get("type") == "page" and t.get("url", "").startswith("http"):
                    ws_url = t["webSocketDebuggerUrl"]
                    break
            if ws_url:
                break
        if not ws_url:
            print("ERR: devtools 端点未就绪或没有页面目标")
            return 2

        async with websockets.connect(ws_url, max_size=128 * 1024 * 1024) as ws:
            mid = 0

            async def call(method, **params):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        if "error" in msg:
                            raise RuntimeError(msg["error"])
                        return msg.get("result", {})

            async def ev(expr):
                r = await call("Runtime.evaluate", expression=expr,
                               awaitPromise=True, returnByValue=True)
                return r["result"].get("value")

            print("① 通道探针:", await ev("(async () => 'ok')()"))

            for _ in range(60):
                if await ev("!!document.getElementById('go')"):
                    break
                await asyncio.sleep(1)
            else:
                print("ERR: 页面未加载出 #go 按钮")
                return 3
            await asyncio.sleep(1.0)

            os.makedirs(DOCS, exist_ok=True)
            s1 = os.path.join(DOCS, "screenshot_webui_start.png")
            n1 = save_png(await call("Page.captureScreenshot", format="png",
                                     captureBeyondViewport=True), s1)
            print(f"② 初始截图: {s1} ({n1} B)")

            print("③ 点击开始分析…")
            await ev("(() => { document.getElementById('go').click(); return 'clicked'; })()")

            status = ""
            for _ in range(150):  # ≤ 300s
                await asyncio.sleep(2)
                status = await ev("document.getElementById('status')?.textContent || ''")
                if status and any(k in status for k in ("完成", "出错", "连接中断")):
                    break
            print("④ 状态:", status)

            for _ in range(20):  # 等图片加载完
                if await ev("[...document.images].every(i => i.complete)"):
                    break
                await asyncio.sleep(1)

            diag = await ev(
                "JSON.stringify({"
                "status: document.getElementById('status')?.textContent,"
                "marked_ok: typeof marked !== 'undefined',"
                "pills: ['p-lit','p-mol','p-rep'].map(i => document.getElementById(i).textContent),"
                "lit_len: document.getElementById('c-lit').innerHTML.length,"
                "mol_len: document.getElementById('c-mol').innerHTML.length,"
                "rep_len: document.getElementById('c-rep').innerHTML.length,"
                "imgs: document.querySelectorAll('#mol-grid img').length,"
                "imgs_ok: [...document.querySelectorAll('#mol-grid img')].filter(i => i.complete && i.naturalWidth > 0).length"
                "})")
            print("⑤ DOM 诊断:", diag)

            s2 = os.path.join(DOCS, "screenshot_webui_done.png")
            n2 = save_png(await call("Page.captureScreenshot", format="png",
                                     captureBeyondViewport=True), s2)
            print(f"⑥ 完成截图: {s2} ({n2} B)")
            ok = ("完成" in status) and ("出错" not in status)
            print("RESULT:", "PASS" if ok else "CHECK", "|", status)
            return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
