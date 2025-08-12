from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import re
import requests
from requests.exceptions import RequestException, JSONDecodeError

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

# ==== SUPPORT ====
def adjust_prediction_factor(history_results, wrong_streak):
    tai_count = history_results.count("tài")
    xiu_count = history_results.count("xỉu")
    adjustment = 0.0
    if tai_count > xiu_count:
        adjustment = min(0.1, 0.05 + 0.01 * wrong_streak)
    elif xiu_count > tai_count:
        adjustment = max(-0.1, -0.05 - 0.01 * wrong_streak)
    if wrong_streak >= 3:
        adjustment *= 1.5
    return adjustment

@app.get("/")
def root():
    return {"message": "API đang chạy, truy cập /hitmd5 để lấy dự đoán"}

# Biến toàn cục để lưu trạng thái và thống kê
history = []
adjustment_factor = 0.0
wrong_streak = 0
previous_prediction = None
previous_external_session_id = None

# Thêm biến thống kê
total_predictions_made = 0
correct_predictions_count = 0

@app.get("/hitmd5")
def predict():
    global history, adjustment_factor, wrong_streak, previous_prediction, previous_external_session_id
    global total_predictions_made, correct_predictions_count # Khai báo để có thể sửa đổi

    EXTERNAL_API_URL = "https://binhsexgayvoiphucchimbehitclub.onrender.com/txmd5"

    try:
        response = requests.get(EXTERNAL_API_URL)
        response.raise_for_status()
        data = response.json()
    except RequestException as e:
        raise HTTPException(status_code=500, detail=f"Không thể lấy dữ liệu từ API bên ngoài: {e}")
    except JSONDecodeError:
        raise HTTPException(status_code=500, detail="Dữ liệu nhận được không phải định dạng JSON hợp lệ.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định khi lấy dữ liệu: {e}")

    required_fields = ["Phien", "Xuc_xac_1", "Xuc_xac_2", "Xuc_xac_3", "Ket_qua", "Md5"]
    if not isinstance(data, dict) or not all(field in data for field in required_fields):
        raise HTTPException(status_code=500, detail="Cấu trúc dữ liệu JSON từ API bên ngoài không đúng định dạng mong đợi (thiếu các trường cơ bản).")
    
    session_id_vua_ket_thuc = data["Phien"]
    result_vua_ket_thuc = data["Ket_qua"].lower()
    dice_vua_ket_thuc = f"{data['Xuc_xac_1']}-{data['Xuc_xac_2']}-{data['Xuc_xac_3']}"
    md5_input_phien_sap_toi = data["Md5"]
    
    # Cập nhật thống kê và hệ số điều chỉnh DỰA TRÊN KẾT QUẢ CỦA PHIÊN TRƯỚC MÀ TA ĐÃ DỰ ĐOÁN
    if previous_prediction is not None and previous_external_session_id is not None and session_id_vua_ket_thuc == previous_external_session_id:
        total_predictions_made += 1 # Đã có một dự đoán được so sánh
        if previous_prediction.lower() == result_vua_ket_thuc:
            correct_predictions_count += 1
            wrong_streak = 0
        else:
            wrong_streak += 1
        
        history.append(result_vua_ket_thuc)
        if len(history) > 100:
            history.pop(0)

        adjustment_factor = adjust_prediction_factor(history, wrong_streak)
    else:
        # Reset nếu là lần gọi đầu tiên hoặc ID phiên không khớp
        # Không reset total_predictions_made và correct_predictions_count ở đây,
        # vì chúng ta muốn thống kê toàn bộ hoạt động từ khi server khởi động.
        wrong_streak = 0
        adjustment_factor = 0.0
        history = [] # Reset lịch sử riêng cho việc điều chỉnh hệ số

    # Phân tích hash của phiên SẮP TỚI để đưa ra dự đoán MỚI
    try:
        hash_md5_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'md5')
        hash_sha256_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'sha256')
        hash_sha512_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'sha512')

        md5_ratio = analyze_md5(hash_md5_phien_sap_toi, adjustment_factor)
        
        bit_1, bit_0 = analyze_bits(hash_sha256_phien_sap_toi)
        bit_diff = bit_1 - bit_0

        even, odd = analyze_even_odd_chars(hash_sha512_phien_sap_toi)
        even_odd_diff = even - odd

        new_prediction_for_next_session = final_decision(md5_ratio, bit_diff, even_odd_diff)
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Lỗi trong quá trình phân tích hash: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định trong quá trình phân tích hash: {e}")

    # Cập nhật `previous_prediction` và `previous_external_session_id` cho lần gọi API tiếp theo
    previous_prediction = new_prediction_for_next_session
    previous_external_session_id = session_id_vua_ket_thuc

    # Tính tỷ lệ chính xác hiện tại
    accuracy = (correct_predictions_count / total_predictions_made) * 100 if total_predictions_made > 0 else 0

    return {
        "id": "S77SIMON",
        "phiên trước": {
            "phiên": session_id_vua_ket_thuc,
            "dice": dice_vua_ket_thuc,
            "kết quả": "Tài" if result_vua_ket_thuc == "tài" else "Xỉu"
        },
        "phiên hiện tại": {
            "phiên": session_id_vua_ket_thuc + 1,
            "mã md5": md5_input_phien_sap_toi,
            "dự đoán": new_prediction_for_next_session
        },
        "thống kê": {
            "tổng dự đoán": total_predictions_made,
            "đúng": correct_predictions_count,
            "sai": total_predictions_made - correct_predictions_count,
            "tỷ lệ chính xác": round(accuracy, 2)
        }
    }
