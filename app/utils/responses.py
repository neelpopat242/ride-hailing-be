from flask import jsonify


def success_response(data, status_code=200):
    return jsonify({"data": data}), status_code


def error_response(code, message, status_code):
    return jsonify({"error": {"code": code, "message": message}}), status_code
