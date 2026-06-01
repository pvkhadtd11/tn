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
    """Lấy câu hỏi học tập theo bài (MCQ hoặc TF) – KHÔNG BAO GỒM correct_option"""
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
    """Lấy câu hỏi cho đề thi – KHÔNG BAO GỒM correct_option"""
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

# ========== API CHẤM ĐIỂM (SERVER) ==========
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
        answers = data.get('answers', {})
        
        if not ten_hoc_sinh or not lop:
            return jsonify({'error': 'Thiếu thông tin học sinh'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        
        total_score = 0.0
        details = {}
        
        # ---------- XỬ LÝ MCQ ----------
        if 'mcq' in answers and answers['mcq']:
            mcq_answers = answers['mcq']
            q_ids = list(mcq_answers.keys())
            if q_ids:
                placeholders = ','.join(['%s'] * len(q_ids))
                cursor.execute(f"""
                    SELECT id, correct_option FROM questions
                    WHERE id IN ({placeholders})
                """, q_ids)
                rows = cursor.fetchall()
                print("DEBUG MCQ rows:", rows)  # Xem console
                
                correct_map = {}
                for row in rows:
                    qid = row['id']
                    opt = row['correct_option']
                    if opt:
                        opt = str(opt).strip().upper()
                    correct_map[qid] = opt
                
                mcq_score = 0
                mcq_detail = {}
                for qid, user_choice in mcq_answers.items():
                    user_choice_upper = user_choice.upper().strip() if user_choice else ''
                    correct_opt = correct_map.get(qid)
                    print(f"   QID {qid}: user={user_choice_upper}, correct={correct_opt}")
                    if correct_opt and correct_opt == user_choice_upper:
                        mcq_score += 0.25
                        mcq_detail[qid] = {'status': 'correct', 'correct_option': correct_opt}
                    else:
                        mcq_detail[qid] = {'status': 'wrong', 'correct_option': correct_opt}
                total_score += mcq_score
                details['mcq'] = {'score': mcq_score, 'detail': mcq_detail}
        
        # ---------- XỬ LÝ TF CHO ĐỀ THI ----------
        if exam_id and 'tf' in answers and answers['tf']:
            tf_answers = answers['tf']
            cursor.execute("""
                SELECT id FROM questions
                WHERE exam_id = %s AND (type = 'tf' OR type = 'TF')
                ORDER BY id
            """, (exam_id,))
            tf_rows = cursor.fetchall()
            tf_ids = [row['id'] for row in tf_rows]
            print("DEBUG TF ids:", tf_ids)
            
            if len(tf_ids) >= 6:
                common_ids = tf_ids[:2]
                khmt_ids = tf_ids[2:4]
                thud_ids = tf_ids[4:6]
            else:
                common_ids = tf_ids
                khmt_ids = []
                thud_ids = []
            
            has_khmt = any(any(tf_answers.get(qid, {}).values()) for qid in khmt_ids)
            has_thud = any(any(tf_answers.get(qid, {}).values()) for qid in thud_ids)
            
            selected_ban = None
            if has_khmt and has_thud:
                selected_ban = "BOTH"
            elif has_khmt:
                selected_ban = "KHMT"
            elif has_thud:
                selected_ban = "THUD"
            
            ids_to_cham = common_ids.copy()
            if selected_ban == "KHMT":
                ids_to_cham.extend(khmt_ids)
            elif selected_ban == "THUD":
                ids_to_cham.extend(thud_ids)
            
            if ids_to_cham:
                placeholders = ','.join(['%s'] * len(ids_to_cham))
                cursor.execute(f"""
                    SELECT id, correct_option FROM questions
                    WHERE id IN ({placeholders})
                """, ids_to_cham)
                correct_rows = cursor.fetchall()
                correct_map = {}
                for row in correct_rows:
                    opts = row['correct_option']
                    if isinstance(opts, str):
                        opts = [x.strip().upper() for x in opts.split(',')]
                    correct_map[row['id']] = opts
                print("DEBUG correct_map TF:", correct_map)
            
            TF_POINTS = {1: 0.1, 2: 0.25, 3: 0.5, 4: 1.0}
            tf_score = 0.0
            tf_details = {}
            
            for qid in ids_to_cham:
                user_choices = tf_answers.get(qid, {})
                correct_opts = correct_map.get(qid, [])
                correct_count = 0
                stmt_results = {}
                for letter in ['a', 'b', 'c', 'd']:
                    user_val = user_choices.get(letter)
                    if user_val:
                        is_correct = (user_val == "Đúng" and letter.upper() in correct_opts) or \
                                     (user_val == "Sai" and letter.upper() not in correct_opts)
                        if is_correct:
                            correct_count += 1
                            stmt_results[letter] = 'correct'
                        else:
                            stmt_results[letter] = 'wrong'
                    else:
                        stmt_results[letter] = 'not_answered'
                score = TF_POINTS.get(correct_count, 0)
                tf_score += score
                tf_details[qid] = {
                    'score': score,
                    'statements': stmt_results,
                    'correct_option': correct_opts
                }
            total_score += tf_score
            details['tf'] = {'score': tf_score, 'detail': tf_details}
        
        # Lưu kết quả
        total_questions = len(answers.get('mcq', {})) + sum(len(v) for v in answers.get('tf', {}).values())
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ket_qua (ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem, subject, exam_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (ten_hoc_sinh, lop, bai_start, bai_end, total_questions, total_score, subject, exam_id))
        conn.commit()
        cur.close()
        
        return jsonify({
            'message': 'Success',
            'total_score': total_score,
            'details': details
        }), 200
        
    except Exception as e:
        print(f"❌ Lỗi submit: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()
            
@app.route('/debug-correct', methods=['GET'])
def debug_correct():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("SELECT id, correct_option FROM questions WHERE id IN (1111, 1135) LIMIT 5")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

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

# ========== API LẤY DANH SÁCH LỚP (dùng cho dropdown) ==========
@app.route('/api/lop', methods=['GET'])
def get_lop():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT lop FROM hoc_sinh ORDER BY lop")
        rows = cursor.fetchall()
        cursor.close()
        classes = [row[0] for row in rows]
        return jsonify(classes), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# ========== API LẤY DANH SÁCH HỌC SINH THEO LỚP ==========
@app.route('/api/hoc-sinh', methods=['GET'])
def get_hoc_sinh():
    conn = None
    lop = request.args.get('lop')
    if not lop:
        return jsonify({"error": "Missing lop parameter"}), 400
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute("SELECT ten FROM hoc_sinh WHERE lop = %s ORDER BY ten", (lop,))
        students = cursor.fetchall()
        cursor.close()
        return jsonify(students), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
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
        return {"status": "ok", "db": "connected"}, 200
    except Exception as e:
        return {"status": "error", "db": "down", "message": str(e)}, 500
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
