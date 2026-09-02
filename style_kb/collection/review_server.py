#!/usr/bin/env python3
"""本地審查伺服器：瀏覽器重整就自動從 DB 拉最新資料。

Usage (from project root):
    # DB 品質審查模式（原有）
    python -m style_kb.collection.review_server
    python -m style_kb.collection.review_server --flagged-only

    # Caption 人工審核模式（先跑 generate_captions --dry-run）
    python -m style_kb.collection.review_server --from-json
    python -m style_kb.collection.review_server --from-json caption_review.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.stdout.reconfigure(encoding="utf-8")

_root = __file__
for _ in range(3):
    _root = os.path.dirname(_root)
sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))
load_dotenv()

from style_kb.collection.generate_review import build_html, fetch_rows, fetch_style_counts
from style_kb.collection.generate_captions import move_storage_file

FLAGGED_ONLY = False
JSON_PATH: str | None = None   # set when --from-json is used


# ── JSON 審核模式 helpers ──────────────────────────────────────────────────────

def _load_json_items() -> list[dict]:
    if not JSON_PATH or not os.path.exists(JSON_PATH):
        return []
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_json_items(items: list[dict]) -> None:
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _build_json_html(items: list[dict]) -> str:
    n = len(items)
    cards_json = json.dumps(items, ensure_ascii=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Use placeholder substitution to avoid f-string brace escaping in CSS/JS
    TMPL = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Caption 人工審核</title>
<style>
* { box-sizing:border-box; margin:0; padding:0 }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       background:#0f172a; color:#e2e8f0; padding-bottom:80px }
.header { background:#1e293b; padding:16px 24px; border-bottom:1px solid #334155;
          position:sticky; top:0; z-index:100; display:flex; align-items:center; gap:16px; flex-wrap:wrap }
.header h1 { font-size:18px; font-weight:700; color:#f1f5f9 }
.stat { font-size:13px; color:#94a3b8 }
.stat b { color:#f1f5f9 }
.top-actions { margin-left:auto; display:flex; gap:8px }
.btn { padding:8px 16px; border-radius:8px; border:none; cursor:pointer; font-size:13px; font-weight:600 }
.btn-approve-all { background:#059669; color:#fff }
.btn-approve-all:hover { background:#047857 }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
        gap:16px; padding:20px 24px }
.card { background:#1e293b; border-radius:10px; overflow:hidden;
        border:2px solid #334155; transition:all .2s }
.card.done { border-color:#059669; opacity:.45; pointer-events:none }
.thumb { width:100%; aspect-ratio:4/3; object-fit:cover; display:block; background:#0f172a }
.card-body { padding:12px; display:flex; flex-direction:column; gap:8px }
.orig { font-size:11px; color:#64748b }
.field label { font-size:11px; color:#94a3b8; display:block; margin-bottom:3px }
.conf { float:right; font-size:10px; color:#475569 }
.ai-sel, .ai-ta {
  width:100%; background:#0f172a; border:1px solid #334155;
  color:#e2e8f0; border-radius:6px; padding:6px 8px; font-size:12px; font-family:inherit
}
.ai-ta { resize:vertical; min-height:80px }
.card-actions { display:flex; gap:8px; margin-top:4px }
.btn-ok { flex:1; background:#6366f1; color:#fff; border:none;
          border-radius:6px; padding:8px; font-size:13px; font-weight:600; cursor:pointer }
.btn-ok:hover { background:#4f46e5 }
.btn-skip { background:#334155; color:#94a3b8; border:none;
            border-radius:6px; padding:8px 12px; font-size:13px; cursor:pointer }
.btn-skip:hover { background:#475569; color:#fff }
.btn-del { background:#450a0a; color:#fca5a5; border:1px solid #7f1d1d;
           border-radius:6px; padding:8px 10px; font-size:13px; cursor:pointer }
.btn-del:hover { background:#7f1d1d; color:#fff }
.empty { text-align:center; padding:80px; color:#475569; font-size:16px }
::-webkit-scrollbar { width:6px }
::-webkit-scrollbar-track { background:#0f172a }
::-webkit-scrollbar-thumb { background:#334155; border-radius:3px }
</style>
</head>
<body>
<div class="header">
  <h1>Caption 人工審核</h1>
  <span class="stat">待審核 <b id="remaining">__COUNT__</b> 筆</span>
  <span class="stat" style="font-size:11px;color:#475569">__NOW__</span>
  <div class="top-actions">
    <button class="btn btn-approve-all" onclick="approveAll()">批准全部</button>
  </div>
</div>
<div class="grid" id="grid"></div>

<script>
const ITEMS = __CARDS_JSON__;
const STYLE_OPT = ["modern","nordic","japanese","industrial","american","classic","luxury","country","other"];
const SPACE_OPT = ["客廳","臥室","廚房","浴室","餐廳","書房","走道","玄關","陽台","辦公室","其他"];
const STYLE_ZH = {modern:"現代",nordic:"北歐",japanese:"日式",industrial:"工業",american:"美式",classic:"古典",luxury:"奢華",country:"鄉村",other:"其他"};
const state = {};

function mkOpts(options, zhMap, selected) {
  return options.map(s => {
    const label = zhMap ? (zhMap[s]||s) : s;
    const sel = s === selected ? ' selected' : '';
    return `<option value="${s}"${sel}>${label}</option>`;
  }).join('');
}

function renderGrid() {
  const grid = document.getElementById("grid");
  if (!ITEMS.length) {
    grid.innerHTML = '<div class="empty">🎉 全部審核完畢！</div>';
    return;
  }
  ITEMS.forEach(item => {
    state[item.id] = {
      caption_en: item.caption_en || "",
      space:      item.space      || "",
      style_id:   item.style_id   || item.original_style_id || "",
    };
    const confPct = item.ai_style_confidence != null
      ? Math.round(item.ai_style_confidence * 100) + "%"
      : "";

    const card = document.createElement("div");
    card.className = "card"; card.id = "card-" + item.id;

    // Image
    const img = document.createElement("img");
    img.className = "thumb"; img.loading = "lazy"; img.src = item.image_url;
    img.onerror = () => { img.style.display = "none"; };

    // Body
    const body = document.createElement("div");
    body.className = "card-body";
    body.innerHTML = `<div class="orig">原始：${STYLE_ZH[item.original_style_id]||item.original_style_id}</div>`;

    // AI Style
    const sf = document.createElement("div"); sf.className = "field";
    sf.innerHTML = `<label>AI 風格 <span class="conf">${confPct}</span></label>
      <select class="ai-sel">${mkOpts(STYLE_OPT, STYLE_ZH, state[item.id].style_id)}</select>`;
    sf.querySelector("select").onchange = e => state[item.id].style_id = e.target.value;

    // Space type
    const spf = document.createElement("div"); spf.className = "field";
    spf.innerHTML = `<label>空間類型</label>
      <select class="ai-sel">${mkOpts(SPACE_OPT, null, state[item.id].space)}</select>`;
    spf.querySelector("select").onchange = e => state[item.id].space = e.target.value;

    // Caption
    const cf = document.createElement("div"); cf.className = "field";
    const ta = document.createElement("textarea");
    ta.className = "ai-ta"; ta.rows = 4; ta.value = item.caption_en || "";
    ta.oninput = e => state[item.id].caption_en = e.target.value;
    cf.innerHTML = "<label>Caption</label>";
    cf.appendChild(ta);

    // Buttons
    const acts = document.createElement("div"); acts.className = "card-actions";
    const okBtn = document.createElement("button"); okBtn.className = "btn-ok"; okBtn.textContent = "✓ 批准";
    okBtn.onclick = () => approveOne(item.id, okBtn);
    const skipBtn = document.createElement("button"); skipBtn.className = "btn-skip"; skipBtn.textContent = "跳過";
    skipBtn.onclick = () => skipOne(item.id, card);
    const delBtn = document.createElement("button"); delBtn.className = "btn-del"; delBtn.textContent = "🗑";
    delBtn.title = "刪除圖片（Storage + DB）";
    delBtn.onclick = () => deleteOne(item.id, delBtn);

    acts.appendChild(okBtn); acts.appendChild(skipBtn); acts.appendChild(delBtn);
    body.appendChild(sf); body.appendChild(spf); body.appendChild(cf); body.appendChild(acts);
    card.appendChild(img); card.appendChild(body);
    grid.appendChild(card);
  });
}

async function approveOne(id, btn) {
  btn.disabled = true; btn.textContent = "儲存中...";
  const ok = await submit([{ id, ...state[id] }]);
  if (ok) {
    document.getElementById("card-" + id).classList.add("done");
    btn.textContent = "✓ 已批准";
    updateCount(-1);
  } else {
    btn.textContent = "❌ 失敗"; btn.disabled = false;
  }
}

async function approveAll() {
  const allBtn = document.querySelector(".btn-approve-all");
  const pending = ITEMS.filter(i => !document.getElementById("card-"+i.id)?.classList.contains("done"));
  if (!pending.length) return;
  allBtn.disabled = true; allBtn.textContent = `處理中 (0/${pending.length})...`;
  const payload = pending.map(i => ({
    id: i.id,
    ...state[i.id],
    original_style_id: i.original_style_id,
    image_path:        i.image_path,
    caption_model:     i.caption_model,
  }));
  const ok = await submit(payload);
  if (ok) {
    pending.forEach(i => document.getElementById("card-"+i.id)?.classList.add("done"));
    updateCount(-pending.length);
    allBtn.textContent = `✓ 已批准 ${pending.length} 筆`;
  } else {
    allBtn.textContent = "❌ 批准失敗";
    allBtn.disabled = false;
    alert("批准失敗，請查看伺服器終端機的錯誤訊息。");
  }
}

async function deleteOne(id, btn) {
  if (!confirm("確定永久刪除此圖片（Storage + DB）？")) return;
  btn.disabled = true; btn.textContent = "刪除中...";
  try {
    const r = await fetch("/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const data = await r.json();
    if (data.ok) {
      document.getElementById("card-" + id)?.remove();
      updateCount(-1);
    } else {
      btn.textContent = "❌"; btn.disabled = false;
      alert("刪除失敗：" + (data.error || "未知錯誤"));
    }
  } catch(e) { console.error(e); btn.textContent = "❌"; btn.disabled = false; }
}

async function skipOne(id, card) {
  card.classList.add("done");
  try {
    await fetch("/skip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
  } catch(e) { console.error(e); }
}

async function submit(items) {
  try {
    const r = await fetch("/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    return (await r.json()).ok;
  } catch(e) { console.error(e); return false; }
}

function updateCount(delta) {
  const el = document.getElementById("remaining");
  el.textContent = Math.max(0, parseInt(el.textContent) + delta);
}

renderGrid();
</script>
</body>
</html>"""

    return (TMPL
            .replace("__COUNT__", str(n))
            .replace("__NOW__", now)
            .replace("__CARDS_JSON__", cards_json))


# ── HTTP Handler ───────────────────────────────────────────────────────────────

class ReviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 重新拉取資料...")
        try:
            if JSON_PATH:
                items = _load_json_items()
                html = _build_json_html(items)
                print(f"  ✅ JSON 模式，待審核 {len(items)} 筆")
            else:
                rows = fetch_rows(style=None, show_all=not FLAGGED_ONLY)
                db_counts = fetch_style_counts()
                html = build_html(rows, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), db_counts)
                print(f"  ✅ 完成，共 {len(rows)} 張")

            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            msg = f"<pre>Error: {e}</pre>".encode()
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
        except Exception as e:
            self._json_resp(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/approve":
            self._handle_approve(body)
        elif self.path == "/save":
            self._handle_save(body)
        elif self.path == "/delete":
            self._handle_delete(body)
        elif self.path == "/skip":
            self._handle_skip(body)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_approve(self, body: dict) -> None:
        """批准 JSON 審核清單：寫進 DB，從 JSON 檔移除。"""
        items = body.get("items", [])
        if not items:
            self._json_resp(200, {"ok": True, "approved": 0})
            return
        try:
            from style_kb.collection.generate_review import get_supabase
            client = get_supabase()
            now = datetime.now(timezone.utc).isoformat()
            for item in items:
                row_id = item.get("id")
                if not row_id:
                    continue
                update = {
                    "caption_en":    item.get("caption_en"),
                    "space":         item.get("space"),
                    "style_id":      item.get("style_id"),
                    "caption_model": item.get("caption_model", "gemini-2.5-flash"),
                    "caption_at":    now,
                }
                # 風格改變時搬 Storage 檔案
                new_style = item.get("style_id")
                old_style = item.get("original_style_id")
                image_path = item.get("image_path")
                if new_style and old_style and new_style != old_style and image_path:
                    update.update(move_storage_file(client, image_path, new_style))
                client.table("style_images").update(update).eq("id", row_id).execute()

            # 從 JSON 檔移除已批准的 ID
            if JSON_PATH:
                approved_ids = {i["id"] for i in items if i.get("id")}
                remaining = [r for r in _load_json_items() if r["id"] not in approved_ids]
                _save_json_items(remaining)
                print(f"  ✅ 批准 {len(items)} 筆，剩餘 {len(remaining)} 筆")

            self._json_resp(200, {"ok": True, "approved": len(items)})
        except Exception as e:
            print(f"  ❌ approve error: {e}")
            self._json_resp(500, {"ok": False, "error": str(e)})

    def _handle_save(self, body: dict) -> None:
        """DB 模式單筆儲存（品質審查頁用）。"""
        try:
            row_id = body.get("id")
            if not row_id:
                raise ValueError("missing id")
            from style_kb.collection.generate_review import get_supabase
            client = get_supabase()
            allowed = {"caption_en2", "space", "style_id"}
            update = {k: v for k, v in body.items() if k in allowed}
            if not update:
                self._json_resp(200, {"ok": True})
                return
            # 風格改變時搬 Storage 檔案
            new_style = update.get("style_id")
            if new_style:
                current = client.table("style_images").select("style_id, image_path").eq("id", row_id).execute()
                if current.data:
                    old_style = current.data[0].get("style_id")
                    old_path  = current.data[0].get("image_path")
                    if old_style and old_style != new_style and old_path:
                        update.update(move_storage_file(client, old_path, new_style))
            client.table("style_images").update(update).eq("id", row_id).execute()
            self._json_resp(200, {"ok": True})
            print(f"  💾 {row_id[:8]}... 更新 {list(update.keys())}")
        except Exception as e:
            self._json_resp(500, {"ok": False, "error": str(e)})

    def _handle_skip(self, body: dict) -> None:
        """跳過：從 JSON 審核清單移除，不寫 DB。"""
        row_id = body.get("id")
        if not row_id or not JSON_PATH:
            self._json_resp(200, {"ok": True})
            return
        try:
            remaining = [r for r in _load_json_items() if r.get("id") != row_id]
            _save_json_items(remaining)
            print(f"  ⏭  {row_id[:8]}... 已跳過")
            self._json_resp(200, {"ok": True})
        except Exception as e:
            self._json_resp(500, {"ok": False, "error": str(e)})

    def _handle_delete(self, body: dict) -> None:
        """刪除單張圖片：從 Storage + DB 刪除，從 JSON 審核清單移除。"""
        row_id = body.get("id")
        if not row_id:
            self._json_resp(400, {"ok": False, "error": "missing id"})
            return
        try:
            from style_kb.collection.generate_review import get_supabase
            from style_kb.collection.generate_captions import BUCKET
            client = get_supabase()
            # 先從 JSON 或 DB 取得 image_path
            image_path = None
            if JSON_PATH:
                for item in _load_json_items():
                    if item.get("id") == row_id:
                        image_path = item.get("image_path")
                        break
            if not image_path:
                result = client.table("style_images").select("image_path").eq("id", row_id).execute()
                if result.data:
                    image_path = result.data[0].get("image_path")
            # 刪除 Storage
            if image_path:
                try:
                    client.storage.from_(BUCKET).remove([image_path])
                    print(f"  🗑 Storage 刪除：{image_path}")
                except Exception as e:
                    print(f"  ⚠️  Storage 刪除失敗（繼續刪 DB）：{e}")
            # 刪除 DB row
            client.table("style_images").delete().eq("id", row_id).execute()
            # 從 JSON 移除
            if JSON_PATH:
                remaining = [r for r in _load_json_items() if r.get("id") != row_id]
                _save_json_items(remaining)
            print(f"  🗑 {row_id[:8]}... 已刪除")
            self._json_resp(200, {"ok": True})
        except Exception as e:
            print(f"  ❌ delete error: {e}")
            self._json_resp(500, {"ok": False, "error": str(e)})

    def _json_resp(self, status: int, data: dict) -> None:
        resp = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        pass


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global FLAGGED_ONLY, JSON_PATH
    parser = argparse.ArgumentParser(description="圖片審查本地伺服器")
    parser.add_argument("--port", type=int, default=8764)
    parser.add_argument("--flagged-only", action="store_true", help="只顯示有問題的圖（DB 模式）")
    parser.add_argument("--from-json", nargs="?", const="caption_review.json",
                        metavar="PATH", help="Caption 審核模式，讀取 JSON 暫存檔")
    args = parser.parse_args()

    FLAGGED_ONLY = args.flagged_only
    JSON_PATH = os.path.join(_root, args.from_json) if args.from_json else None

    if JSON_PATH:
        n = len(_load_json_items())
        print(f"✅ Caption 審核模式：http://localhost:{args.port}")
        print(f"   來源：{JSON_PATH}（{n} 筆待審核）")
    else:
        print(f"✅ 審查伺服器啟動：http://localhost:{args.port}")
        print("   瀏覽器重整 = 自動從 DB 拉最新資料")
    print("   按 Ctrl+C 停止\n")

    import webbrowser
    webbrowser.open(f"http://localhost:{args.port}")

    server = HTTPServer(("localhost", args.port), ReviewHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n伺服器已停止")


if __name__ == "__main__":
    main()
