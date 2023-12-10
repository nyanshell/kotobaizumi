import base64
import json
import random
import os
import io
import wave

from flask import Flask, render_template, request, Response

from utils import generate, concatenate_wavs, DATA_FOLDER, META_FILE


app = Flask(__name__)

with open(os.path.join(DATA_FOLDER, META_FILE), 'r') as fin:
    meta_info = [json.loads(line) for line in fin.readlines()]


@app.route("/record", methods=["POST"])
def insert_new():
    data = json.loads(request.data)
    text = data.get("text")
    meta = generate(text)
    meta_info.append(meta)
    print(meta)
    resp = Response()
    resp.set_data(json.dumps(meta, ensure_ascii=False))
    resp.headers.set("Content-Type", "application/json; charset=utf-8")
    return resp


@app.route("/random")
def get_rand():

    rand_phrase = meta_info[random.randint(0, len(meta_info) - 1)]
    data, sample_rate = concatenate_wavs(rand_phrase['hash'])

    pause_frames = 2 * sample_rate
    pause_data = b"\x00" * pause_frames
    wav_binary = io.BytesIO(b'')
    with wave.open(wav_binary, 'wb') as fout:
        fout.setparams(data[0][0])
        for i in range(len(data)):
            fout.writeframes(data[i][1])
            fout.writeframes(pause_data)
    audio_base64 = base64.b64encode(wav_binary.getvalue()).decode("ascii")
    audio_string = f"data:audio/wav;base64,{audio_base64}"

    return render_template("index.html", audio_string=audio_string, data=rand_phrase)
