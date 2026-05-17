import os
from flask import Flask, jsonify, render_template, request
import pdf_utils

app = Flask(__name__)
PDF_DIR = os.environ.get("PDF_DIR", "/data/apps/sandbox/pdf_books")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/api/pdfs")
def list_pdfs():
    subdir = request.args.get("dir", "")
    result = pdf_utils.list_pdfs_with_dirs(PDF_DIR, subdir)
    return jsonify(result)


@app.route("/api/pdf/<path:filename>/info")
def pdf_info(filename):
    filepath = os.path.join(PDF_DIR, filename)
    if not os.path.isfile(filepath) or not filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF not found"}), 404
    try:
        info = pdf_utils.get_pdf_info(filepath)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pdf/<path:filename>/page/<int:page_num>")
def get_page(filename, page_num):
    filepath = os.path.join(PDF_DIR, filename)
    if not os.path.isfile(filepath) or not filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF not found"}), 404
    try:
        result = pdf_utils.extract_page_html(filepath, page_num)
        result["filename"] = filename
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
