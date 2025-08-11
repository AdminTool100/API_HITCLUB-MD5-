from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import re
import requests

app = FastAPI()

# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép mọi domain
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== THUẬT TOÁN =====
def generate_hash(input_string, method='md5'):
    h = input_string.encode()
    if method == 'md5':
        return hashlib.md5(h).hexdigest()
    elif method == 'sha256':
        return hashlib.sha256(h).hexdigest()
    elif method == 'sha512':
        return hashlib.sha512(h).hexdigest()
    else:
        raise ValueError("Unknown hash method")

def analyze_md5_bytes(hash_str, adjustment_factor):
    bytes_list = [hash_str[i:i+2] for i in range(0, len(hash_str), 2)]
    selected_bytes = [bytes_list[7], bytes_list[3], bytes_list[12]]
    digits_sum = sum(int(b, 16) for b in selected_bytes)
    tai_ratio = (digits_sum % 100) / 100
    tai_ratio = min(1, max(0, tai_ratio + adjustment_factor))
    xiu_ratio = 1 - tai_ratio
    return round(tai_ratio * 100, 2), round(xiu_ratio * 100, 2), selected_bytes

def analyze_bits(hash_str):
    binary = ''.join(f'{int(c, 16):04b}' for c in hash_str)
    return binary.count('1'), binary.count('0')

def analyze_even_odd_chars(hash_str):
    even = sum(1 for c in hash_str if c in '02468ace')
    return even, len(hash_str) - even

def final_decision(md5_ratio, bit_diff, even_odd_diff):
    score = 0
    score += 1 if md5_ratio[0] > md5_ratio[1] else -1
    score += 1 if bit_diff > 0 else -1
    score += 1 if even_odd_diff > 0 else -1
    return "Tài" if score > 0 else "Xỉu"

def parse_and_sum_result(result_string):
    numbers = list(map(int, re.findall(r'\d+', result_string)))
    return sum(numbers[:3]) if len(numbers) >= 3 else 0

# ===== API /predict =====
history = []
adjustment_factor = 0.0
wrong_streak = 0
previous_prediction = None
previous_session = None

@app.get("/predict")
def predict():
    global history, adjustment_factor, wrong_streak, previous_prediction, previous_session

    # Lấy dữ liệu từ API lịch sử
    try:
        data = requests.get("https://hitcolubnhumaubuoitao.onrender.com/txmd5").json()
    except:
        return {"error": "Không lấy được dữ liệu"}

    if not data or len(data) < 2:
        return {"error": "Dữ liệu lịch sử không đủ"}

    # Phiên trước
    prev_game = data[1]
    prev_result = prev_game["result"].lower()

    # Nếu có dự đoán trước thì cập nhật điều chỉnh
    if previous_prediction and prev_game["session"] == previous_session + 1:
        if previous_prediction.lower() != prev_result:
            wrong_streak += 1
        else:
            wrong_streak = 0

        tai_count = history.count("tài")
        xiu_count = history.count("xỉu")
        if tai_count > xiu_count:
            adjustment_factor = min(0.1, 0.05 + 0.01 * wrong_streak)
        elif xiu_count > tai_count:
            adjustment_factor = max(-0.1, -0.05 - 0.01 * wrong_streak)
        if wrong_streak >= 3:
            adjustment_factor *= 1.5
        history.append(prev_result)

    # Phiên hiện tại
    current_game = data[0]
    md5_input = current_game["hash"]

    # Phân tích hash
    hash_md5 = generate_hash(md5_input, 'md5')
    hash_sha256 = generate_hash(md5_input, 'sha256')
    hash_sha512 = generate_hash(md5_input, 'sha512')

    md5_ratio, xiu_ratio, sel_bytes = analyze_md5_bytes(hash_md5, adjustment_factor)
    bit_1, bit_0 = analyze_bits(hash_sha256)
    even, odd = analyze_even_odd_chars(hash_sha512)
    prediction = final_decision((md5_ratio, xiu_ratio), bit_1 - bit_0, even - odd)

    previous_prediction = prediction
    previous_session = current_game["session"]

    return {
        "id": "@S77SIMON",
        "phiên trước": {
            "dice": prev_game["dice"],
            "kết quả": prev_result
        },
        "hiện tại": {
            "phiên": current_game["session"],
            "md5": hash_md5,
            "dự đoán": prediction
        }
    }