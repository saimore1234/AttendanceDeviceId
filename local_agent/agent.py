
#!/usr/bin/env python3
"""Attendance Device Integration - Local Agent."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request

try:
    from zk import ZK
    from zk.exception import ZKErrorConnection, ZKErrorResponse, ZKNetworkError
except ImportError:
    ZK = None
    ZKErrorConnection = ZKErrorResponse = ZKNetworkError = Exception


DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8585,
    "token": ""
}

MANTRA_RECEIVER = "http://127.0.0.1:8586"


def load_config(path):
    if not path or not os.path.exists(path):
        print(f"[agent] WARNING: config file {path!r} not found.")
        return dict(DEFAULT_CONFIG)

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def _is_mantra(device):
    return "mantra" in str(
        device.get("protocol_type") or ""
    ).lower()


def _mantra_get(path):
    url = MANTRA_RECEIVER + path
    req = urllib.request.Request(url, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))

    except Exception as e:
        raise ConnectionError(
            f"Mantra SDK receiver unavailable: {e}"
        )

    if not data.get("success", path == "/health"):
        raise RuntimeError(
            data.get("error", "Mantra SDK operation failed")
        )

    return data


def _mantra_attendance(device):
    ip = device.get("ip_address")
    port = int(device.get("port") or 5005)

    # Correct ERPNext Attendance Device fieldname:
    # Device ID (Protocol) = tcp_device_id
    device_id = device.get("tcp_device_id")

    if device_id is None or str(device_id).strip() == "":
        raise ValueError(
            "Device ID (Protocol) is missing from Attendance Device"
        )

    query = urllib.parse.urlencode({
        "id": int(device_id),
        "ip": ip,
        "port": port
    })

    result = _mantra_get("/attendance-logs?" + query)

    punches = result.get("punches", [])

    payload = request.get_json(silent=True) or {}

    since = payload.get("since")
    from_date = payload.get("start_date")
    to_date = payload.get("end_date")

    if since:
        since_dt = datetime.fromisoformat(since)

        punches = [
            p for p in punches
            if datetime.fromisoformat(
                p["punch_datetime"]
            ) > since_dt
        ]

    elif from_date and to_date:
        start_dt = datetime.fromisoformat(from_date)
        end_dt = datetime.fromisoformat(to_date)

        punches = [
            p for p in punches
            if start_dt <= datetime.fromisoformat(
                p["punch_datetime"]
            ) <= end_dt
        ]

    return {
        "success": True,
        "count": len(punches),
        "punches": punches
    }


def _connect(device):
    if ZK is None:
        raise RuntimeError(
            "pyzk is not installed. Run: pip install pyzk"
        )

    ip = device.get("ip_address")

    if not ip:
        raise ValueError("No ip_address in device config")

    port = int(device.get("port") or 4370)
    timeout = int(device.get("connection_timeout") or 10)

    password = (
        int(device.get("password"))
        if str(device.get("password") or "").isdigit()
        else 0
    )

    zk = ZK(
        ip,
        port=port,
        timeout=timeout,
        password=password,
        force_udp=False,
        ommit_ping=False
    )

    try:
        try:
            return zk.connect()

        except ZKNetworkError:
            zk = ZK(
                ip,
                port=port,
                timeout=timeout,
                password=password,
                force_udp=True,
                ommit_ping=True
            )

            return zk.connect()

    except ZKNetworkError as e:
        raise ConnectionError(
            f"Could not reach {ip}:{port} - {e}"
        )

    except ZKErrorConnection as e:
        raise PermissionError(
            f"Connection to {ip}:{port} failed - {e}"
        )


def create_app(config):
    app = Flask(__name__)

    def require_auth(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = config.get("token")

            if token:
                header = request.headers.get(
                    "Authorization", ""
                )

                if header != f"Bearer {token}":
                    return jsonify({
                        "success": False,
                        "error": "Unauthorized"
                    }), 401

            return fn(*args, **kwargs)

        return wrapper

    def with_connection(fn):
        @wraps(fn)
        def wrapper():
            payload = request.get_json(
                force=True,
                silent=True
            ) or {}

            device = payload.get("device") or {}
            conn = None

            try:
                if _is_mantra(device):
                    return fn(None, payload)

                conn = _connect(device)

                return fn(conn, payload)

            except Exception as e:
                code = (
                    "SDK_MISSING"
                    if ZK is None and not _is_mantra(device)
                    else "CONNECTION_FAILED"
                )

                return jsonify({
                    "success": False,
                    "error": str(e),
                    "error_code": code
                }), 200

            finally:
                if conn is not None:
                    try:
                        conn.disconnect()
                    except Exception:
                        pass

        return wrapper

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "time": time.time(),
            "pyzk_available": ZK is not None
        })

    @app.route("/test-connection", methods=["POST"])
    @require_auth
    @with_connection
    def test_connection(conn, payload):
        started = time.monotonic()

        if conn is None:
            # Checks whether the Mantra receiver is running.
            # Actual device connectivity is checked during log retrieval.
            result = _mantra_get("/health")

            return jsonify({
                "success": True,
                "adapter": "Mantra BioTime SDK",
                "device_info": {
                    "platform": "Mantra BioTime SDK",
                    "receiver": result.get("service")
                },
                "elapsed_seconds": round(
                    time.monotonic() - started, 3
                )
            })

        info = {
            "firmware_version": _safe(
                conn.get_firmware_version
            ),
            "serial_number": _safe(
                conn.get_serialnumber
            ),
            "user_count": len(
                _safe(conn.get_users, default=[]) or []
            )
        }

        return jsonify({
            "success": True,
            "device_info": info,
            "elapsed_seconds": round(
                time.monotonic() - started, 3
            )
        })

    @app.route("/device-info", methods=["POST"])
    @require_auth
    @with_connection
    def device_info(conn, payload):
        if conn is None:
            return jsonify({
                "success": True,
                "platform": "Mantra BioTime SDK",
                "serial_number": None,
                "user_count": None
            })

        return jsonify({
            "success": True,
            "firmware_version": _safe(
                conn.get_firmware_version
            ),
            "serial_number": _safe(
                conn.get_serialnumber
            ),
            "platform": _safe(conn.get_platform),
            "mac": _safe(conn.get_mac),
            "user_count": len(
                _safe(conn.get_users, default=[]) or []
            )
        })

    @app.route("/users", methods=["POST"])
    @require_auth
    @with_connection
    def users(conn, payload):
        if conn is None:
            return jsonify({
                "success": True,
                "users": [],
                "message": (
                    "Mantra user listing is not implemented yet"
                )
            })

        result = []

        for u in conn.get_users():
            result.append({
                "device_user_id": str(u.user_id),
                "name": u.name,
                "card_number": (
                    str(u.card)
                    if getattr(u, "card", None)
                    else None
                ),
                "status": str(
                    getattr(u, "privilege", "")
                )
            })

        return jsonify({
            "success": True,
            "users": result
        })

    @app.route("/attendance-logs", methods=["POST"])
    @require_auth
    @with_connection
    def attendance_logs(conn, payload):
        if conn is None:
            return jsonify(
                _mantra_attendance(
                    payload.get("device") or {}
                )
            )

        records = conn.get_attendance()

        start_date = payload.get("start_date")
        end_date = payload.get("end_date")
        since = payload.get("since")

        punches = []

        for r in records or []:
            direction = (
                "IN" if getattr(r, "punch", None) == 0
                else "OUT" if getattr(r, "punch", None) == 1
                else "UNKNOWN"
            )

            punches.append({
                "device_user_id": str(r.user_id),
                "punch_datetime": r.timestamp.isoformat(),
                "punch_type": str(
                    getattr(r, "status", "")
                ),
                "direction": direction
            })

        if since:
            since_dt = datetime.fromisoformat(since)

            punches = [
                p for p in punches
                if datetime.fromisoformat(
                    p["punch_datetime"]
                ) > since_dt
            ]

        elif start_date and end_date:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)

            punches = [
                p for p in punches
                if start_dt <= datetime.fromisoformat(
                    p["punch_datetime"]
                ) <= end_dt
            ]

        return jsonify({
            "success": True,
            "punches": punches
        })

    @app.route("/clear-logs", methods=["POST"])
    @require_auth
    @with_connection
    def clear_logs(conn, payload):
        if conn is None:
            return jsonify({
                "success": False,
                "error": (
                    "Clearing Mantra device logs is disabled"
                )
            }), 400

        conn.clear_attendance()

        return jsonify({"success": True})

    @app.route("/get-time", methods=["POST"])
    @require_auth
    @with_connection
    def get_time(conn, payload):
        if conn is None:
            return jsonify({
                "success": False,
                "error": (
                    "Mantra time retrieval is not implemented"
                )
            }), 400

        return jsonify({
            "success": True,
            "device_time": conn.get_time().isoformat()
        })

    @app.route("/set-time", methods=["POST"])
    @require_auth
    @with_connection
    def set_time(conn, payload):
        if conn is None:
            return jsonify({
                "success": False,
                "error": (
                    "Mantra time setting is not implemented"
                )
            }), 400

        target = payload.get("datetime")

        conn.set_time(
            datetime.fromisoformat(target)
            if target
            else datetime.now()
        )

        return jsonify({"success": True})

    @app.route("/restart", methods=["POST"])
    @require_auth
    @with_connection
    def restart(conn, payload):
        if conn is None:
            return jsonify({
                "success": False,
                "error": (
                    "Mantra restart is not implemented"
                )
            }), 400

        conn.restart()

        return jsonify({"success": True})

    return app


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Attendance Device Integration - Local Agent"
        )
    )

    parser.add_argument(
        "--config",
        default=os.environ.get(
            "AGENT_CONFIG",
            "config.json"
        )
    )

    args = parser.parse_args()

    config = load_config(args.config)
    app = create_app(config)

    print(
        f"[agent] Listening on {config['host']}:{config['port']} "
        f"(auth {'ON' if config.get('token') else 'OFF'}, "
        f"pyzk {'available' if ZK else 'MISSING'})"
    )

    app.run(
        host=config["host"],
        port=int(config["port"])
    )


if __name__ == "__main__":
    main()
