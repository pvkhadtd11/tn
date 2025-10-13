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

# Load environment variables
load_dotenv()

app = Flask(__name__)
# Restrict CORS to specific frontend domain (update with your domain)
CORS(app, resources={r"/api/*": {"origins": os.getenv("FRONTEND_URL", "*")}})
# Rate limiting to prevent abuse
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

# Database connection pool (min 1, max 10 connections)
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        database=urllib.parse.urlparse(os.getenv("DATABASE_URL")).path[1:],
        user=urllib.parse.urlparse(os.getenv("DATABASE_URL")).username,
        password=urllib.parse.urlparse(os.getenv("DATABASE_URL")).password,
        host=urllib.parse.urlparse(os.getenv("DATABASE_URL")).hostname,
        port=urllib.parse.urlparse(os.getenv("DATABASE_URL")).port,
        sslmode="require"
    )
except psycopg2.Error as e:
    print(f"Failed to create DB pool: {e}")
    raise SystemExit("Database pool initialization failed")

# Get DB connection from pool
def get_db_connection():
    try:
        conn = db_pool.getconn()
        return conn
    except psycopg2.Error as e:
        print(f"DB connection error: {e}")
        return None

# Release DB connection back to pool
def release_db_connection(conn):
    if conn:
        db_pool.putconn(conn)

# 1. Get list of questions
@app.route("/api/questions", methods=["GET"])
@limiter.limit("100/hour")  # Limit requests to prevent scraping
def get_questions():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, question, option_a, option_b, option_c, option_d, image FROM questions")
        questions = cursor.fetchall()
        cursor.close()
        return jsonify(questions)
    except psycopg2.Error as e:
        print(f"Query error: {e}")
        return jsonify({"error": "Failed to fetch questions"}), 500
    finally:
        release_db_connection(conn)

# 2. Submit quiz results
@app.route("/api/submit", methods=["POST"])
@limiter.limit("10/hour")  # Limit submissions to prevent spam
def submit_answers():
    data = request.get_json(silent=True)
    if not data:
        abort(400, "Invalid JSON payload")

    # Validate input
    required_fields = ["username", "score", "answers"]
    if not all(k in data for k in required_fields):
        abort(400, "Missing required fields")
    
    username = data["username"]
    score = data["score"]
    answers = data["answers"]
    
    # Validate types and constraints
    if not isinstance(username, str) or len(username) < 3 or len(username) > 50:
        abort(400, "Username must be string between 3-50 characters")
    if not isinstance(score, int) or score < 0:
        abort(400, "Score must be a non-negative integer")
    if not isinstance(answers, list):
        abort(400, "Answers must be a list")

    # Serialize answers to JSON
    try:
        details = json.dumps(answers)
    except (TypeError, ValueError):
        abort(400, "Invalid answers format")

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO results (username, score, answers, created_at) VALUES (%s, %s, %s, %s)",
            (username, score, details, datetime.utcnow())
        )
        conn.commit()
        cursor.close()
        return jsonify({"message": "Results saved successfully!"}), 201
    except psycopg2.Error as e:
        print(f"Insert error: {e}")
        conn.rollback()
        return jsonify({"error": "Failed to save results"}), 500
    finally:
        release_db_connection(conn)

# 3. Get leaderboard
@app.route("/api/results", methods=["GET"])
@limiter.limit("50/hour")  # Limit leaderboard requests
def get_results():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, username, score, created_at FROM results ORDER BY score DESC, created_at DESC LIMIT 50")
        results = cursor.fetchall()
        cursor.close()
        return jsonify(results)
    except psycopg2.Error as e:
        print(f"Query error: {e}")
        return jsonify({"error": "Failed to fetch results"}), 500
    finally:
        release_db_connection(conn)

# Error handler for 400 Bad Request
@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": str(error.description)}), 400

# Main entry point
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if os.environ.get("RENDER"):
        print("Running in production mode...")
    else:
        app.run(host="0.0.0.0", port=port, debug=True)