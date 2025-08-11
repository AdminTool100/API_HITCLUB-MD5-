from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import re
import requests
from requests.exceptions import RequestException, JSONDecodeError

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
        # Trường hợp này lý tưởng là không nên xảy ra nếu các lệnh gọi được kiểm soát
        raise ValueError("Phương thức băm không xác định")

def analyze_md5_bytes(hash_str, adjustment_factor):
    bytes_list = [hash_str[i:i+2] for i in range(0, len(hash_str), 2)]
    # Đảm bảo có đủ byte để chọn
    if len(bytes_list) < 13: # Cần ít nhất chỉ mục 12 (để lấy byte thứ 12)
        raise ValueError("Chuỗi băm MD5 quá ngắn để phân tích byte.")
    selected_bytes = [bytes_list[7], bytes_list[3], bytes_list[12]]
    digits_sum = sum(int(b, 16) for b in selected_bytes)
    tai_ratio = (digits_sum % 100) / 100
    tai_ratio = min(1, max(0, tai_ratio + adjustment_factor))
    xiu_ratio = 1 - tai_ratio
    return round(tai_ratio * 100, 2), round(xiu_ratio * 100, 2), selected_bytes

def analyze_bits(hash_str):
    try:
        binary = ''.join(f'{int(c, 16):04b}' for c in hash_str)
        return binary.count('1'), binary.count('0')
    except ValueError:
        raise ValueError("Chuỗi thập lục phân không hợp lệ để phân tích bit.")


def analyze_even_odd_chars(hash_str):
    even = sum(1 for c in hash_str if c in '02468ace')
    return even, len(hash_str) - even

def final_decision(md5_ratio, bit_diff, even_odd_diff):
    score = 0
    score += 1 if md5_ratio[0] > md5_ratio[1] else -1
    score += 1 if bit_diff > 0 else -1
    score += 1 if even_odd_diff > 0 else -1
    return "Tài" if score > 0 else "Xỉu"

# ===== API gốc =====
@app.get("/")
def root():
    return {"message": "API đang chạy, truy cập /hitmd5 để lấy dự đoán"}

# ===== API /hitmd5 =====
# Biến toàn cục để lưu trạng thái giữa các lần gọi API (cho logic dự đoán)
history = []
adjustment_factor = 0.0
wrong_streak = 0
previous_prediction = None
previous_session = None

@app.get("/hitmd5")
def predict():
    global history, adjustment_factor, wrong_streak, previous_prediction, previous_session

    # Lấy dữ liệu từ API lịch sử
    try:
        response = requests.get("https://hitcolubnhumaubuoitao.onrender.com/txmd5")
        response.raise_for_status()  # Nâng HTTPError cho các phản hồi xấu (4xx hoặc 5xx)
        data = response.json()
    except RequestException as e:
        # Bắt bất kỳ lỗi liên quan đến yêu cầu nào (sự cố mạng, thời gian chờ, URL xấu, v.v.)
        raise HTTPException(status_code=500, detail=f"Không thể lấy dữ liệu lịch sử từ API bên ngoài: {e}")
    except JSONDecodeError:
        # Bắt lỗi nếu phản hồi không phải JSON hợp lệ
        raise HTTPException(status_code=500, detail="Dữ liệu lịch sử nhận được không phải định dạng JSON hợp lệ.")
    except Exception as e:
        # Bắt bất kỳ lỗi không mong muốn nào khác trong quá trình tìm nạp dữ liệu
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định khi lấy dữ liệu lịch sử: {e}")

    # Kiểm tra dữ liệu lịch sử nhận được
    if not isinstance(data, list) or len(data) < 2:
        raise HTTPException(status_code=500, detail="Dữ liệu lịch sử không đủ hoặc không đúng định dạng (cần ít nhất 2 phiên).")

    # Phiên trước (index 1 trong danh sách)
    prev_game = data[1]
    # Đảm bảo các khóa cần thiết tồn tại trong dữ liệu phiên trước
    if "result" not in prev_game or "session" not in prev_game or "dice" not in prev_game:
        raise HTTPException(status_code=500, detail="Dữ liệu phiên trước thiếu thông tin cần thiết (result, session, dice).")

    prev_result = prev_game["result"].lower()

    # Nếu có dự đoán trước (từ lần gọi API trước) thì cập nhật điều chỉnh
    # Chỉ cập nhật nếu phiên hiện tại là phiên tiếp theo của phiên trước đó đã được dự đoán
    if previous_prediction is not None and previous_session is not None and prev_game["session"] == previous_session + 1:
        if previous_prediction.lower() != prev_result:
            wrong_streak += 1
        else:
            wrong_streak = 0

        # Cập nhật lịch sử các kết quả trước đó
        history.append(prev_result)

        # Tính toán lại hệ số điều chỉnh dựa trên lịch sử và chuỗi sai
        tai_count = history.count("tài")
        xiu_count = history.count("xỉu")
        
        if tai_count > xiu_count:
            adjustment_factor = min(0.1, 0.05 + 0.01 * wrong_streak)
        elif xiu_count > tai_count:
            adjustment_factor = max(-0.1, -0.05 - 0.01 * wrong_streak)
        else: # Số lượng tài/xỉu bằng nhau hoặc trạng thái ban đầu
            adjustment_factor = 0.0

        if wrong_streak >= 3:
            adjustment_factor *= 1.5
    else:
        # Nếu không có dự đoán trước hoặc phiên không khớp, đặt lại chuỗi sai và hệ số điều chỉnh
        wrong_streak = 0
        adjustment_factor = 0.0
        # Xóa lịch sử để tránh dữ liệu cũ ảnh hưởng đến các tính toán mới
        history = []


    # Phiên hiện tại (index 0 trong danh sách)
    current_game = data[0]
    # Đảm bảo các khóa cần thiết tồn tại trong dữ liệu phiên hiện tại
    if "hash" not in current_game or "session" not in current_game:
        raise HTTPException(status_code=500, detail="Dữ liệu phiên hiện tại thiếu thông tin cần thiết (hash, session).")
    
    md5_input = current_game["hash"]

    # Phân tích hash để đưa ra dự đoán
    try:
        hash_md5 = generate_hash(md5_input, 'md5')
        hash_sha256 = generate_hash(md5_input, 'sha256')
        hash_sha512 = generate_hash(md5_input, 'sha512')

        md5_ratio, xiu_ratio, sel_bytes = analyze_md5_bytes(hash_md5, adjustment_factor)
        bit_1, bit_0 = analyze_bits(hash_sha256)
        even, odd = analyze_even_odd_chars(hash_sha512)
        prediction = final_decision((md5_ratio, xiu_ratio), bit_1 - bit_0, even - odd)
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Lỗi trong quá trình phân tích hash: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định trong quá trình phân tích hash: {e}")

    # Lưu lại dự đoán và phiên hiện tại cho lần gọi tiếp theo
    previous_prediction = prediction
    previous_session = current_game["session"]

    # Trả về kết quả dự đoán
    return {
        "id": "@S77SIMON",
        "phiên trước": {
            "dice": prev_game["dice"],
            "kết quả": "Tài" if prev_result == "tài" else "Xỉu"
        },
        "hiện tại": {
            "phiên": current_game["session"],
            "md5": hash_md5,
            "dự đoán": prediction
        }
    }
