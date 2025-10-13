import os
import urllib.parse
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import psycopg2
from psycopg2 import extras
# from xuli import process_and_store_questions # Giả định file này được giữ nguyên
import openpyxl 
# Lưu ý: openpyxl và send_file có thể gặp vấn đề trên môi trường Render 
# do việc ghi/đọc file tạm thời, nhưng logic được giữ nguyên theo yêu cầu.

app = Flask(__name__)
# Đặt FRONTEND_URL trong biến môi trường Render
FRONTEND_URL = os.getenv("FRONTEND_URL", "*") 
CORS(app, resources={r"/*": {"origins": FRONTEND_URL}}) 

# ---------------- PostgreSQL Connection ----------------
def get_db_connection():
    # Lấy DATABASE_URL từ biến môi trường của Render
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Dùng cho local test nếu không có DATABASE_URL
        # Bạn có thể cần thiết lập biến môi trường PG_HOST, PG_USER, ...
        raise ConnectionError("DATABASE_URL environment variable is not set.")

    # Phân tích cú pháp DATABASE_URL (postgres://user:pass@host:port/dbname)
    result = urllib.parse.urlparse(db_url)
    
    # Kết nối đến PostgreSQL
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode="require" # Bắt buộc cho Render/Hầu hết các dịch vụ đám mây
    )
    return conn

# ---------------- API ROUTES ----------------

@app.route('/questions', methods=['GET'])
def get_questions():
    conn = None
    try:
        khoi = request.args.get('khoi')
        bai_start = request.args.get('baiStart')
        bai_end = request.args.get('baiEnd')

        # Đảm bảo tất cả các cột cũ được SELECT, và IMAGE_PATH thay cho IMAGE
        query = """
            SELECT 
                id, question, option_a, option_b, option_c, option_d, 
                correct_answer, image_path, khoi, bai, 
                option_ai, option_bi, option_ci, option_di 
            FROM questions
        """
        query_params = []
        
        # Giữ nguyên logic lọc (Lưu ý: PostgreSQL dùng %s cho tham số)
        if khoi and bai_start and bai_end:
            query += " WHERE khoi = %s AND bai BETWEEN %s AND %s"
            query_params = [khoi, bai_start, bai_end]

        conn = get_db_connection()
        # Sử dụng RealDictCursor để lấy kết quả dạng Dict, dễ dàng truy cập bằng tên cột
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor) 
        cursor.execute(query, query_params)
        questions = cursor.fetchall()
        cursor.close()
        # Không cần conn.close() ở đây, kết nối sẽ được đóng ở finally nếu không dùng pool
        
        # Vì đã dùng RealDictCursor, questions đã là list of dicts.
        # Không cần chuyển đổi danh sách bằng cách truy cập chỉ số [0], [1], ... nữa.
        # Tuy nhiên, để giữ nguyên đầu ra JSON, ta có thể trả về trực tiếp
        return jsonify(questions)
        
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    except ConnectionError as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close() # Đóng kết nối đơn lẻ

@app.route('/submit', methods=['POST'])
def submit_quiz():
    conn = None
    data = request.json
    ten_hoc_sinh = data.get('ten_hoc_sinh')
    lop = data.get('lop')
    bai_start = data.get('bai_start')
    bai_end = data.get('bai_end')
    tong_so_cau_hoi = data.get('tong_so_cau_hoi')
    diem = data.get('diem')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # GIỮ NGUYÊN logic tính ID thủ công (Tuy nhiên, nên dùng SERIAL trong PostgreSQL)
        cursor.execute("SELECT COUNT(*) FROM ket_qua")
        result = cursor.fetchone() # Lấy kết quả dưới dạng Tuple
        new_id = result[0] + 1  # Tính id mới dựa trên số lượng dòng hiện có
        
        # GIỮ NGUYÊN INSERT với %s cho PostgreSQL
        cursor.execute("""
            INSERT INTO ket_qua (id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (new_id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem))
        conn.commit()
        cursor.close()
        
        return jsonify({"message": "Success"}), 201
    except psycopg2.Error as err:
        # Nếu có lỗi (ví dụ: duplicate key do tính ID thủ công), rollback
        if conn:
            conn.rollback() 
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/download-results', methods=['GET'])
def download_results():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Giả sử bảng ket_qua có các cột này
        cursor.execute("SELECT ten_hoc_sinh, lop, diem FROM ket_qua")
        results = cursor.fetchall()
        cursor.close()
        
        # Logic tạo Excel được giữ nguyên
        excel_directory = os.path.join(os.path.dirname(__file__), 'excel')
        excel_filename = os.path.join(excel_directory, 'quiz_results.xlsx')

        if not os.path.exists(excel_directory):
            os.makedirs(excel_directory)

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = 'Quiz Results'
        sheet.append(['Họ và Tên', 'Lớp', 'Điểm']) 
        for row in results:
            sheet.append(row)
        workbook.save(excel_filename)
        
        # Lưu ý: send_file có thể cần cấu hình đặc biệt cho môi trường Render
        return send_file(excel_filename, as_attachment=True, download_name='quiz_results.xlsx')
    
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e: # Bắt các lỗi khác như PermissionError, FileNotFoundError
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/history', methods=['GET'])
def get_history():
    conn = None
    student_name = request.args.get('student_name')
    lop = request.args.get('lop')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # GIỮ NGUYÊN cú pháp và logic
        cursor.execute("SELECT id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem FROM ket_qua WHERE ten_hoc_sinh = %s AND lop = %s", (student_name, lop))
        results = cursor.fetchall()
        cursor.close()
        
        return jsonify(results), 200
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/statistics', methods=['GET'])
def get_statistics():
    conn = None
    lop = request.args.get('lop')
    bai = request.args.get('bai')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor) # Dùng DictCursor cho dễ xử lý JSON
        
        # GIỮ NGUYÊN cú pháp và logic
        cursor.execute("""
            SELECT lop, bai_start, COUNT(*) as so_hoc_sinh
            FROM ket_qua
            WHERE lop = %s AND bai_start = %s
            GROUP BY lop, bai_start
        """, (lop, bai))
        students_per_class_and_bai = cursor.fetchall()

        # Lấy chi tiết điểm của các học sinh
        cursor.execute("""
            SELECT ten_hoc_sinh, diem, tong_so_cau_hoi
            FROM ket_qua
            WHERE lop = %s AND bai_start = %s
        """, (lop, bai))
        student_scores = cursor.fetchall()

        cursor.close()
        
        return jsonify({
            "students_per_class_and_bai": students_per_class_and_bai,
            "student_scores": student_scores
        }), 200
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/upload', methods=['POST'])
def upload_file():
    # ... (Giữ nguyên logic xử lý file và gọi process_and_store_questions)
    # Lưu ý: logic này dựa vào file xuli.py và có thể cần sửa đổi bên trong xuli.py
    # để xử lý kết nối PostgreSQL
    if 'question_file' not in request.files:
        return jsonify({"message": "No file part"}), 400

    file = request.files['question_file']
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400

    format_type = request.form.get('format_type')
    grade = request.form.get('grade')
    lesson_number = request.form.get('lesson_number')

    if file and file.filename.endswith('.docx') and format_type and grade and lesson_number:
        # Giả định thư mục 'uploads' tồn tại và có thể ghi được
        file_path = os.path.join('uploads', file.filename) 
        file.save(file_path)
        
        # Tách câu hỏi từ tệp và lưu vào CSDL dựa trên định dạng đã chọn
        # HÀM NÀY CẦN ĐƯỢC CẬP NHẬT TRONG FILE xuli.py ĐỂ DÙNG psycopg2
        process_and_store_questions(file_path, format_type, grade, lesson_number)
        return jsonify({"message": "File uploaded successfully!"}), 200

    return jsonify({"message": "Invalid file type or missing format type"}), 400

# ---------------- Khác ----------------

@app.after_request
def add_header(response):
    response.cache_control.no_store = True
    response.cache_control.no_cache = True
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 0
    response.pragma = 'no-cache'
    response.expires = 0
    return response

if __name__ == '__main__':
    # Dùng PORT được cung cấp bởi môi trường hosting (Render)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)