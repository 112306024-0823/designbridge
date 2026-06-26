import os
from datetime import datetime
from pathlib import Path
from huggingface_hub import InferenceClient
from PIL import Image
from dotenv import load_dotenv

# Always load .env from project root (one level above test/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

# 想要測試的模型清單
MODELS = {
    "Flux-1-Schnell": "black-forest-labs/FLUX.1-schnell",
}

# 室內設計的 Prompt (建議用英文，效果最好)
PROMPT = "An elegant New Chinese Style (Xin Zhong Shi) living room. Centered against the main wall is a pair of symmetrical dark rosewood armchairs with white silk cushions, separated by a matching tea table. Behind them, a large decorative wall panel featuring a subtle, misty landscape ink wash painting (Shan Shui). On either side of the panel, vertical dark wood louvered screens (Grilles) allow soft ambient light to filter through. A minimalist low-profile gray fabric sofa is positioned in the foreground. On the coffee table, a delicate celadon tea set and a single branch of blooming plum blossoms in a slender vase. The floor is made of polished light grey marble with natural veining. Above, a modern rectangular chandelier with warm lantern-like glow. A serene and zen atmosphere, cinematic lighting, hyper-realistic, 8k resolution, interior design photography."

# prompt 1 ="A modern minimalist living room, cream-colored sofa, warm wooden floor, large windows with sunlight, cinematic lighting, 8k resolution, interior design photography"
# prompt 2 ="A cozy rustic country style living room. Centered in the room is a large, comfortable slipcovered linen sofa in warm beige. To the left of the sofa, a vintage distressed wooden side table with a classic ceramic lamp. Against the far wall, a grand stone fireplace with a thick reclaimed wood mantel. On either side of the fireplace, built-in white shiplap bookshelves filled with old books and woven baskets. In the foreground, a large round jute rug sits on a wide-plank oak floor. Above, exposed dark timber ceiling beams. Natural soft light streaming through large grid windows, illuminating floating dust motes, cinematic lighting, hyper-realistic, 8k resolution, interior design photography"

# ==========================================

OUTPUT_ROOT = TEST_DIR / "test_picture"

def run_test():
    hf_token = os.getenv("HF_TOKEN", "").strip()
    if not hf_token:
        raise RuntimeError("找不到 HF_TOKEN。請確認 .env 內有設定 HF_TOKEN，並從專案根目錄執行。")

    client = InferenceClient(api_key=hf_token)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = OUTPUT_ROOT / f"run_{run_id}"
    run_output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🚀 開始測試室內設計生圖...")
    print(f"📝 Prompt: {PROMPT}\n")
    print(f"📁 輸出資料夾: {run_output_dir}\n")

    for name, model_id in MODELS.items():
        print(f"🎨 正在使用 [{name}] 生成圖片...")
        try:
            # 呼叫 API 生圖
            image = client.text_to_image(
                PROMPT,
                model=model_id
            )
            
            # 儲存圖片
            filename = f"result_{name.lower()}.png"
            output_path = run_output_dir / filename
            image.save(output_path)
            print(f"✅ 已完成！儲存為: {output_path}")
            
        except Exception as e:
            print(f"❌ [{name}] 執行失敗。原因: {e}")
            if "403" in str(e):
                print("💡 提示：請確認你是否已在 HF 官網對該模型點擊過 'Agree and access' 並申請權限。")

    print("\n✨ 所有測試結束！請查看本次輸出資料夾內的 PNG 檔案。")

if __name__ == "__main__":
    run_test()



# prompt 1

#一間溫馨且具原始質感的鄉村風客廳。

#中心佈局： 房間中央擺放著一張寬大舒適的暖米色亞麻布藝沙發。
#家具細節： 沙發左側放著一張帶有磨損質感的復古舊木邊几，上方擺著一盞經典陶瓷檯燈。
#牆面焦點： 遠處牆面有一座雄偉的石造壁爐，配有厚實的回收舊木壁爐架 (Mantel)。
#收納裝飾： 壁爐兩側設有嵌入式的白色搭接板 (Shiplap) 書架，架上擺滿了舊書與編織籃。
#地面與結構： 前景處，一張大型圓形黃麻地毯鋪在寬版橡木地板上；天花板則有外露的深色原木樑柱。
#光影氛圍： 自然柔光從大型格狀窗戶灑入，照亮了空氣中飄浮的微塵。
#影像規格： 電影級光影渲染、極致寫實、8k 解析度、室內設計攝影風格。


# prompt 2

#中心佈局： 主牆前對稱擺放著一對深色花梨木扶手椅，配有白色絲綢坐墊，中間隔著一張配套的茶几。
#視覺焦點： 座椅後方有一塊大型裝飾牆板，上面繪有細膩、朦朧的山水水墨畫。
#光影結構： 牆板兩側設有深色木質豎向格柵，讓柔和的環境光過濾進室內。
#家具配置： 前景擺放著一張簡約的低矮灰色布藝沙發。
#裝飾點綴： 茶几上有一套精緻的青瓷茶具，以及細長花瓶中插著的一枝梅花。
#地面材質： 地板採用磨光的淺灰色大理石，帶有自然紋理。
#燈飾氛圍： 上方懸掛著現代長方形吊燈，發出如燈籠般的溫暖光芒。
#意境： 寧靜禪意的氛圍、電影級光影、極致寫實、8k 解析度、室內設計攝影風格。
