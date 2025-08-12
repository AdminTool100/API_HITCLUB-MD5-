from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# Import JSONResponse to control JSON formatting
from fastapi.responses import JSONResponse 
import hashlib
import re
import requests
from requests.exceptions import RequestException, JSONDecodeError
import json # Still need this if you want to use json.dumps for debugging or other purposes, but not for the final return

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== HASHING METHODS ====
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

# ==== HASH ANALYSIS ====
def analyze_md5(hash_str, adjustment_factor):
    digits_sum = sum(int(c, 16) for c in hash_str if c.isdigit() or c in 'abcdef')
    tai_ratio = (digits_sum % 100) / 100
    tai_ratio = min(1, max(0, tai_ratio + adjustment_factor))
    xiu_ratio = 1 - tai_ratio
    return round(tai_ratio * 100, 2), round(xiu_ratio * 100, 2)

def analyze_bits(hash_str):
    binary = ''.join(f'{int(c, 16):04b}' for c in hash_str)
    count_1 = binary.count('1')
    count_0 = binary.count('0')
    return count_1, count_0

def analyze_even_odd_chars(hash_str):
    even = sum(1 for c in hash_str if c in '02468ace')
    odd = len(hash_str) - even
    return even, odd

def final_decision(md5_ratio, bit_diff, even_odd_diff):
    score = 0
    score += 1 if md5_ratio[0] > md5_ratio[1] else -1
    score += 1 if bit_diff > 0 else -1
    score += 1 if even_odd_diff > 0 else -1
    return "Tài" if score > 0 else "Xỉu"

# ==== SUPPORT (ADJUSTED) ====
def adjust_prediction_factor(history_results):
    tai_count = history_results.count("tài")
    xiu_count = history_results.count("xỉu")
    adjustment = 0.0

    if tai_count > xiu_count:
        adjustment = 0.02
    elif xiu_count > tai_count:
        adjustment = -0.02
    return adjustment

@app.get("/")
def root():
    return {"message": "API đang chạy, truy cập /hitmd5 để lấy dự đoán"}

# Biến toàn cục để lưu trạng thái và thống kê
history = []
adjustment_factor = 0.0
wrong_streak = 0

prediction_for_next_session_id = None
our_prediction_for_that_session = None

last_session_id_from_external_api = None

total_predictions_evaluated = 0
correct_predictions_count = 0

@app.get("/hitmd5")
def predict():
    global history, adjustment_factor, wrong_streak
    global prediction_for_next_session_id, our_prediction_for_that_session, last_session_id_from_external_api
    global total_predictions_evaluated, correct_predictions_count

    EXTERNAL_API_URL = "https://binhsexgayvoiphucchimbehitclub.onrender.com/md5"

    try:
        response = requests.get(EXTERNAL_API_URL)
        response.raise_for_status()

        response.encoding = 'utf-8' 
        data = response.json()
    except RequestException as e:
        print(f"LỖI KẾT NỐI API NGOÀI: {e}") # Debugging
        raise HTTPException(status_code=500, detail=f"Không thể lấy dữ liệu từ API bên ngoài: {e}")
    except JSONDecodeError as e:
        print(f"LỖI GIẢI MÃ JSON: {e}") # Debugging
        # Có thể in response.text để xem nội dung thô nếu JSONDecodeError xảy ra
        # print(f"Raw response text: {response.text}")
        raise HTTPException(status_code=500, detail="Dữ liệu nhận được không phải định dạng JSON hợp lệ hoặc không thể giải mã với UTF-8.")
    except Exception as e:
        print(f"LỖI KHÔNG XÁC ĐỊNH: {e}") # Debugging
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định khi lấy dữ liệu: {e}")

    required_fields = ["Phien", "Xuc_xac_1", "Xuc_xac_2", "Xuc_xac_3", "Ket_qua", "Md5"]
    if not isinstance(data, dict) or not all(field in data for field in required_fields):
        print(f"LỖI CẤU TRÚC DỮ LIỆU: {data}") # Debugging
        raise HTTPException(status_code=500, detail="Cấu trúc dữ liệu JSON từ API bên ngoài không đúng định dạng mong đợi (thiếu các trường cơ bản).")
    
    current_session_id_from_external_api = data["Phien"]
    current_session_result_from_external_api = data["Ket_qua"].lower()
    current_session_dice_from_external_api = f"{data['Xuc_xac_1']}-{data['Xuc_xac_2']}-{data['Xuc_xac_3']}"
    md5_for_current_session = data["Md5"]

    # --- LOGIC CẬP NHẬT THỐNG KÊ ---
    if our_prediction_for_that_session is not None and \
       current_session_id_from_external_api == prediction_for_next_session_id and \
       current_session_id_from_external_api != last_session_id_from_external_api:
        
        total_predictions_evaluated += 1 

        if our_prediction_for_that_session.lower() == current_session_result_from_external_api:
            correct_predictions_count += 1
            wrong_streak = 0
        else:
            wrong_streak += 1
        
        history.append(current_session_result_from_external_api)
        if len(history) > 100:
            history.pop(0)

        adjustment_factor = adjust_prediction_factor(history)
        
        last_session_id_from_external_api = current_session_id_from_external_api
    
    elif prediction_for_next_session_id is None:
        last_session_id_from_external_api = current_session_id_from_external_api
        history = []
        adjustment_factor = 0.0
        wrong_streak = 0

    # --- LOGIC DỰ ĐOÁN CHO PHIÊN MỚI ---
    next_session_id_to_predict = current_session_id_from_external_api + 1

    try:
        hash_md5_for_prediction = generate_hash(md5_for_current_session, 'md5')
        hash_sha256_for_prediction = generate_hash(md5_for_current_session, 'sha256')
        hash_sha512_for_prediction = generate_hash(md5_for_current_session, 'sha512')

        md5_ratio = analyze_md5(hash_md5_for_prediction, adjustment_factor)
        
        bit_1, bit_0 = analyze_bits(hash_sha256_for_prediction)
        bit_diff = bit_1 - bit_0

        even, odd = analyze_even_odd_chars(hash_sha512_for_prediction)
        even_odd_diff = even - odd

        new_prediction_result = final_decision(md5_ratio, bit_diff, even_odd_diff)
    except ValueError as ve:
        print(f"LỖI PHÂN TÍCH HASH: {ve}") # Debugging
        raise HTTPException(status_code=500, detail=f"Lỗi trong quá trình phân tích hash: {ve}")
    except Exception as e:
        print(f"LỖI KHÔNG XÁC ĐỊNH KHI PHÂN TÍCH HASH: {e}") # Debugging
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định trong quá trình phân tích hash: {e}")

    prediction_for_next_session_id = next_session_id_to_predict
    our_prediction_for_that_session = new_prediction_result

    accuracy = (correct_predictions_count / total_predictions_evaluated) * 100 if total_predictions_evaluated > 0 else 0

    # Tạo dictionary kết quả
    response_content = {
        "id": "S77SIMON",
        "thống kê": {
            "tổng dự đoán đã đánh giá": total_predictions_evaluated,
            "đúng": correct_predictions_count,
            "sai": total_predictions_evaluated - correct_predictions_count,
            "tỷ lệ chính xác": round(accuracy, 2)
        },
        "phiên trước": {
            "phiên": current_session_id_from_external_api,
            "kết quả": "Tài" if current_session_result_from_external_api == "tài" else "Xỉu",
            "dice": current_session_dice_from_external_api
        },
        "phiên hiện tại": {
            "phiên": next_session_id_to_predict,
            "mã md5": md5_for_current_session,
            "dự đoán": new_prediction_result
        }
    }
    
    # Trả về JSON được định dạng đẹp bằng JSONResponse
    # Sử dụng `json.dumps` với `indent` trong encoder của JSONResponse
    # để đảm bảo JSON luôn đẹp
    return JSONResponse(
        content=response_content,
        media_type="application/json",
        # Sử dụng json_encoder để định dạng đẹp
        # render sẽ sử dụng default encoder của Uvicorn/Starlette/FastAPI,
        # và nó đã có khả năng pretty-print nếu debug=True hoặc env variable set.
        # Tuy nhiên, nếu muốn đảm bảo, có thể custom encoder:
        # json_dumps_params={"indent": 4, "ensure_ascii": False} # This does not work directly with JSONResponse
                                                                # You would set app.json_encoder for this
    )

# Để đảm bảo FastAPI pretty-print, bạn có thể cấu hình app.json_encoder
# Cần đặt điều này SAU khi định nghĩa `app = FastAPI()`
# Lưu ý: Điều này có thể ảnh hưởng đến tất cả các endpoint trả về JSON
app.json_encoder = lambda obj: json.dumps(obj, indent=4, ensure_ascii=False)

