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
        raise ValueError("Phương thức băm không xác định")

def analyze_md5_bytes(hash_str, adjustment_factor):
    bytes_list = [hash_str[i:i+2] for i in range(0, len(hash_str), 2)]
    if len(bytes_list) < 13: # MD5 hash có 16 byte, cần ít nhất chỉ mục 12
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
# Biến toàn cục để lưu trạng thái giữa các lần gọi API
history = [] # Lịch sử kết quả "tài" hoặc "xỉu" để tính adjustment_factor
adjustment_factor = 0.0
wrong_streak = 0
previous_prediction = None # Lưu dự đoán của CHÍNH chúng ta cho phiên TRƯỚC (lần gọi API trước đó)
previous_external_session_id = None # Lưu ID phiên NGOÀI (từ API bên ngoài) của phiên đã dự đoán ở lần gọi trước

@app.get("/hitmd5")
def predict():
    global history, adjustment_factor, wrong_streak, previous_prediction, previous_external_session_id

    # Lấy dữ liệu từ API bên ngoài
    try:
        response = requests.get("https://hitcolubnhumaubuoitao.onrender.com/txmd5")
        response.raise_for_status() # Nâng HTTPError cho các phản hồi lỗi (4xx hoặc 5xx)
        data = response.json()
    except RequestException as e:
        raise HTTPException(status_code=500, detail=f"Không thể lấy dữ liệu từ API bên ngoài: {e}")
    except JSONDecodeError:
        raise HTTPException(status_code=500, detail="Dữ liệu nhận được không phải định dạng JSON hợp lệ.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định khi lấy dữ liệu: {e}")

    # Kiểm tra cấu trúc dữ liệu JSON nhận được
    if not isinstance(data, dict) or "ket_qua_phien_truoc" not in data or "thong_tin_phien_sau" not in data:
        raise HTTPException(status_code=500, detail="Cấu trúc dữ liệu JSON từ API bên ngoài không đúng định dạng mong đợi.")

    ket_qua_phien_truoc = data["ket_qua_phien_truoc"]
    thong_tin_phien_sau = data["thong_tin_phien_sau"]

    # Kiểm tra các khóa cần thiết trong ket_qua_phien_truoc
    if "Phien" not in ket_qua_phien_truoc or "rs" not in ket_qua_phien_truoc or "d1" not in ket_qua_phien_truoc or "d2" not in ket_qua_phien_truoc or "d3" not in ket_qua_phien_truoc:
        raise HTTPException(status_code=500, detail="Dữ liệu 'ket_qua_phien_truoc' thiếu thông tin cần thiết (Phien, rs, d1, d2, d3).")
    
    # Kiểm tra các khóa cần thiết trong thong_tin_phien_sau
    if "md5" not in thong_tin_phien_sau:
        raise HTTPException(status_code=500, detail="Dữ liệu 'thong_tin_phien_sau' thiếu thông tin cần thiết (md5).")
    
    # Lấy thông tin phiên vừa kết thúc (mà chúng ta sẽ dùng để điều chỉnh thuật toán)
    session_id_vua_ket_thuc = ket_qua_phien_truoc["Phien"]
    result_vua_ket_thuc = ket_qua_phien_truoc["rs"].lower() # 'tài' hoặc 'xỉu'
    dice_vua_ket_thuc = f"{ket_qua_phien_truoc['d1']},{ket_qua_phien_truoc['d2']},{ket_qua_phien_truoc['d3']}"

    # Lấy md5 của phiên sắp tới để đưa ra dự đoán
    md5_input_phien_sap_toi = thong_tin_phien_sau["md5"]
    
    # LOGIC ĐIỀU CHỈNH: So sánh dự đoán TRƯỚC (previous_prediction)
    # với KẾT QUẢ THỰC TẾ của phiên TRƯỚC (result_vua_ket_thuc)
    # Chỉ điều chỉnh nếu đây không phải là lần gọi đầu tiên và ID phiên khớp
    if previous_prediction is not None and previous_external_session_id is not None and session_id_vua_ket_thuc == previous_external_session_id:
        if previous_prediction.lower() != result_vua_ket_thuc:
            wrong_streak += 1
        else:
            wrong_streak = 0
        
        # Thêm kết quả của phiên vừa kết thúc vào lịch sử
        history.append(result_vua_ket_thuc)
        # Giới hạn lịch sử để tránh tiêu tốn bộ nhớ quá nhiều
        if len(history) > 100: # Ví dụ: chỉ giữ 100 phiên gần nhất
            history.pop(0)

        tai_count = history.count("tài")
        xiu_count = history.count("xỉu")
        
        if tai_count > xiu_count:
            adjustment_factor = min(0.1, 0.05 + 0.01 * wrong_streak)
        elif xiu_count > tai_count:
            adjustment_factor = max(-0.1, -0.05 - 0.01 * wrong_streak)
        else:
            adjustment_factor = 0.0 # Nếu số lượng bằng nhau hoặc không có lịch sử

        if wrong_streak >= 3:
            adjustment_factor *= 1.5
    else:
        # Reset nếu là lần gọi đầu tiên hoặc ID phiên không khớp (có thể do API bên ngoài khởi động lại hoặc có lỗi)
        wrong_streak = 0
        adjustment_factor = 0.0
        history = [] # Xóa lịch sử cũ nếu không khớp hoặc mới bắt đầu

    # Phân tích hash của phiên SẮP TỚI để đưa ra dự đoán MỚI
    try:
        hash_md5_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'md5')
        hash_sha256_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'sha256')
        hash_sha512_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'sha512')

        md5_ratio, xiu_ratio, sel_bytes = analyze_md5_bytes(hash_md5_phien_sap_toi, adjustment_factor)
        bit_1, bit_0 = analyze_bits(hash_sha256_phien_sap_toi)
        even, odd = analyze_even_odd_chars(hash_sha512_phien_sap_toi)
        new_prediction_for_next_session = final_decision((md5_ratio, xiu_ratio), bit_1 - bit_0, even - odd)
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=f"Lỗi trong quá trình phân tích hash: {ve}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định trong quá trình phân tích hash: {e}")

    # Cập nhật previous_prediction và previous_external_session_id cho lần gọi API tiếp theo
    # previous_prediction giờ đây sẽ là dự đoán của chúng ta cho phiên SẮP TỚI
    # previous_external_session_id sẽ là ID của phiên SẮP TỚI này
    # Lần gọi API tiếp theo, chúng ta sẽ dùng các giá trị này để so sánh với ket_qua_phien_truoc
    previous_prediction = new_prediction_for_next_session
    previous_external_session_id = session_id_vua_ket_thuc + 1 # ID của phiên mà chúng ta vừa dự đoán

    # Trả về kết quả dự đoán
    return {
        "id": "@S77SIMON",
        "thoi_gian_lay_du_lieu": data.get("thoi_gian", "Không có thông tin thời gian"), # Lấy thời gian từ phản hồi gốc
        "ket_qua_phien_truoc_tu_api_goc": {
            "Phien": session_id_vua_ket_thuc,
            "dice": dice_vua_ket_thuc,
            "ket_qua": "Tài" if result_vua_ket_thuc == "tài" else "Xỉu"
        },
        "du_doan_cho_phien_sap_toi": {
            "phien_sap_toi_id": session_id_vua_ket_thuc + 1,
            "hash_md5_sap_toi": hash_md5_phien_sap_toi,
            "du_doan": new_prediction_for_next_session
        },
        "thong_tin_dieu_chinh": {
            "du_doan_lan_truoc": previous_prediction, # Dự đoán của bạn cho phiên hiện tại
            "ket_qua_phien_truoc": result_vua_ket_thuc, # Kết quả của phiên hiện tại (dùng để điều chỉnh)
            "chuoi_sai_lien_tiep": wrong_streak,
            "he_so_dieu_chinh_hien_tai": adjustment_factor,
            "so_luong_phien_trong_lich_su": len(history)
        }
    }
