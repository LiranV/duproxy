#!/usr/bin/env python3
from flask import Flask
import json
import sys

app = Flask(__name__)


@app.route("/register", methods=["POST"])
def register():
    return json.dumps({
        "message": "Registered successfully",
        "status": "Success"
    }), 201


@app.route("/changePassword", methods=["POST"])
def changePassword():
    return json.dumps({
        "message": "Password changed successfully",
        "status": "Success"
    }), 201


@app.route("/login", methods=["GET"])
def login():
    return "login", 200


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Listening port must be provided.")
    app.run(debug=True, port=int(sys.argv[1]))
