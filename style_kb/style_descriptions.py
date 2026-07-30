# style_kb/style_descriptions.py
"""各風格的詳細描述，供 CLIP embedding 比對與 caption 生成使用。
參考來源：https://www.100.com.tw/article/3167
"""

# ── CLIP 比對用（英文，效果較佳）────────────────────────────────────────────────
# 用於 verify_style_embedding.py：將文字 encode 成向量，與圖片 embedding 做 cosine similarity

STYLE_CLIP_TEXTS: dict[str, str] = {
    "modern": (
        "modern interior design, clean geometric lines, "
        "tempered glass metal natural wood materials, "
        "neutral gray white black color palette, "
        "minimalist hidden storage open shelving, "
        "bright airy space with functional layout"
    ),
    "nordic": (
        "scandinavian nordic interior design, "
        "abundant natural wood, large windows soft diffused daylight, "
        "white beige light muted tones, "
        "sheepskin throws potted plants simple streamlined furniture, "
        "warm cozy minimalist atmosphere"
    ),
    "japanese": (
        "japanese zen interior design, "
        "wood lattice shoji screen tatami platform, "
        "bamboo tea table floor cushion folding screen, "
        "natural oak warm muted earthy tones, "
        "serene minimal grounded wabi-sabi atmosphere"
    ),
    "industrial": (
        "industrial loft interior design, "
        "exposed brick wall concrete ceiling bare pipes steel frame, "
        "aged rust metal fixtures distressed leather, "
        "dark cold gray charcoal black tones, "
        "raw unfinished materials urban aesthetic"
    ),
    "american": (
        "american style interior design, "
        "dark walnut wood paneling wainscoting crown molding, "
        "leather sofa upholstered fabric armchair, "
        "warm wood beige cream tones, "
        "eclectic comfortable relaxed layered decor"
    ),
    "classic": (
        "classic european interior design, "
        "ornate carved wood molding ceiling cornice crystal chandelier, "
        "marble floor mahogany rosewood furniture, "
        "chaise lounge decorative mirror gilded frame, "
        "rich dark brown burgundy tones, "
        "neoclassical roman greek architectural details"
    ),
    "luxury": (
        "modern luxury interior design, "
        "marble stone surface gold brass copper accents, "
        "velvet upholstery lacquered panels, "
        "polished reflective surfaces understated elegance, "
        "refined premium materials sophisticated atmosphere"
    ),
    "country": (
        "country rustic farmhouse interior design, "
        "stone fireplace exposed wood beams brick wall, "
        "floral pattern linen cotton fabric, "
        "warm brown earthy terracotta tones, "
        "vintage antique furniture dried flowers cozy nostalgic"
    ),
    "other": (
        "eclectic mixed style interior design"
    ),
}


# ── 中文描述（人工參考 / prompt 提示用）────────────────────────────────────────
STYLE_DESCRIPTIONS_ZH: dict[str, dict] = {
    "modern": {
        "name":       "現代風",
        "concept":    "理性、簡潔、強調功能性",
        "elements":   ["幾何線條", "鋼化玻璃隔層", "隱藏式收納", "開放式書架"],
        "materials":  ["鋼化玻璃", "金屬", "原木"],
        "colors":     ["中性黑灰白", "低飽和高明度色系"],
        "furniture":  ["複合式系統櫃", "簡約吊燈"],
    },
    "nordic": {
        "name":       "北歐風",
        "concept":    "與自然共處，兼具簡潔與溫度",
        "elements":   ["大量木材", "強調透光設計", "樸實淺色系", "功能性導向"],
        "materials":  ["木材", "玻璃", "鐵件"],
        "colors":     ["木材原色", "白色", "米色"],
        "furniture":  ["綠色植栽", "流線感單椅", "簡約燈具", "毛毯地毯"],
    },
    "japanese": {
        "name":       "日式風",
        "concept":    "禪宗哲學，追求心靈平靜與人境交流",
        "elements":   ["簡單樸實線條", "木格柵設計", "與自然共存理念"],
        "materials":  ["梧桐木", "竹子", "榻榻米", "板岩"],
        "colors":     ["原木色", "素雅暖色系"],
        "furniture":  ["捲簾", "木格柵", "茶桌", "坐墊", "屏風"],
        "variants":   ["日式無印風（簡約＋木質＋北歐融合）"],
    },
    "industrial": {
        "name":       "工業風",
        "concept":    "粗曠美學，越舊越有味道",
        "elements":   ["裸露磚牆與水泥", "外露管線與鋼架", "仿舊金屬鐵件"],
        "materials":  ["鏽蝕鐵件", "仿舊皮革", "混凝土"],
        "colors":     ["建材原色", "黑灰白冷色調"],
        "furniture":  ["鉚釘鐵件", "外露燈泡", "仿舊皮革沙發"],
        "variants":   ["輕工業風（較溫暖清新）", "LOFT風（樓中樓、開放式）"],
    },
    "american": {
        "name":       "美式風",
        "concept":    "多元融合，舒適自由的輕生活感",
        "elements":   ["深褐色木材", "線板設計", "可移動皮革沙發", "多元文化元素"],
        "materials":  ["柚木", "楓木", "皮革", "大理石"],
        "colors":     ["木色", "米色"],
        "furniture":  ["復古沙發", "布沙發", "畫框壁紙", "碎花窗簾"],
        "variants":   ["美式殖民風（草蓆、非洲木雕）", "美式現代風（自然材質平衡簡約）"],
    },
    "classic": {
        "name":       "古典／新古典風",
        "concept":    "貴氣奢華，承襲歐洲皇室風範",
        "elements":   ["大型華麗傢俱", "精緻雕花與線板", "深沉棕紅配色", "充足開放空間"],
        "materials":  ["紫檀木", "紅木", "皮革", "大理石"],
        "colors":     ["棕紅木色"],
        "furniture":  ["水晶燈", "文藝掛畫", "貴妃椅", "裝飾掛鏡"],
        "variants":   ["新古典風（內斂細膩、融合羅馬希臘元素）", "美式古典風（暖白色系）"],
        "note":       "原 neoclassic 已於 2026-06-26 合併至此分類",
    },
    "luxury": {
        "name":       "輕奢風",
        "concept":    "低調奢華，精緻細膩的現代質感",
        "elements":   ["大理石紋路", "金屬線條點綴", "天鵝絨材質", "鏡面反射"],
        "materials":  ["大理石", "黃銅", "天鵝絨", "烤漆板"],
        "colors":     ["黑白灰為底", "金銅色點綴"],
        "furniture":  ["設計感單椅", "造型燈具", "藝術品擺件"],
    },
    "country": {
        "name":       "鄉村風",
        "concept":    "反璞歸真，懷舊愜意的農村生活",
        "elements":   ["良好採光", "壁爐或壁龕", "花草與圖騰裝飾", "復古懷舊感"],
        "materials":  ["原木", "板岩", "磚牆"],
        "colors":     ["棕色", "褐色", "米白色"],
        "furniture":  ["粗棉麻布", "乾燥花卉", "木製餐具", "復古收納瓶罐"],
    },
    "other": {
        "name":       "其他／混搭",
        "concept":    "不明確歸類的風格，或多種風格混搭",
        "elements":   [],
        "materials":  [],
        "colors":     [],
        "furniture":  [],
    },
}


# ── Caption 生成提示（給 Gemini / Claude 的 prompt 格式參考）────────────────────
STYLE_CAPTION_HINTS: dict[str, str] = {
    "modern":     "Focus on: clean lines, glass/metal/wood materials, neutral tones, minimalist layout",
    "nordic":     "Focus on: natural wood, light tones, soft daylight, plants, cozy textiles",
    "japanese":   "Focus on: wood lattice, tatami, zen atmosphere, natural materials, muted tones",
    "industrial": "Focus on: exposed brick/concrete/pipes, metal fixtures, dark cold tones, raw materials",
    "american":   "Focus on: wood paneling, molding, leather/fabric sofa, warm eclectic layering",
    "classic":    "Focus on: carved molding, crystal chandelier, marble, ornate furniture, rich dark tones",
    "luxury":     "Focus on: marble, brass/gold accents, velvet, polished surfaces, refined elegance",
    "country":    "Focus on: fireplace, exposed beams, floral patterns, earthy tones, vintage nostalgia",
    "other":      "Describe the visual style and dominant design elements observed",
}
