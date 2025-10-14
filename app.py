import os
import urllib.parse
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import psycopg2
from psycopg2 import extras
# from xuli import process_and_store_questions 
import openpyxl 

app = Flask(__name__)
FRONTEND_URL = os.getenv("FRONTEND_URL", "*") 
CORS(app, resources={r"/*": {"origins": FRONTEND_URL}}) 

# ---------------- PostgreSQL Connection ----------------

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ConnectionError("DATABASE_URL environment variable is not set.")

    result = urllib.parse.urlparse(db_url)
    
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode="require"
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

        query = """
            SELECT 
                id, question, option_a, option_b, option_c, option_d, 
                correct_option, image_path, khoi, bai, 
                "optionA_i", "optionB_i", "optionC_i", "optionD_i" 
            FROM questions
        """
        query_params = []
        conditions = []

        # Lọc theo khối nếu có
        if khoi:
            conditions.append("khoi = %s")
            query_params.append(khoi)

        # Lọc theo bài nếu có
        if bai_start and bai_end:
            try:
                bai_start_int = int(bai_start)
                bai_end_int = int(bai_end)

                if bai_start_int == bai_end_int:
                    conditions.append(
                        "( (bai ~ '^[0-9]+$' AND CAST(bai AS INTEGER) = %s) OR bai IN ('gki','cki','gkii','ckii') )"
                    )
                    query_params.append(bai_start_int)
                else:
                    conditions.append(
                        "( (bai ~ '^[0-9]+$' AND CAST(bai AS INTEGER) BETWEEN %s AND %s) OR bai IN ('gki','cki','gkii','ckii') )"
                    )
                    query_params.extend([bai_start_int, bai_end_int])
            except (ValueError, TypeError):
                # Nếu không ép kiểu được thì fallback so sánh chuỗi
                if bai_start == bai_end:
                    conditions.append("bai = %s")
                    query_params.append(bai_start)
                else:
                    conditions.append("bai >= %s AND bai <= %s")
                    query_params.extend([bai_start, bai_end])

        # Ghép điều kiện nếu có
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute(query, query_params)
        questions = cursor.fetchall()
        cursor.close()

        return jsonify(questions)

    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    except ConnectionError as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

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
        
        cursor.execute("SELECT COUNT(*) FROM ket_qua")
        result = cursor.fetchone() 
        new_id = result[0] + 1 
        
        # GIỮ NGUYÊN INSERT và logic cũ.
        cursor.execute("""
            INSERT INTO ket_qua (id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (new_id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem))
        conn.commit()
        cursor.close()
        
        return jsonify({"message": "Success"}), 201
    except psycopg2.Error as err:
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
        
        # SỬ DỤNG CỘT TỪ BẢNG KET_QUA BẠN CUNG CẤP: ten_hoc_sinh, lop, diem
        cursor.execute("SELECT ten_hoc_sinh, lop, diem FROM ket_qua")
        results = cursor.fetchall()
        cursor.close()
        
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
        
        return send_file(excel_filename, as_attachment=True, download_name='quiz_results.xlsx')
    
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e: 
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
        # SỬ DỤNG CỘT TỪ BẢNG KET_QUA BẠN CUNG CẤP
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
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor) 
        
        # SỬ DỤNG CỘT TỪ BẢNG KET_QUA BẠN CUNG CẤP
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)