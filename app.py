import os
import urllib.parse
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2 import extras

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["https://playgame.id.vn"])

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
        bai_start = request.args.get('baiStart', type=int)
        bai_end = request.args.get('baiEnd', type=int)

        query = """
            SELECT 
                id, question, option_a, option_b, option_c, option_d, 
                correct_option, image_path, khoi, bai, 
                "optionA_i", "optionB_i", "optionC_i", "optionD_i" 
            FROM questions
        """
        query_params = []
        conditions = []

        if khoi:
            conditions.append("khoi = %s")
            query_params.append(khoi)

        if bai_start is not None and bai_end is not None:
            if bai_start == bai_end:
                conditions.append("bai = %s")
                query_params.append(bai_start)
            else:
                conditions.append("bai BETWEEN %s AND %s")
                query_params.extend([bai_start, bai_end])

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

@app.route('/history', methods=['GET'])
def get_history():
    conn = None
    student_name = request.args.get('student_name')
    lop = request.args.get('lop')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
        cursor.execute("""
            SELECT id, ten_hoc_sinh, lop, bai_start, bai_end, tong_so_cau_hoi, diem 
            FROM ket_qua 
            WHERE ten_hoc_sinh = %s AND lop = %s
        """, (student_name, lop))
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
        
        cursor.execute("""
            SELECT lop, bai_start, COUNT(*) as so_hoc_sinh
            FROM ket_qua
            WHERE lop = %s AND bai_start = %s
            GROUP BY lop, bai_start
        """, (lop, bai))
        students_per_class_and_bai = cursor.fetchall()

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
