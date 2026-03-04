import json


def print_success(message, data):
    print(json.dumps({"status": "success", "message": message, "data": data}))


def print_error(message):
    print(json.dumps({"status": "error", "message": message}))
