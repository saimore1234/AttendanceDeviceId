#!/usr/bin/env python3
"""
Attendance Device Integration - Local Agent

A small, standalone Flask service that runs on a PC that IS on the same
network as the attendance device (ESSL/ZKTeco over TCP/IP), for when the
ERPNext server itself is remote and can't reach the device directly.

ERPNext talks to this agent over HTTP/internet; this agent talks to the
device over the local network using the real `pyzk` library (the same
one the main app's ZK Protocol adapter uses). Deliberately self-contained
- no dependency on Frappe/ERPNext being installed here, just Python +
pyzk + Flask.

Run:
	python agent.py --config config.json

Config: see config.example.json. Copy to config.json and set a token.

Endpoints:
	GET  /health
	POST /test-connection   {"device": {...}}
	POST /device-info       {"device": {...}}
	POST /users             {"device": {...}}
	POST /attendance-logs   {"device": {...}, "start_date": "...", "end_date": "..."}
	POST /clear-logs        {"device": {...}}
	POST /get-time          {"device": {...}}
	POST /set-time          {"device": {...}}
	POST /restart           {"device": {...}}

`device` is the same field shape as an Attendance Device document
(protocol_type, ip_address, port, connection_timeout, ...) - ERPNext
sends it inline with every request, so nothing needs to be duplicated
into this agent's own config.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request

try:
	from zk import ZK
	from zk.exception import ZKErrorConnection, ZKErrorResponse, ZKNetworkError
except ImportError:
	ZK = None
	ZKErrorConnection = ZKErrorResponse = ZKNetworkError = Exception


DEFAULT_CONFIG = {"host": "0.0.0.0", "port": 8585, "token": ""}


def load_config(path):
	if not path or not os.path.exists(path):
		print(f"[agent] WARNING: config file {path!r} not found, using defaults (no auth!).")
		return dict(DEFAULT_CONFIG)
	with open(path, "r", encoding="utf-8") as f:
		config = json.load(f)
	merged = dict(DEFAULT_CONFIG)
	merged.update(config)
	return merged


def _connect(device):
	if ZK is None:
		raise RuntimeError("pyzk is not installed. Run: pip install pyzk")
	ip = device.get("ip_address")
	if not ip:
		raise ValueError("No ip_address in device config")
	port = int(device.get("port") or 4370)
	timeout = int(device.get("connection_timeout") or 10)

	zk = ZK(ip, port=port, timeout=timeout, force_udp=False, ommit_ping=False)
	try:
		return zk.connect()
	except ZKNetworkError as e:
		raise ConnectionError(f"Could not reach {ip}:{port} - {e}")
	except ZKErrorConnection as e:
		raise PermissionError(f"Connection to {ip}:{port} failed - {e}")


def create_app(config):
	app = Flask(__name__)

	def require_auth(fn):
		@wraps(fn)
		def wrapper(*args, **kwargs):
			token = config.get("token")
			if token:
				header = request.headers.get("Authorization", "")
				if header != f"Bearer {token}":
					return jsonify({"success": False, "error": "Unauthorized"}), 401
			return fn(*args, **kwargs)
		return wrapper

	def with_connection(fn):
		@wraps(fn)
		def wrapper():
			payload = request.get_json(force=True, silent=True) or {}
			device = payload.get("device") or {}
			conn = None
			try:
				conn = _connect(device)
				return fn(conn, payload)
			except Exception as e:
				code = "SDK_MISSING" if ZK is None else "CONNECTION_FAILED"
				return jsonify({"success": False, "error": str(e), "error_code": code}), 200
			finally:
				if conn is not None:
					try:
						conn.disconnect()
					except Exception:
						pass
		return wrapper

	@app.route("/health", methods=["GET"])
	def health():
		return jsonify({"status": "ok", "time": time.time(), "pyzk_available": ZK is not None})

	@app.route("/test-connection", methods=["POST"])
	@require_auth
	@with_connection
	def test_connection(conn, payload):
		started = time.monotonic()
		info = {
			"firmware_version": _safe(conn.get_firmware_version),
			"serial_number": _safe(conn.get_serialnumber),
			"user_count": len(_safe(conn.get_users, default=[]) or []),
		}
		return jsonify({"success": True, "device_info": info, "elapsed_seconds": round(time.monotonic() - started, 3)})

	@app.route("/device-info", methods=["POST"])
	@require_auth
	@with_connection
	def device_info(conn, payload):
		return jsonify({
			"success": True,
			"firmware_version": _safe(conn.get_firmware_version),
			"serial_number": _safe(conn.get_serialnumber),
			"platform": _safe(conn.get_platform),
			"mac": _safe(conn.get_mac),
			"user_count": len(_safe(conn.get_users, default=[]) or []),
		})

	@app.route("/users", methods=["POST"])
	@require_auth
	@with_connection
	def users(conn, payload):
		result = []
		for u in conn.get_users():
			result.append({
				"device_user_id": str(u.user_id), "name": u.name,
				"card_number": str(u.card) if getattr(u, "card", None) else None,
				"status": str(getattr(u, "privilege", "")),
			})
		return jsonify({"success": True, "users": result})

	@app.route("/attendance-logs", methods=["POST"])
	@require_auth
	@with_connection
	def attendance_logs(conn, payload):
		records = conn.get_attendance()
		start_date = payload.get("start_date")
		end_date = payload.get("end_date")
		since = payload.get("since")

		punches = []
		for r in records or []:
			direction = "IN" if getattr(r, "punch", None) == 0 else ("OUT" if getattr(r, "punch", None) == 1 else "UNKNOWN")
			punches.append({
				"device_user_id": str(r.user_id),
				"punch_datetime": r.timestamp.isoformat(),
				"punch_type": str(getattr(r, "status", "")),
				"direction": direction,
			})

		if since:
			since_dt = datetime.fromisoformat(since)
			punches = [p for p in punches if datetime.fromisoformat(p["punch_datetime"]) > since_dt]
		elif start_date and end_date:
			start_dt, end_dt = datetime.fromisoformat(start_date), datetime.fromisoformat(end_date)
			punches = [p for p in punches if start_dt <= datetime.fromisoformat(p["punch_datetime"]) <= end_dt]

		return jsonify({"success": True, "punches": punches})

	@app.route("/clear-logs", methods=["POST"])
	@require_auth
	@with_connection
	def clear_logs(conn, payload):
		conn.clear_attendance()
		return jsonify({"success": True})

	@app.route("/get-time", methods=["POST"])
	@require_auth
	@with_connection
	def get_time(conn, payload):
		return jsonify({"success": True, "device_time": conn.get_time().isoformat()})

	@app.route("/set-time", methods=["POST"])
	@require_auth
	@with_connection
	def set_time(conn, payload):
		conn.set_time(datetime.now())
		return jsonify({"success": True})

	@app.route("/restart", methods=["POST"])
	@require_auth
	@with_connection
	def restart(conn, payload):
		conn.restart()
		return jsonify({"success": True})

	return app


def _safe(fn, default=None):
	try:
		return fn()
	except Exception:
		return default


def main():
	parser = argparse.ArgumentParser(description="Attendance Device Integration - Local Agent")
	parser.add_argument("--config", default=os.environ.get("AGENT_CONFIG", "config.json"))
	args = parser.parse_args()

	config = load_config(args.config)
	app = create_app(config)
	print(f"[agent] Listening on {config['host']}:{config['port']} (auth {'ON' if config.get('token') else 'OFF'}, "
		  f"pyzk {'available' if ZK else 'MISSING - run: pip install pyzk'})")
	app.run(host=config["host"], port=int(config["port"]))


if __name__ == "__main__":
	main()
