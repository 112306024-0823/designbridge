-- Phase 0: 新增 Flux LoRA 訓練所需欄位
-- 執行方式: 在 Supabase SQL Editor 貼上執行

ALTER TABLE public.style_images
  ADD COLUMN IF NOT EXISTS width          INTEGER,
  ADD COLUMN IF NOT EXISTS height         INTEGER,
  ADD COLUMN IF NOT EXISTS file_size_kb   FLOAT,
  ADD COLUMN IF NOT EXISTS quality_score  FLOAT,
  ADD COLUMN IF NOT EXISTS quality_flags  JSONB,
  ADD COLUMN IF NOT EXISTS caption_en     TEXT,
  ADD COLUMN IF NOT EXISTS is_selected    BOOLEAN DEFAULT FALSE;
