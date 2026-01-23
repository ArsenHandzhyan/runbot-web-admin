from flask import Flask, send_from_directory, request
import os

app = Flask(__name__)

@app.route('/test/<path:filename>')
def test_serve(filename):
    """Простой тестовый endpoint"""
    try:
        return send_from_directory('media', filename)
    except Exception as e:
        return f"Ошибка: {e}", 500

if __name__ == '__main__':
    app.run(port=5002, debug=True)
