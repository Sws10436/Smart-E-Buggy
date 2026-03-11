from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

DB = "buggy.db"

# ---------------------------
# Initialize Database
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gps_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL,
            longitude REAL,
            speed REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Root Route (for testing)
# ---------------------------
@app.route("/")
def home():
    return "Smart E-Buggy Backend Running"

# ---------------------------
# API: Receive Data from ESP8266
# ---------------------------
@app.route("/api/update-location", methods=["POST"])
def update_location():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON received"}), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    speed = data.get("speed_kmh")

    if latitude is None or longitude is None or speed is None:
        return jsonify({"error": "Missing data fields"}), 400

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO gps_logs (latitude, longitude, speed, timestamp)
        VALUES (?, ?, ?, ?)
    """, (latitude, longitude, speed, datetime.now()))

    conn.commit()
    conn.close()

    return jsonify({"message": "Location updated successfully"}), 200


# ---------------------------
# API: Send Latest Data to Frontend
# ---------------------------
@app.route("/")
def home():
    return "Smart E-Buggy Backend Running"
@app.route("/api/latest", methods=["GET"])
def latest():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT latitude, longitude, speed, timestamp
        FROM gps_logs
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify({
            "latitude": row[0],
            "longitude": row[1],
            "speed": row[2],
            "timestamp": row[3]
        })

    return jsonify({"error": "No data found"}), 404


# ---------------------------
# Run Server (Render Compatible)
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)