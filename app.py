import json
import os
from flask import Flask, jsonify, render_template, request
import pdf_utils

app = Flask(__name__)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")

with open(CONFIG_PATH) as f:
    config = json.load(f)

PDF_DIRECTORIES = config["pdf_directories"]
DIR_MAP = {d["key"]: d["path"] for d in PDF_DIRECTORIES}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/api/dirs")
def list_dirs():
    return jsonify({
        "directories": [{
            "key": d["key"],
            "label": d["label"],
            "dirname": os.path.basename(os.path.abspath(d["path"]))
        } for d in PDF_DIRECTORIES]
    })


@app.route("/api/browse/<dir_key>")
@app.route("/api/browse/<dir_key>/<path:subpath>")
def browse_dir(dir_key, subpath=""):
    if dir_key not in DIR_MAP:
        return jsonify({"error": "Directory not found"}), 404
    target = os.path.normpath(os.path.join(DIR_MAP[dir_key], subpath))
    allowed = os.path.normpath(DIR_MAP[dir_key])
    if not target.startswith(allowed):
        return jsonify({"error": "Directory not found"}), 404
    return jsonify(pdf_utils.browse_directory(DIR_MAP[dir_key], subpath))


@app.route("/api/pdfs")
def list_pdfs():
    all_pdfs = []
    for d in PDF_DIRECTORIES:
        if not os.path.isdir(d["path"]):
            continue
        try:
            pdfs = pdf_utils.list_pdfs(d["path"])
        except Exception:
            pdfs = []
        for p in pdfs:
            p["dir_key"] = d["key"]
            p["dir_label"] = d["label"]
        all_pdfs.extend(pdfs)
    return jsonify({"pdfs": all_pdfs})


def _resolve(compound):
    """Split 'dir_key/filename.pdf' into (dir_key, filename)."""
    parts = compound.split("/", 1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def _resolve_pdf(compound):
    """Resolve compound path, return (filepath, error_tuple).

    Returns (filepath, None) on success, or (None, (response, status_code)) on error.
    """
    dir_key, filename = _resolve(compound)
    if dir_key not in DIR_MAP:
        return None, (jsonify({"error": "PDF not found"}), 404)
    filepath = os.path.normpath(os.path.join(DIR_MAP[dir_key], filename))
    allowed = os.path.normpath(DIR_MAP[dir_key])
    if not filepath.startswith(allowed) or not os.path.isfile(filepath) or not filename.lower().endswith(".pdf"):
        return None, (jsonify({"error": "PDF not found"}), 404)
    return filepath, None


@app.route("/api/pdf/<path:compound>/info")
def pdf_info(compound):
    filepath, err = _resolve_pdf(compound)
    if err:
        return err
    try:
        info = pdf_utils.get_pdf_info(filepath)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pdf/<path:compound>/toc")
def pdf_toc(compound):
    filepath, err = _resolve_pdf(compound)
    if err:
        return err
    try:
        toc = pdf_utils.get_pdf_toc(filepath)
        return jsonify({"toc": toc})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pdf/<path:compound>/thumbnails")
def pdf_thumbnails(compound):
    filepath, err = _resolve_pdf(compound)
    if err:
        return err
    try:
        start = int(request.args.get("start", 1))
        end = request.args.get("end", None)
        if end is not None:
            end = int(end)
        result = pdf_utils.get_thumbnails(filepath, start, end)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pdf/<path:compound>/page/<int:page_num>")
def get_page(compound, page_num):
    filepath, err = _resolve_pdf(compound)
    if err:
        return err
    try:
        result = pdf_utils.extract_page_html(filepath, page_num)
        result["filename"] = compound
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
