# main.py
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from dateutil import parser
from haversine import haversine, Unit
import os

# ---- Config ----
API_KEY = os.environ.get("API_KEY", "dev_key_please_change")
GEOfences = {
    "A": {"lat": 12.9710, "lon": 77.5946, "radius_m": 80},
    "B": {"lat": 12.9720, "lon": 77.5956, "radius_m": 80}
}
MIN_TRIP_TIME_S = 30
MIN_TRIP_DISTANCE_M = 20
EMISSION_FACTOR_KG_PER_KM = 0.20

# ---- App & DB ----
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ebuggy.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---- Models ----
class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String, default="")
    last_seen = db.Column(db.DateTime)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String, nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    speed_kmh = db.Column(db.Float, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False)

class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String, nullable=False)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    start_lat = db.Column(db.Float)
    start_lon = db.Column(db.Float)
    end_lat = db.Column(db.Float)
    end_lon = db.Column(db.Float)
    distance_m = db.Column(db.Float)
    duration_s = db.Column(db.Float)

# create tables (safe on import)
with app.app_context():
    db.create_all()

# ---- Helpers ----
def parse_iso(ts):
    try:
        if isinstance(ts, str):
            return parser.isoparse(ts)
        else:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except:
        return datetime.utcnow().replace(tzinfo=timezone.utc)

def inside_geofence(lat, lon, fence):
    d = haversine((lat, lon), (fence["lat"], fence["lon"]), unit=Unit.METERS)
    return d <= fence["radius_m"]

# minimal in-memory state for trip detection
device_state = {}

def detect_trip_and_record(device_id, lat, lon, ts):
    state = device_state.get(device_id, {"lastZone": None, "enter_time": None, "enter_pos": None})
    currentZone = None
    for zone_name, fence in GEOfences.items():
        if inside_geofence(lat, lon, fence):
            currentZone = zone_name
            break

    if state["lastZone"] is None and currentZone is not None:
        state["lastZone"] = currentZone
        state["enter_time"] = ts
        state["enter_pos"] = (lat, lon)
    elif state["lastZone"] == currentZone:
        pass
    elif state["lastZone"] is not None and currentZone is not None and state["lastZone"] != currentZone:
        enter_time = state["enter_time"]
        enter_pos = state["enter_pos"]
        duration = (ts - enter_time).total_seconds() if enter_time else None
        distance_m = haversine(enter_pos, (lat, lon), unit=Unit.METERS) if enter_pos else None
        if duration and distance_m and duration >= MIN_TRIP_TIME_S and distance_m >= MIN_TRIP_DISTANCE_M:
            trip = Trip(
                device_id=device_id,
                start_time=enter_time,
                end_time=ts,
                start_lat=enter_pos[0],
                start_lon=enter_pos[1],
                end_lat=lat,
                end_lon=lon,
                distance_m=distance_m,
                duration_s=duration
            )
            db.session.add(trip)
            db.session.commit()
        state["lastZone"] = currentZone
        state["enter_time"] = ts
        state["enter_pos"] = (lat, lon)
    else:
        if currentZone is None:
            state["lastZone"] = None
            state["enter_time"] = None
            state["enter_pos"] = None

    device_state[device_id] = state

# ---- Routes ----
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/location", methods=["POST"])
def api_location():
    data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    device_id = data.get("device_id") or data.get("deviceId") or data.get("device")
    api_key = data.get("api_key") or request.headers.get("X-API-KEY")
    if API_KEY and api_key != API_KEY:
        return jsonify({"status":"error","message":"invalid api key"}), 401
    try:
        lat = float(data.get("lat") or data.get("latitude"))
        lon = float(data.get("lon") or data.get("longitude"))
    except:
        return jsonify({"status":"error","message":"lat/lon missing or invalid"}), 400
    speed = float(data.get("speed_kmh") or data.get("speed") or 0)
    ts_raw = data.get("timestamp") or data.get("time")
    ts = parse_iso(ts_raw) if ts_raw else datetime.utcnow().replace(tzinfo=timezone.utc)

    dev = Device.query.filter_by(device_id=device_id).first()
    if not dev:
        dev = Device(device_id=device_id, name=device_id, last_seen=ts)
        db.session.add(dev)
        db.session.commit()
    else:
        dev.last_seen = ts
        db.session.commit()

    loc = Location(device_id=device_id, lat=lat, lon=lon, speed_kmh=speed, timestamp=ts)
    db.session.add(loc)
    db.session.commit()

    try:
        detect_trip_and_record(device_id, lat, lon, ts)
    except Exception as e:
        print("Trip detect error:", e)

    print("Received:", device_id, lat, lon, ts.isoformat())
    return jsonify({"status":"ok"})

@app.route('/api/devices/latest', methods=['GET'])
def api_devices_latest():
    q = db.session.query(Location.device_id, Location.lat, Location.lon, Location.speed_kmh, Location.timestamp).order_by(Location.timestamp.desc()).all()
    latest = {}
    for row in q:
        if row.device_id not in latest:
            latest[row.device_id] = {"device_id": row.device_id, "lat": row.lat, "lon": row.lon, "speed_kmh": row.speed_kmh, "timestamp": row.timestamp.isoformat()}
    return jsonify(list(latest.values()))

@app.route('/api/trips/summary', methods=['GET'])
def api_trips_summary():
    from sqlalchemy import func
    q = db.session.query(func.date(Trip.start_time).label("day"), func.count(Trip.id).label("cnt"), func.sum(Trip.distance_m).label("m_sum")).group_by(func.date(Trip.start_time)).order_by(func.date(Trip.start_time)).all()
    results = []
    total_trips = 0
    total_m = 0.0
    for row in q:
        results.append({"day": str(row.day), "trips": int(row.cnt), "distance_m": float(row.m_sum or 0.0)})
        total_trips += int(row.cnt)
        total_m += float(row.m_sum or 0.0)
    total_km = total_m/1000.0
    co2_saved_kg = total_km * EMISSION_FACTOR_KG_PER_KM
    return jsonify({"days": results, "total_trips": total_trips, "total_km": total_km, "co2_saved_kg": co2_saved_kg})

@app.route('/api/trips/list', methods=['GET'])
def api_trips_list():
    trips = Trip.query.order_by(Trip.start_time.desc()).limit(200).all()
    out = []
    for t in trips:
        out.append({
            "device_id": t.device_id,
            "start_time": t.start_time.isoformat(),
            "end_time": t.end_time.isoformat(),
            "distance_m": t.distance_m,
            "duration_s": t.duration_s,
            "start_lat": t.start_lat,
            "start_lon": t.start_lon,
            "end_lat": t.end_lat,
            "end_lon": t.end_lon
        })
    return jsonify(out)
