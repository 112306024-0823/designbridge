-- 新增第二組英文 caption 欄位
-- 執行方式: 在 Supabase SQL Editor 貼上執行

ALTER TABLE public.style_images
  ADD COLUMN IF NOT EXISTS caption_en2 TEXT;
