"""CellStock - minimal inventory lookup API (Flask + PostgreSQL + Redis cache)."""
import json
import os

import psycopg
import redis
from flask import Flask, jsonify, request, send_from_directory
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

app = Flask(__name__, static_folder="static", static_url_path="/static")

CACHE_TTL_SECONDS = 30


def db_conn():
    # Host is the Compose *service name* ("db"), resolved by Docker's internal DNS.
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        row_factory=dict_row,
        connect_timeout=3,
    )


def cache_client():
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "cache"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=True,
    )


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health():
    status = {"status": "ok", "database": "up", "cache": "up"}
    code = 200
    try:
        with db_conn() as conn:
            conn.execute("SELECT 1")
    except Exception:
        status["status"], status["database"], code = "degraded", "down", 503
    try:
        cache_client().ping()
    except Exception:
        # Cache is optional: the app still works without it.
        status["cache"] = "down"
    return jsonify(status), code


@app.get("/api/products")
def list_products():
    q = (request.args.get("q") or "").strip()
    key = f"search:{q.lower()}"

    r = None
    try:
        r = cache_client()
        cached = r.get(key)
        if cached is not None:
            items = json.loads(cached)
            return jsonify({"count": len(items), "cache": "hit", "items": items}), 200
    except redis.RedisError:
        r = None

    like = f"%{q}%"
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, category, compatible_models, price_idr, quantity, location
            FROM products
            WHERE %s = '' OR name ILIKE %s OR category ILIKE %s OR compatible_models ILIKE %s
            ORDER BY name
            LIMIT 50
            """,
            (q, like, like, like),
        ).fetchall()

    items = [dict(row, in_stock=row["quantity"] > 0) for row in rows]
    if r is not None:
        try:
            r.setex(key, CACHE_TTL_SECONDS, json.dumps(items))
        except redis.RedisError:
            pass
    return jsonify({"count": len(items), "cache": "miss", "items": items}), 200


@app.post("/api/products")
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Body must be a JSON object"}), 400

    name = str(data.get("name", "")).strip()
    location = str(data.get("location", "")).strip()
    category = str(data.get("category", "")).strip() or None
    models = str(data.get("compatible_models", "")).strip() or None
    price, qty = data.get("price_idr"), data.get("quantity")

    errors = []
    if not name:
        errors.append("name is required")
    if not location:
        errors.append("location is required")
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        errors.append("price_idr must be an integer >= 0")
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
        errors.append("quantity must be an integer >= 0")
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    try:
        with db_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO products (name, category, compatible_models, price_idr, quantity, location)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, name, category, compatible_models, price_idr, quantity, location
                """,
                (name, category, models, price, qty, location),
            ).fetchone()
    except UniqueViolation:
        return jsonify({"error": f"Product '{name}' already exists"}), 409

    # Invalidate cached searches so new data shows up immediately.
    try:
        r = cache_client()
        for k in r.scan_iter("search:*"):
            r.delete(k)
    except redis.RedisError:
        pass

    resp = jsonify(row)
    resp.status_code = 201
    resp.headers["Location"] = f"/api/products/{row['id']}"
    return resp
