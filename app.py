import os
import json
import urllib.parse
from flask import Flask, jsonify, request, abort
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import psycopg2
from psycopg2 import pool, extras
from dotenv import load_dotenv
from datetime import datetime

# ---------------- Load Environment ----------------
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": os.getenv("FRONTEND_URL", "*")}})

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)

# ---------------- Database Connection ----------------
def create_connection_pool():
    try:
        db_url = os.getenv("DATABASE_URL")

        # Nếu Render cung cấp DATABASE_URL dạng full URI (postgres://...)
        if db_url:
            result = urllib.parse.urlparse(db_url)
            return psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port,
                sslmode="require"
            )
        else:
            # Dành cho local test hoặc môi trường thủ công
            return psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                database=os.getenv("PG_DATABASE"),
                user=os.getenv("PG_USER"),
                password=os.getenv("PG_PASSWORD"),
                host=os.getenv("PG_HOST"),
                port=os.getenv("PG_PORT", 5432),
                sslmode=os.getenv("PG_SSLMODE", "require")
            )
    except Exception as e:
        print(f"❌ Failed to create DB pool: {e}")
        raise SystemExit("Database pool initialization failed")

db_pool = create_connection_pool()

def get_db_connection():
    try:
        return db_pool.getconn()
    except psycopg2.Error as e:
        print(f"⚠️ DB connection error: {e}")
        return None

def release_db_connection(conn):
    if conn:
        db_pool.putconn(conn)

# ---------------- API ROUTES ----------------

# Health check (Render gọi để kiểm tra container)
@app.route("/")
def health():
    return jsonify({"status": "ok"}), 200

# 1️⃣ Get questions
@app.route("/api/questions", methods=["GET"])
@limiter.limit("100/hour")
def get_questions():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT id, question, option_a, option_b, option_c, option_d, image FROM questions")
            questions = cursor.fetchall()
        return jsonify(questions)
    except Exception as e:
        print(f"❌ Query error: {e}")
        return jsonify({"error": "Failed to fetch questions"}), 500
    finally:
        release_db_connection(conn)

# 2️⃣ Submit answers
@app.route("/api/submit", methods=["POST"])
@limiter.limit("10/hour")
def submit_answers():
    data = request.get_json(silent=True)
    if not data:
        abort(400, "Invalid JSON payload")

    required_fields = ["username", "score", "answers"]
    if not all(k in data for k in required_fields):
        abort(400, "Missing required fields")

    username = data["username"]
    score = data["score"]
    answers = data["answers"]

    if not isinstance(username, str) or not (3 <= len(username) <= 50):
        abort(400, "Username must be string between 3–50 characters")
    if not isinstance(score, int) or score < 0:
        abort(400, "Score must be a non-negative integer")
    if not isinstance(answers, list):
        abort(400, "Answers must be a list")

    try:
        details = json.dumps(answers)
    except Exception:
        abort(400, "Invalid answers format")

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO results (username, score, answers, created_at) VALUES (%s, %s, %s, %s)",
                (username, score, details, datetime.utcnow())
            )
            conn.commit()
        return jsonify({"message": "Results saved successfully!"}), 201
    except Exception as e:
        print(f"❌ Insert error: {e}")
        conn.rollback()
        return jsonify({"error": "Failed to save results"}), 500
    finally:
        release_db_connection(conn)

# 3️⃣ Get leaderboard
@app.route("/api/results", methods=["GET"])
@limiter.limit("50/hour")
def get_results():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, username, score, created_at
                FROM results
                ORDER BY score DESC, created_at DESC
                LIMIT 50
            """)
            results = cursor.fetchall()
        return jsonify(results)
    except Exception as e:
        print(f"❌ Query error: {e}")
        return jsonify({"error": "Failed to fetch results"}), 500
    finally:
        release_db_connection(conn)

# ---------------- Error Handling ----------------
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": str(error.description)}), 400

# ---------------- Main Entry ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"✅ Flask app running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=not os.getenv("RENDER"))
