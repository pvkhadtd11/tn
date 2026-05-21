import os
import random
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv
from flask import render_template

# Load environment variables
load_dotenv()

app = Flask(__name__)

origins = [
    "https://phamkha.io.vn",
    "https://www.phamkha.io.vn",
    "http://localhost:5000"
]
CORS(app, supports_credentials=True, origins=origins)

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ConnectionError("DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(db_url, sslmode="require")
    return conn

@app.route('/api/hoc-sinh', methods=['GET'])
def get_hoc_sinh():
    lop = request.args.get('lop')
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
    if lop:
        cursor.execute("SELECT ten, lop FROM hoc_sinh WHERE lop = %s ORDER BY ten", (lop,))
    else:
        cursor.execute("SELECT ten, lop FROM hoc_sinh ORDER BY lop, ten")
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(students)

@app.route('/api/lop', methods=['GET'])
def get_lop():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("SELECT DISTINCT lop FROM hoc_sinh ORDER BY lop")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([row['lop'] for row in rows])
    
# ========== API CHO TAB 1 & 2 (HỌC THEO BÀI) ==========
@app.route('/api/questions', methods=['GET'])
def get_questions():
    """Lấy câu hỏi học tập theo bài (MCQ hoặc TF)"""
    conn = None
    try:
        question_type = request.args.get('type')  # 'mcq' hoặc 'tf'
        khoi = request.args.get('khoi', type=int)
        bai_start = request.args.get('baiStart', type=int)
        bai_end = request.args.get('baiEnd', type=int)
        subject = request.args.get('subject')
        
        # Chỉ lấy câu hỏi học tập (exam_id IS NULL)
        query = """
            SELECT id, type, question, 
                   option_a, option_b, option_c, option_d, 
                   correct_option, khoi, bai, subject
            FROM questions
            WHERE exam_id IS NULL
        """
        query_params = []
        conditions = []
        
        if question_type:
            conditions.append("type = %s")
            query_params.append(question_type)
        
        if khoi:
            conditions.append("khoi = %s")
            query_params.append(khoi)
        
        if subject:
            conditions.append("subject = %s")
            query_params.append(subject)
        
        if bai_start is not None and bai_end is not None:
            if bai_start == bai_end:
                conditions.append("bai = %s")
                query_params.append(bai_start)
            else:
                conditions.append("bai BETWEEN %s AND %s")
                query_params.extend([bai_start, bai_end])
        
        if conditions:
            query += " AND " + " AND ".join(conditions)
        
        query += " ORDER BY bai, id"
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute(query, query_params)
        questions = cursor.fetchall()
        cursor.close()
        
        # Xử lý correct_option cho TF (chuyển chuỗi 'A,B,C' thành mảng)
        for q in questions:
            if q['type'] == 'tf' and isinstance(q['correct_option'], str):
                if ',' in q['correct_option']:
                    q['correct_option'] = q['correct_option'].split(',')
        
        return jsonify(questions)
    
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

# ========== API CHO TAB 3 (ĐỀ THI) ==========
@app.route('/api/exams', methods=['GET'])
def get_exams():
    """Lấy danh sách các đề thi có sẵn"""
    conn = None
    try:
        khoi = request.args.get('khoi', type=int)
        subject = request.args.get('subject')
        
        query = """
            SELECT DISTINCT exam_id 
            FROM questions 
            WHERE exam_id IS NOT NULL 
              AND khoi = %s 
              AND subject = %s
            ORDER BY exam_id
        """
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute(query, (khoi, subject))
        exams = cursor.fetchall()
        cursor.close()
        
        return jsonify(exams)
    
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/exam-questions', methods=['GET'])
def get_exam_questions():
    """Lấy câu hỏi cho đề thi"""
    conn = None
    try:
        exam_id = request.args.get('exam_id', type=int)
        khoi = request.args.get('khoi', type=int)
        subject = request.args.get('subject')
        
        if not exam_id:
            return jsonify({"error": "exam_id is required"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        
        query = """
            SELECT id, type, question, 
                   option_a, option_b, option_c, option_d, 
                   correct_option, khoi, subject, exam_id
            FROM questions
            WHERE exam_id = %s AND khoi = %s AND subject = %s
            ORDER BY id
        """
        cursor.execute(query, (exam_id, khoi, subject))
        all_questions = cursor.fetchall()
        cursor.close()
        
        # Tách MCQ và TF
        mcq_questions = [q for q in all_questions if q['type'] == 'mcq']
        tf_questions = [q for q in all_questions if q['type'] == 'tf']
        
        # Xáo trộn thứ tự câu hỏi
        random.shuffle(mcq_questions)
        random.shuffle(tf_questions)
        
        # Ghép lại: MCQ trước, TF sau
        final_questions = mcq_questions + tf_questions
        
        # Xử lý correct_option cho TF
        for q in final_questions:
            if q['type'] == 'tf' and isinstance(q['correct_option'], str):
                if ',' in q['correct_option']:
                    q['correct_option'] = q['correct_option'].split(',')
        
        return jsonify(final_questions)
    
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

# ========== API NỘP BÀI ==========
@app.route('/api/submit', methods=['POST'])
def submit_quiz():
    conn = None
    data = request.json
    ten_hoc_sinh = data.get('ten_hoc_sinh')
    lop = data.get('lop')
    bai_start = data.get('bai_start')
    bai_end = data.get('bai_end')
    tong_so_cau_hoi = data.get('tong_so_cau_hoi')
    diem = data.get('diem')
    subject = data.get('subject')
    exam_id = data.get('exam_id')
    
    print(f"📝 Nhận dữ liệu: {data}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM ket_qua")
        result = cursor.fetchone() 
        new_id = result[0] + 1 
        
        # Thêm subject và exam_id nếu có
        cursor.execute("""
            INSERT INTO ket_qua (id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem, subject, exam_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (new_id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem, subject, exam_id))
        conn.commit()
        cursor.close()
        
        print(f"✅ Đã lưu kết quả: {ten_hoc_sinh} - {diem}/{tong_so_cau_hoi}")
        return jsonify({"message": "Success"}), 201
    except psycopg2.Error as err:
        if conn:
            conn.rollback() 
        print(f"❌ Lỗi: {err}")
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

# ========== API LỊCH SỬ ==========
@app.route('/api/history', methods=['GET'])
def get_history():
    conn = None
    student_name = request.args.get('student_name')
    lop = request.args.get('lop')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute("""
            SELECT id, ten_hoc_sinh, lop, bai_start, bai_end, 
                   tong_so_cau_hoi, diem, subject, exam_id, created_at
            FROM ket_qua 
            WHERE ten_hoc_sinh = %s AND lop = %s
            ORDER BY id DESC
        """, (student_name, lop))
        results = cursor.fetchall()
        cursor.close()
        
        # Chuyển đổi datetime thành string
        for result in results:
            if result.get('created_at'):
                result['created_at'] = result['created_at'].isoformat()
        
        return jsonify(results), 200
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

# ========== API THỐNG KÊ ==========
@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    conn = None
    lop = request.args.get('lop')
    bai = request.args.get('bai')
    subject = request.args.get('subject')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor) 
        
        cursor.execute("""
            SELECT lop, bai_start, COUNT(*) as so_hoc_sinh
            FROM ket_qua
            WHERE lop = %s AND bai_start = %s AND subject = %s
            GROUP BY lop, bai_start
        """, (lop, bai, subject))
        students_per_class_and_bai = cursor.fetchall()

        cursor.execute("""
            SELECT ten_hoc_sinh, diem, tong_so_cau_hoi, created_at
            FROM ket_qua
            WHERE lop = %s AND bai_start = %s AND subject = %s
            ORDER BY diem DESC, created_at DESC
        """, (lop, bai, subject))
        student_scores = cursor.fetchall()

        cursor.close()
        
        # Tính thêm thống kê tổng hợp
        scores = [s['diem'] for s in student_scores]
        stats = {
            "students_per_class_and_bai": students_per_class_and_bai,
            "student_scores": student_scores,
            "total_students": len(student_scores),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "highest_score": max(scores) if scores else 0,
            "lowest_score": min(scores) if scores else 0
        }
        
        return jsonify(stats), 200
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

# ========== HEALTH CHECK ==========
@app.route('/')
@app.route('/ping')
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route("/health")
def health():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        return {
            "status": "ok",
            "db": "connected"
        }, 200
    except Exception as e:
        return {
            "status": "error",
            "db": "down",
            "message": str(e)
        }, 500
    finally:
        if conn:
            conn.close()

# ========== CẤU HÌNH CACHE ==========
@app.after_request
def add_header(response):
    response.cache_control.no_store = True
    response.cache_control.no_cache = True
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 0
    response.pragma = 'no-cache'
    response.expires = 0
    return response

# 1. Trang quản trị
@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

# 2. API lấy danh sách tất cả học sinh (kèm thống kê)
@app.route('/api/all-students')
def get_all_students():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        # Dùng CASE WHEN để tránh chia cho 0 ngay trong SQL
        cursor.execute("""
            SELECT 
                ten_hoc_sinh,
                lop,
                COUNT(*) as submission_count,
                AVG(CASE WHEN tong_so_cau_hoi > 0 THEN diem * 100.0 / tong_so_cau_hoi ELSE 0 END) as avg_score,
                MIN(CASE WHEN tong_so_cau_hoi > 0 THEN diem * 100.0 / tong_so_cau_hoi ELSE 0 END) as min_score,
                MAX(CASE WHEN tong_so_cau_hoi > 0 THEN diem * 100.0 / tong_so_cau_hoi ELSE 0 END) as max_score
            FROM ket_qua
            GROUP BY ten_hoc_sinh, lop
            ORDER BY ten_hoc_sinh
        """)
        students = cursor.fetchall()
        
        for s in students:
            # Lấy lần đầu (id nhỏ nhất) – cũng kiểm tra tong_so_cau_hoi
            cursor.execute("""
                SELECT diem, tong_so_cau_hoi FROM ket_qua
                WHERE ten_hoc_sinh = %s AND lop = %s
                ORDER BY id ASC LIMIT 1
            """, (s['ten_hoc_sinh'], s['lop']))
            first = cursor.fetchone()
            if first and first['tong_so_cau_hoi'] and first['tong_so_cau_hoi'] > 0:
                s['first_score'] = round(first['diem'] * 100.0 / first['tong_so_cau_hoi'], 1)
            else:
                s['first_score'] = 0
            
            # Lấy lần cuối (id lớn nhất)
            cursor.execute("""
                SELECT diem, tong_so_cau_hoi FROM ket_qua
                WHERE ten_hoc_sinh = %s AND lop = %s
                ORDER BY id DESC LIMIT 1
            """, (s['ten_hoc_sinh'], s['lop']))
            last = cursor.fetchone()
            if last and last['tong_so_cau_hoi'] and last['tong_so_cau_hoi'] > 0:
                s['last_score'] = round(last['diem'] * 100.0 / last['tong_so_cau_hoi'], 1)
            else:
                s['last_score'] = 0
            
            # Xử lý avg_score có thể là None
            s['avg_score'] = round(s['avg_score'], 1) if s['avg_score'] else 0
        
        cursor.close()
        return jsonify(students)
    except Exception as e:
        print(f"Lỗi trong /api/all-students: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# 3. API lấy lịch sử làm bài của một học sinh (theo thứ tự thời gian tăng dần)
#    Lưu ý: endpoint /api/history đã tồn tại nhưng đang ORDER BY id DESC
#    Bạn có thể giữ nguyên hoặc tạo endpoint mới. Để tránh xung đột, tạo mới:
@app.route('/api/student-history', methods=['GET'])
def get_student_history():
    conn = None
    student_name = request.args.get('student_name')
    lop = request.args.get('lop')
    if not student_name or not lop:
        return jsonify({"error": "Thiếu tham số"}), 400
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute("""
            SELECT id, ten_hoc_sinh, lop, bai_start, bai_end, 
                   tong_so_cau_hoi, diem, subject, exam_id
            FROM ket_qua 
            WHERE ten_hoc_sinh = %s AND lop = %s
            ORDER BY id ASC
        """, (student_name, lop))
        history = cursor.fetchall()
        cursor.close()
        return jsonify(history)
    except Exception as e:
        print(f"Lỗi trong /api/student-history: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# 4. (Tùy chọn) API thống kê tổng quan cho các thẻ số
@app.route('/api/admin/stats')
def admin_stats():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute("SELECT COUNT(DISTINCT ten_hoc_sinh || '_' || lop) as total_students FROM ket_qua")
        total_students = cursor.fetchone()['total_students']
        cursor.execute("SELECT COUNT(*) as total_submissions FROM ket_qua")
        total_submissions = cursor.fetchone()['total_submissions']
        cursor.execute("SELECT AVG(diem * 100.0 / tong_so_cau_hoi) as avg_score FROM ket_qua")
        avg_score = cursor.fetchone()['avg_score'] or 0
        cursor.close()
        return jsonify({
            'total_students': total_students,
            'total_submissions': total_submissions,
            'avg_score': round(avg_score, 1)
        })
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
