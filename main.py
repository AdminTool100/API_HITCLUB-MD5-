from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse # Có thể cần nhập cái này nếu muốn dùng trực tiếp JSONResponse

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
    if len(bytes_list) < 13:
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

@app.get("/")
def root():
    return {"message": "API đang chạy, truy cập /hitmd5 để lấy dự đoán"}

history = []
adjustment_factor = 0.0
wrong_streak = 0
previous_prediction = None
previous_external_session_id = None

@app.get("/hitmd5")
def predict():
    global history, adjustment_factor, wrong_streak, previous_prediction, previous_external_session_id

    try:
        response = requests.get("https://hitcolubnhumaubuoitao.onrender.com/txmd5")
        response.raise_for_status()
        data = response.json()
    except RequestException as e:
        # Nếu muốn chắc chắn UTF-8, bạn có thể làm thế này, nhưng HTTPException thường đủ
        # return JSONResponse(status_code=500, content={"detail": f"Không thể lấy dữ liệu từ API bên ngoài: {e}"}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail=f"Không thể lấy dữ liệu từ API bên ngoài: {e}")
    except JSONDecodeError:
        # return JSONResponse(status_code=500, content={"detail": "Dữ liệu nhận được không phải định dạng JSON hợp lệ."}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail="Dữ liệu nhận được không phải định dạng JSON hợp lệ.")
    except Exception as e:
        # return JSONResponse(status_code=500, content={"detail": f"Lỗi không xác định khi lấy dữ liệu: {e}"}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định khi lấy dữ liệu: {e}")

    if not isinstance(data, dict) or "ket_qua_phien_truoc" not in data or "thong_tin_phien_sau" not in data:
        # return JSONResponse(status_code=500, content={"detail": "Cấu trúc dữ liệu JSON từ API bên ngoài không đúng định dạng mong đợi."}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail="Cấu trúc dữ liệu JSON từ API bên ngoài không đúng định dạng mong đợi.")

    ket_qua_phien_truoc = data["ket_qua_phien_truoc"]
    thong_tin_phien_sau = data["thong_tin_phien_sau"]

    if "Phien" not in ket_qua_phien_truoc or "rs" not in ket_qua_phien_truoc or "d1" not in ket_qua_phien_truoc or "d2" not in ket_qua_phien_truoc or "d3" not in ket_qua_phien_truoc:
        # return JSONResponse(status_code=500, content={"detail": "Dữ liệu 'ket_qua_phien_truoc' thiếu thông tin cần thiết (Phien, rs, d1, d2, d3)."}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail="Dữ liệu 'ket_qua_phien_truoc' thiếu thông tin cần thiết (Phien, rs, d1, d2, d3).")
    
    if "md5" not in thong_tin_phien_sau:
        # return JSONResponse(status_code=500, content={"detail": "Dữ liệu 'thong_tin_phien_sau' thiếu thông tin cần thiết (md5)."}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail="Dữ liệu 'thong_tin_phien_sau' thiếu thông tin cần thiết (md5).")
    
    session_id_vua_ket_thuc = ket_qua_phien_truoc["Phien"]
    result_vua_ket_thuc = ket_qua_phien_truoc["rs"].lower()
    dice_vua_ket_thuc = f"{ket_qua_phien_truoc['d1']}-{ket_qua_phien_truoc['d2']}-{ket_qua_phien_truoc['d3']}"

    md5_input_phien_sap_toi = thong_tin_phien_sau["md5"]
    
    if previous_prediction is not None and previous_external_session_id is not None and session_id_vua_ket_thuc == previous_external_session_id:
        if previous_prediction.lower() != result_vua_ket_thuc:
            wrong_streak += 1
        else:
            wrong_streak = 0
        
        history.append(result_vua_ket_thuc)
        if len(history) > 100:
            history.pop(0)

        tai_count = history.count("tài")
        xiu_count = history.count("xỉu")
        
        if tai_count > xiu_count:
            adjustment_factor = min(0.1, 0.05 + 0.01 * wrong_streak)
        elif xiu_count > tai_count:
            adjustment_factor = max(-0.1, -0.05 - 0.01 * wrong_streak)
        else:
            adjustment_factor = 0.0

        if wrong_streak >= 3:
            adjustment_factor *= 1.5
    else:
        wrong_streak = 0
        adjustment_factor = 0.0
        history = []

    try:
        hash_md5_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'md5')
        hash_sha256_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'sha256')
        hash_sha512_phien_sap_toi = generate_hash(md5_input_phien_sap_toi, 'sha512')

        md5_ratio, xiu_ratio, sel_bytes = analyze_md5_bytes(hash_md5_phien_sap_toi, adjustment_factor)
        bit_1, bit_0 = analyze_bits(hash_sha256_phien_sap_toi)
        even, odd = analyze_even_odd_chars(hash_sha512_phien_sap_toi)
        new_prediction_for_next_session = final_decision((md5_ratio, xiu_ratio), bit_1 - bit_0, even - odd)
    except ValueError as ve:
        # return JSONResponse(status_code=500, content={"detail": f"Lỗi trong quá trình phân tích hash: {ve}"}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail=f"Lỗi trong quá trình phân tích hash: {ve}")
    except Exception as e:
        # return JSONResponse(status_code=500, content={"detail": f"Lỗi không xác định trong quá trình phân tích hash: {e}"}, media_type="application/json; charset=utf-8")
        raise HTTPException(status_code=500, detail=f"Lỗi không xác định trong quá trình phân tích hash: {e}")

    previous_prediction = new_prediction_for_next_session
    previous_external_session_id = session_id_vua_ket_thuc + 1

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
        }
    }
