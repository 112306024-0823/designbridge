"""
把本機已經下載好的圖片資料夾，上傳到 Cloudflare R2。

假設你的本機資料夾結構跟 image_path 一致，例如：
downloaded_images/
    industrial/
        api_1908434_1581404229_D7BQODjpbQ.jpg
    nordic/
        admin_30_1576476056_COiUMy3G8K.jpg
    ...

上傳後，R2 裡的 key 會直接沿用相對路徑（例如 industrial/xxx.jpg），
這樣才能跟 Supabase 表格裡的 image_path 對應起來。

使用方式：
1. 填好下方 R2 設定
2. LOCAL_ROOT 指向你本機圖片資料夾
3. 執行即可，支援中斷續傳（已上傳過的檔案會用 HEAD 請求檢查，跳過重複上傳）
"""

import mimetypes
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# ====== R2 設定 ======
R2_ACCOUNT_ID = "adf8791a229eb5890d75e8a209fd266f"
R2_ACCESS_KEY = "ee6d880a2ae7fafe9e6bd049f052cff7"
R2_SECRET_KEY = "69090c4f5dabb13b49c58ae2fda25dd52214e964c52a20438443188227330e6e"
R2_BUCKET = "designbridge"


# ====== 其他設定 ======
LOCAL_ROOT = Path(r"C:\Users\Timothy\Downloads\designbridge_image")   # 換成你本機圖片資料夾的路徑
MAX_RETRIES = 3
SKIP_IF_EXISTS = True   # True = 上傳前先檢查 R2 上有沒有同名檔案，有就跳過（省時間、可中斷續傳）

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
)


def already_uploaded(key: str) -> bool:
    if not SKIP_IF_EXISTS:
        return False
    try:
        s3.head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except ClientError:
        return False


def upload_one(local_path: Path, key: str) -> bool:
    content_type, _ = mimetypes.guess_type(str(local_path))
    content_type = content_type or "application/octet-stream"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            s3.upload_file(
                str(local_path),
                R2_BUCKET,
                key,
                ExtraArgs={"ContentType": content_type},
            )
            return True
        except Exception as e:
            print(f"  ⚠️ 第 {attempt} 次失敗：{key} ({e})")
            time.sleep(1)

    print(f"  ❌ 放棄：{key}")
    return False


def main():
    all_files = [p for p in LOCAL_ROOT.rglob("*") if p.is_file()]
    total = len(all_files)
    print(f"本機共找到 {total} 個檔案，準備上傳到 bucket「{R2_BUCKET}」")

    success, skipped, fail = 0, 0, 0
    for i, local_path in enumerate(all_files, 1):
        key = str(local_path.relative_to(LOCAL_ROOT)).replace("\\", "/")  # Windows 路徑分隔符轉換

        if already_uploaded(key):
            skipped += 1
        else:
            ok = upload_one(local_path, key)
            success += ok
            fail += not ok

        if i % 100 == 0:
            print(f"  進度：{i}/{total}（成功 {success}，跳過 {skipped}，失敗 {fail}）")

    print(f"\n全部完成：成功 {success}，跳過(已存在) {skipped}，失敗 {fail}")


if __name__ == "__main__":
    main()