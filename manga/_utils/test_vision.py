import requests
import base64
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
VISION_MODEL = "moondream"
IMAGE_PATH = r"data/raw/manga/panels/buddha_v01/panels/image panels/buddha_v01_p0014_panel01.png"

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def test():
    img_b64 = encode_image(IMAGE_PATH)
    # Simple prompt to see what it sees
    prompt = "Describe what is happening in this manga panel."

    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        print(response.json().get("response", ""))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
