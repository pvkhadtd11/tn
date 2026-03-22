import os
import random
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

origins = [
    "https://playgame.id.vn",
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
                   khoi, bai, subject
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
                   khoi, subject, exam_id
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
        
        return jsonify(final_questions)
    
    except psycopg2.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/submit-quiz', methods=['POST'])
def submit_quiz():
    conn = None
    try:
        data = request.get_json()
        ten_hoc_sinh = data.get('ten_hoc_sinh')
        lop = data.get('lop')
        bai_start = data.get('bai_start')
        bai_end = data.get('bai_end')
        subject = data.get('subject')
        exam_id = data.get('exam_id')
        user_answers = data.get('answers') # Dictionary: {question_id: selected_option, ...}

        if not ten_hoc_sinh or not lop or not user_answers:
            return jsonify({'error': 'Thiếu thông tin'}), 400

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)

        # Lấy tất cả đáp án đúng cho các câu hỏi mà học sinh đã trả lời
        question_ids = list(user_answers.keys())
        placeholders = ','.join(['%s'] * len(question_ids))
        cursor.execute(f"""
            SELECT id, correct_option
            FROM questions
            WHERE id IN ({placeholders})
        """, question_ids)
        correct_answers = {row['id']: row['correct_option'] for row in cursor.fetchall()}

        # Chấm điểm
        score = 0
        for q_id, user_ans in user_answers.items():
            if q_id in correct_answers:
                if user_ans == correct_answers[q_id]:
                    score += 1

        total_questions = len(user_answers)
        # Lưu kết quả vào bảng ket_qua
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ket_qua (ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem, subject, exam_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (ten_hoc_sinh, lop, bai_start, bai_end, total_questions, score, subject, exam_id))
        conn.commit()
        cur.close()

        return jsonify({
            'message': 'Success',
            'score': score,
            'total': total_questions
        }), 201

    except Exception as e:
        print(f"❌ Lỗi khi chấm điểm: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# ========== API LỊCH SỬ ==========
@app.route('/history', methods=['GET'])
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
@app.route('/statistics', methods=['GET'])
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
