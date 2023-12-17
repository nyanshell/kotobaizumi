import json

from flask import Flask, render_template, request, Response

from utils import (
    generate,
    encode_audio_string,
    remove_sentence,
    get_phrases,
)


app = Flask(__name__)


@app.route("/delete/<string:hash_text>", methods=["DELETE"])
def remove(hash_text):
    remove_sentence(hash_text)
    return json.dumps({'result': 'done!'})


@app.route("/record", methods=["POST"])
def insert_new():
    data = json.loads(request.data)
    text = data.get("text")
    meta = generate(text)
    resp = Response()
    resp.set_data(json.dumps(meta, ensure_ascii=False))
    resp.headers.set("Content-Type", "application/json; charset=utf-8")
    return resp


@app.route("/")
def play():
    sort_type = request.args.get('sort', '')
    try:
        return_count = request.args.get('count', 1)
    except ValueError:
        return_count = 1
    phrase_meta = get_phrases(sort_type, return_count=return_count)
    audio_string = encode_audio_string(phrase_meta)
    return render_template("index.html", audio_string=audio_string, data=phrase_meta)
