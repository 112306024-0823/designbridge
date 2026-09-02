import argparse
import os, shutil, sys, httpx, zipfile
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).parent / ".env")

parser = argparse.ArgumentParser(description="匯出 Supabase style_images 為 Flux LoRA 訓練資料集")
parser.add_argument("--style", type=str, default=None, help="只匯出指定風格，例如 nordic（預設：全部風格）")
parser.add_argument("--limit", type=int, default=None, help="最多匯出幾筆（預設：全部）")
args = parser.parse_args()

from supabase import create_client
client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

# PostgREST 單次上限 1000 筆，要分頁撈
rows, page = [], 0
while True:
    q = (client.table("style_images")
         .select("id, image_url, caption_en2, style_id")
         .not_.is_("caption_en2", "null")
         .not_.is_("image_url", "null"))
    if args.style:
        q = q.eq("style_id", args.style)
    batch = q.order("id").range(page * 1000, page * 1000 + 999).execute().data
    rows += batch
    if len(batch) < 1000:
        break
    page += 1

if args.limit:
    rows = rows[:args.limit]

# 每個風格一個 trigger word，caption 前面加上去給 Flux LoRA 訓練用
TRIGGER = {
    "modern": "dsgnbrg_modern",
    "country": "dsgnbrg_country",
    "classic": "dsgnbrg_classic",
    "nordic": "dsgnbrg_nordic",
    "industrial": "dsgnbrg_industrial",
    "japanese": "dsgnbrg_japanese",
    "american": "dsgnbrg_american",
    "luxury": "dsgnbrg_luxury",
    "neoclassic": "dsgnbrg_neoclassic",
    "other": "dsgnbrg_other",
}

print(f"共 {len(rows)} 張，開始下載...")

out = Path(__file__).parent / "dataset_export"
shutil.rmtree(out, ignore_errors=True)  # 清掉舊資料，避免跟上次不同篩選條件的殘留檔混在一起
out.mkdir(exist_ok=True)

failed = 0
for i, row in enumerate(rows):
    stem = f"{i:05d}_{row['style_id']}"
    try:
        img_bytes = httpx.get(row["image_url"], timeout=20, follow_redirects=True).content
        (out / f"{stem}.jpg").write_bytes(img_bytes)
        trig = TRIGGER.get(row["style_id"], f"dsgnbrg_{row['style_id']}")
        (out / f"{stem}.txt").write_text(f"{trig}, {row['caption_en2']}", encoding="utf-8")
        if (i + 1) % 50 == 0:
            print(f"[{i+1}/{len(rows)}] ✅")
    except Exception as e:
        failed += 1
        print(f"[{i+1}] ❌ {e}")

print(f"下載完成：{len(rows) - failed} 成功，{failed} 失敗")

zip_name = f"designbridge_dataset_{args.style}.zip" if args.style else "designbridge_dataset.zip"
zip_path = Path(__file__).parent / zip_name
print("打包中...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(out.iterdir()):
        zf.write(f, f.name)

size_mb = zip_path.stat().st_size / 1e6
print(f"✅ ZIP 完成：{size_mb:.1f} MB → {zip_path}")
