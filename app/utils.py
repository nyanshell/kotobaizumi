import base64
import io
import os
import json
import hashlib
import wave
import re
import time
import sqlite3
from sqlite3 import IntegrityError

from openai import OpenAI
import azure.cognitiveservices.speech as speechsdk


client = OpenAI()

DATA_FOLDER = os.getenv('DATA_FOLDER', '/data')
META_FILE = os.getenv('META_FILE', 'meta.json')
JP_MODEL_1 = 'ja-JP-AoiNeural'
JP_MODEL_2 = 'ja-JP-MayuNeural'
JP_MODEL_3 = 'ja-JP-DaichiNeural'
GPT_MODEL = 'gpt-4'
PLAYBACK_ORDER = [
    JP_MODEL_1,
    JP_MODEL_2,
    JP_MODEL_3,
    'en',
    'zh'
]

conn = sqlite3.connect(os.path.join(DATA_FOLDER, "meta.db"))
META_TABLE = 'sentences'
db_cursor = conn.cursor()
db_cursor.execute(f'''CREATE TABLE IF NOT EXISTS {META_TABLE} (
    hash TEXT PRIMARY KEY,
    count INTEGER,
    timestamp INTEGER
)''')

service_region = os.getenv('REGION', 'japaneast')
speech_key = os.getenv('AZURE_SERVICE_TOKEN')

jp_speech_config = speechsdk.SpeechConfig(
    subscription=speech_key,
    region=service_region,
)
audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)

jp_speech_config.speech_synthesis_voice_name = JP_MODEL_1
jp_speech_synthesizer = speechsdk.SpeechSynthesizer(
    speech_config=jp_speech_config,
    audio_config=audio_config,
)

zh_speech_config = speechsdk.SpeechConfig(
    subscription=speech_key,
    region=service_region,
)
zh_speech_config.speech_synthesis_voice_name = "zh-CN-XiaoyiNeural"
zh_speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=zh_speech_config)


en_speech_config = speechsdk.SpeechConfig(
    subscription=speech_key,
    region=service_region
    )
en_speech_config.speech_synthesis_voice_name = "en-GB-MaisieNeural"
en_speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=en_speech_config)
extract_grammar = re.compile("{{(.+?)}}")

ZH_TRANSLATION_PROMPT = [
    {"role": "system", "content": "你是一个专业的译者，将用户输入的句子翻译成中文。要求符合原句的语境"},
]
EN_TRANSLATION_PROMPT = [
    {
        "role": "system",
        "content": '''You're a professional translator who translates sentences entered by users
        into English. I require the translation to be in line with the original context.'''
    },
]
GRAMMAR_PROMPT = [
    {
        "role": "system",
        "content": '''You're a language teacher who teaching user Japanese language,
        The user will give you the grammar point and example sentence.
        Explain the grammar in Jpanese. And add more examples. Add Hiragana readings for kanji words.
        Don't use Romaji.
        Use ** to emphasis the grammar point. Output with aesthetic markdown format.''',
    },
    {
        "role": "user",
        "content": "Show me the usage of 「そういう」 in the sentence そういう行動は許せません。",
    },
    {
        "role": "assistant",
        "content": '''「そういう～」は日本語の表現で、「そのような〜」という意味を持ちます。これは、特定の種類、状態、或いは品質を持つ何かを表すために使用されます。

例文：

**そういう**態度（たいど）は許容（きょよう）できません。 (Such an attitude is not acceptable.)
あなたが話（はなし）している**そういう**問題（もんだい）について考（かんが）えてみます。 (I'll think about such a problem you're talking about.)
**そういう**意図（いと）は全（まった）くありませんでした。 (There was no such intention at all.)''',
    }
]
READING_PROMPT = [
    {
        "role": "system",
        "content": 'add word reading with brackets for the Japanese sentence input',
    },
    {
        "role": "user",
        "content": "新学年を迎えるにあたって、私たちは新しい計画を立てました。",
    },
    {
        "role": "assistant",
        "content": "新学年（しんがくねん）を迎（むか）えるにあたって、私（わたし）たちは新（あたら）しい計画（けいかく）を立（た）てました。",
    },
]


def explain_grammar(text: str) -> str:
    grammar_pattern = extract_grammar.search(text)
    if grammar_pattern is not None:
        return translate(
            f"Show me the usage of 「{grammar_pattern.group(1)}」 in the sentence {text}",
            GRAMMAR_PROMPT
        )
    return ''


def translate(text: str, context_messages: list) -> str:
    resp = client.chat.completions.create(
        model=GPT_MODEL,
        messages=context_messages + [{"role": "user", "content": text}],
    )
    last_resp = json.loads(resp.model_dump_json())['choices'][0]['message']['content']
    return last_resp


def save_wav(file_name: str, data: bytes):
    out_wav_file = os.path.join(DATA_FOLDER, file_name)
    with open(out_wav_file, 'wb') as fout:
        fout.write(data)


def save(text: str, en_text: str, zh_text: str, wav_data, explain, reading):
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    for name, wav in wav_data:
        save_wav(f'{text_hash}.{name}.wav', wav)
    meta_info = {
        'hash': text_hash,
        'ja_text': text,
        'en_text': en_text,
        'cn_text': zh_text,
        'explain': explain,
        'reading': reading,
    }

    # update meta db
    try:
        with sqlite3.connect(os.path.join(DATA_FOLDER, "meta.db")) as conn:
            db_cursor = conn.cursor()
            db_cursor.execute(
                f"INSERT INTO {META_TABLE} (hash, count, timestamp) VALUES (?, ?, ?)",
                (text_hash, 0, int(time.time()))
            )
            conn.commit()
    except IntegrityError:
        print('sentence duplicated')
        return {"error": "sentence duplicated"}

    with open(os.path.join(DATA_FOLDER, META_FILE), 'a') as fout:
        fout.write(json.dumps(meta_info, ensure_ascii=False) + '\n')

    print(meta_info)
    return meta_info


def make_ssml(text, model_name):
    ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{model_name}' style='cheerful'>
        <prosody rate='-10%'>
            {text}
        </prosody>
    </voice>
    </speak>
    """
    return ssml_string


def tts(text: str, synthesizer, ssml=False):
    if ssml:
        speech_synthesis_result = synthesizer.speak_ssml_async(text).get()
    else:
        speech_synthesis_result = synthesizer.speak_text_async(text).get()
    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return speech_synthesis_result.audio_data
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                print("Error details: {}".format(cancellation_details.error_details))
                print("Did you set the speech resource key and region values?")
            raise RuntimeError(cancellation_details.error_details)


def generate(text):

    explain = explain_grammar(text)
    text = text.replace('{{', '').replace('}}', '')
    zh_text = translate(text, ZH_TRANSLATION_PROMPT)
    en_text = translate(text, EN_TRANSLATION_PROMPT)
    reading = translate(text, READING_PROMPT)

    jp1_ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{JP_MODEL_1}' style='cheerful'>
        <prosody rate='-10%'>
            {text}
        </prosody>
    </voice>
    </speak>
    """

    jp2_ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{JP_MODEL_2}'>
        <prosody rate='-10%'>
            {text}
        </prosody>
    </voice>
    </speak>
    """

    jp3_ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{JP_MODEL_3}'>
        {text}
    </voice>
    </speak>
    """

    wav_data = [
        (JP_MODEL_1, tts(jp1_ssml_string, jp_speech_synthesizer, ssml=True)),
        (JP_MODEL_2, tts(jp2_ssml_string, jp_speech_synthesizer, ssml=True)),
        (JP_MODEL_3, tts(jp3_ssml_string, jp_speech_synthesizer, ssml=True)),
        ('en', tts(en_text, en_speech_synthesizer)),
        ('zh', tts(zh_text, zh_speech_synthesizer)),
    ]
    meta = save(text, en_text, zh_text, wav_data, explain, reading)
    return meta


def concatenate_wavs(text_hash):
    data = []
    sample_rate = 0
    for model_name in PLAYBACK_ORDER:
        full_name = os.path.join(DATA_FOLDER, f'{text_hash}.{model_name}.wav')
        with wave.open(full_name, 'rb') as w:
            sample_rate = w.getframerate()
            data.append([w.getparams(), w.readframes(w.getnframes())])
    return data, sample_rate


def encode_audio_string(hash_text: list):

    wav_binary = io.BytesIO(b'')
    with wave.open(wav_binary, 'wb') as fout:
        for idx, hash_info in enumerate(hash_text):
            data, sample_rate = concatenate_wavs(hash_info['hash'])
            pause_frames = 2 * sample_rate
            pause_data = b"\x00" * pause_frames
            if idx == 0:
                fout.setparams(data[0][0])
            for i in range(len(data)):
                fout.writeframes(data[i][1])
                fout.writeframes(pause_data)

    audio_base64 = base64.b64encode(wav_binary.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{audio_base64}"


def remove_sentence(hash_text):
    with sqlite3.connect(os.path.join(DATA_FOLDER, "meta.db")) as conn:
        db_cursor = conn.cursor()
        db_cursor.execute(f"DELETE FROM {META_TABLE} WHERE hash = ?", (hash_text, ))
        conn.commit()


def get_phrases(sort_type: str, return_count=1):
    with sqlite3.connect(os.path.join(DATA_FOLDER, "meta.db")) as conn:
        db_cursor = conn.cursor()
        if sort_type == 'freq':
            phrase_info = db_cursor.execute(
                f"SELECT * FROM {META_TABLE} ORDER BY count LIMIT {return_count};"
            ).fetchall()
        elif sort_type == 'time':
            phrase_info = db_cursor.execute(
                f"SELECT * FROM {META_TABLE} ORDER BY timestamp LIMIT {return_count};"
            ).fetchall()
        else:
            phrase_info = db_cursor.execute(
                f"SELECT * FROM {META_TABLE} ORDER BY RANDOM() LIMIT {return_count};"
            ).fetchall()
        text_hash = set(hash_text for hash_text, _, _ in phrase_info)
        for hash_ in text_hash:
            db_cursor.execute(
                f"UPDATE {META_TABLE} SET count = count + 1 WHERE hash = ?",
                (hash_, )
            )
        conn.commit()
    phrase_meta = []
    with open(os.path.join(DATA_FOLDER, META_FILE), 'r') as fin:
        for row in fin:
            meta = json.loads(row)
            if meta['hash'] in text_hash:
                phrase_meta.append(meta)
                text_hash.remove(meta['hash'])
    return phrase_meta


if __name__ == '__main__':
    # generate('旅行に出発するにあたって、必要なものすべてをパックしました。')
    # generate('部屋はゴミだらけだった。')
    '''
    data, sample_rate = concatenate_wavs('d41e9a0491ae35e79c6d35b00a56df3d')

    import io

    pause_frames = 2 * sample_rate
    pause_data = b"\x00" * pause_frames
    wav_binary = io.BytesIO(b'')
    # with wav_binary as fout:
    with wave.open(wav_binary, "wb") as fout:
        fout.setparams(data[0][0])
        for i in range(len(data)):
            fout.writeframes(data[i][1])
            fout.writeframes(pause_data)
    bs = wav_binary.getvalue()
    print(len(bs))
    with open('/data/test.wav', 'wb') as fout:
        fout.write(bs)
    '''
    # print(explain_grammar('～たまらない'))
    # generate test
    generate('新学年を迎える{{にあたって}}、私たちは新しい計画を立てました。')
    generate('このコーヒーはとても{{濃い}}。')
