import os, sys, httpx, zipfile
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).parent / ".env")

from supabase import create_client
client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

rows = (client.table("style_images")
        .select("id, image_url, caption_en, style_id")
        .not_.is_("caption_en", "null")
        .not_.is_("image_url", "null")
        .execute().data)

print(f"共 {len(rows)} 張，開始下載...")

out = Path(__file__).parent / "dataset_export"
out.mkdir(exist_ok=True)

failed = 0
for i, row in enumerate(rows):
    stem = f"{i:05d}_{row['style_id']}"
    try:
        img_bytes = httpx.get(row["image_url"], timeout=20, follow_redirects=True).content
        (out / f"{stem}.jpg").write_bytes(img_bytes)
        (out / f"{stem}.txt").write_text(row["caption_en"], encoding="utf-8")
        if (i + 1) % 50 == 0:
            print(f"[{i+1}/{len(rows)}] ✅")
    except Exception as e:
        failed += 1
        print(f"[{i+1}] ❌ {e}")

print(f"下載完成：{len(rows) - failed} 成功，{failed} 失敗")

zip_path = Path(__file__).parent / "designbridge_dataset.zip"
print("打包中...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(out.iterdir()):
        zf.write(f, f.name)

size_mb = zip_path.stat().st_size / 1e6
print(f"✅ ZIP 完成：{size_mb:.1f} MB → {zip_path}")
