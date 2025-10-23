from flask import Flask, request, jsonify

app = Flask(__name__)

# Test route (to verify deployment works)
@app.route("/")
def home():
    return "Smart E-Buggy Tracker is LIVE ✅"

# API endpoint where ESP32 will send data later
@app.route("/api/location", methods=["POST"])
def receive_location():
    data = request.get_json()
    print("Received:", data)
    return jsonify({"status": "ok", "message": "data received", "data": data})

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

