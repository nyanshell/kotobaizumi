import base64
import hashlib
import io
import json
import os
import re
import wave

import azure.cognitiveservices.speech as speechsdk
from openai import OpenAI

from app.database import SentenceManager
from app.settings import logger

client = OpenAI()

# Default to ./data directory relative to the project root
DEFAULT_DATA_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DATA_FOLDER = os.getenv("DATA_FOLDER", DEFAULT_DATA_FOLDER)
META_FILE = os.getenv("META_FILE", "meta.json")
JP_MODEL_1 = "ja-JP-AoiNeural"
JP_MODEL_2 = "ja-JP-MayuNeural"
JP_MODEL_3 = "ja-JP-DaichiNeural"
GPT_MODEL = "gpt-4"
PLAYBACK_ORDER = [JP_MODEL_1, JP_MODEL_2, JP_MODEL_3, "en", "zh"]


service_region = os.getenv("REGION", "japaneast")
speech_key = os.getenv("AZURE_SERVICE_TOKEN")

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
    subscription=speech_key, region=service_region
)
en_speech_config.speech_synthesis_voice_name = "en-GB-MaisieNeural"
en_speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=en_speech_config)
extract_grammar = re.compile("{{(.*?)}}")


def extract_grammar_pattern(text: str) -> tuple[str, str]:
    """Extract grammar pattern from text with {{}} markers.

    Returns:
        tuple: (clean_text_without_markers, grammar_pattern_or_none)
    """
    match = extract_grammar.search(text)
    if match:
        grammar_pattern = match.group(1).strip()
        # Reject empty patterns
        if not grammar_pattern:
            return text, None
        clean_text = extract_grammar.sub(lambda m: m.group(1), text)
        return clean_text, grammar_pattern
    return text, None

ZH_TRANSLATION_PROMPT = [
    {
        "role": "system",
        "content": "你是一个专业的译者，将用户输入的句子翻译成中文。要求符合原句的语境",
    },
]
EN_TRANSLATION_PROMPT = [
    {
        "role": "system",
        "content": """You're a professional translator who translates sentences entered by users
        into English. I require the translation to be in line with the original context.""",
    },
]
GRAMMAR_PROMPT = [
    {
        "role": "system",
        "content": """You're a language teacher who teaching user Japanese language,
        The user will give you the grammar point and example sentence.
        Explain the grammar in Jpanese. And add more examples. Add Hiragana readings for kanji words.
        Don't use Romaji.
        Use ** to emphasis the grammar point. Output with aesthetic markdown format.""",
    },
    {
        "role": "user",
        "content": "Show me the usage of 「そういう」 in the sentence そういう行動は許せません。",
    },
    {
        "role": "assistant",
        "content": """「そういう～」は日本語の表現で、「そのような〜」という意味を持ちます。これは、特定の種類、状態、或いは品質を持つ何かを表すために使用されます。

例文：

**そういう**態度（たいど）は許容（きょよう）できません。 (Such an attitude is not acceptable.)
あなたが話（はなし）している**そういう**問題（もんだい）について考（かんが）えてみます。 (I'll think about such a problem you're talking about.)
**そういう**意図（いと）は全（まった）くありませんでした。 (There was no such intention at all.)""",
    },
]
READING_PROMPT = [
    {
        "role": "system",
        "content": "add word reading with brackets for the Japanese sentence input",
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
            GRAMMAR_PROMPT,
        )
    return ""


def translate(text: str, context_messages: list) -> str:
    try:
        resp = client.chat.completions.create(
            model=GPT_MODEL,
            messages=context_messages + [{"role": "user", "content": text}],
        )
        last_resp = json.loads(resp.model_dump_json())["choices"][0]["message"][
            "content"
        ]
        logger.debug("OpenAI translation successful for text: %s", text[:50])
        return last_resp
    except Exception as e:
        logger.error("OpenAI API error during translation: %s", e)
        logger.error("Failed to translate text: %s", text[:100])
        raise RuntimeError(f"Translation failed: {e}") from e


def save_wav(file_name: str, data: bytes):
    out_wav_file = os.path.join(DATA_FOLDER, file_name)
    with open(out_wav_file, "wb") as fout:
        fout.write(data)


def save_sentence_data(
    user_id: int, text: str, en_text: str, zh_text: str, wav_data, explain, reading
):
    # Check for empty grammar markers
    if "{{" in text and "}}" in text:
        # Extract grammar pattern and get clean text
        clean_text, grammar_pattern = extract_grammar_pattern(text)
        if "{{" in text and grammar_pattern is None:
            return {"error": "Empty grammar markers {{}} are not allowed. Please provide a grammar pattern like {{pattern}}."}
    else:
        clean_text, grammar_pattern = extract_grammar_pattern(text)

    # Use clean text for hashing and audio generation
    text_hash = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
    for name, wav in wav_data:
        save_wav(f"{text_hash}.{name}.wav", wav)

    success = SentenceManager.save_sentence(
        user_id, text_hash, clean_text, en_text, zh_text, reading, explain, text, grammar_pattern
    )

    if success:
        return {
            "hash": text_hash,
            "ja_text": clean_text,
            "en_text": en_text,
            "cn_text": zh_text,
            "explain": explain,
            "reading": reading,
            "rendered_text": text,
            "grammar": grammar_pattern,
        }
    else:
        return {"error": "Failed to save sentence or sentence already exists"}


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
    try:
        if ssml:
            speech_synthesis_result = synthesizer.speak_ssml_async(text).get()
        else:
            speech_synthesis_result = synthesizer.speak_text_async(text).get()

        if (
            speech_synthesis_result.reason
            == speechsdk.ResultReason.SynthesizingAudioCompleted
        ):
            return speech_synthesis_result.audio_data
        elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = speech_synthesis_result.cancellation_details
            logger.error("Speech synthesis canceled: %s", cancellation_details.reason)
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    logger.error(
                        "Error details: %s", cancellation_details.error_details
                    )
                    logger.error(
                        "Did you set the speech resource key and region values?"
                    )
                raise RuntimeError(
                    f"Azure TTS Error: {cancellation_details.error_details}"
                )
            else:
                raise RuntimeError(f"Azure TTS Canceled: {cancellation_details.reason}")
        else:
            logger.error(
                "Unexpected Azure TTS result reason: %s", speech_synthesis_result.reason
            )
            raise RuntimeError(
                f"Unexpected TTS result: {speech_synthesis_result.reason}"
            )
    except Exception as e:
        logger.error("Azure TTS API error: %s", e)
        logger.error("Failed to synthesize text: %s", text)
        raise RuntimeError(f"TTS synthesis failed: {e}") from e


def generate_sentence_content(text):
    """Generate translations and explanations without audio content"""
    try:
        logger.info("Starting sentence content generation for: %s", text)
        explain = explain_grammar(text)
        clean_text = text.replace("{{", "").replace("}}", "")
        zh_text = translate(clean_text, ZH_TRANSLATION_PROMPT)
        en_text = translate(clean_text, EN_TRANSLATION_PROMPT)
        reading = translate(clean_text, READING_PROMPT)
        logger.info("All translations completed successfully")
    except Exception as e:
        logger.error("Failed to generate translations for text: %s", text)
        raise RuntimeError(f"Translation generation failed: {e}") from e

    return {
        "ja_text": clean_text,
        "en_text": en_text,
        "cn_text": zh_text,
        "explain": explain,
        "reading": reading,
    }


def generate_audio_content(sentence_data):
    """Generate TTS audio for sentence data"""
    clean_text = sentence_data["ja_text"]
    en_text = sentence_data["en_text"]
    zh_text = sentence_data["cn_text"]

    jp1_ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{JP_MODEL_1}' style='cheerful'>
        <prosody rate='-10%'>
            {clean_text}
        </prosody>
    </voice>
    </speak>
    """

    jp2_ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{JP_MODEL_2}'>
        <prosody rate='-10%'>
            {clean_text}
        </prosody>
    </voice>
    </speak>
    """

    jp3_ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='{JP_MODEL_3}'>
        {clean_text}
    </voice>
    </speak>
    """

    try:
        logger.info("Starting TTS synthesis for multiple voices")
        wav_data = [
            (JP_MODEL_1, tts(jp1_ssml_string, jp_speech_synthesizer, ssml=True)),
            (JP_MODEL_2, tts(jp2_ssml_string, jp_speech_synthesizer, ssml=True)),
            (JP_MODEL_3, tts(jp3_ssml_string, jp_speech_synthesizer, ssml=True)),
            ("en", tts(en_text, en_speech_synthesizer)),
            ("zh", tts(zh_text, zh_speech_synthesizer)),
        ]
        logger.info("All TTS synthesis completed successfully")
        return wav_data
    except Exception as e:
        logger.error("Failed to generate TTS audio for text: %s", clean_text)
        raise RuntimeError(f"TTS generation failed: {e}") from e


def concatenate_wavs(text_hash):
    data = []
    sample_rate = 0
    for model_name in PLAYBACK_ORDER:
        full_name = os.path.join(DATA_FOLDER, f"{text_hash}.{model_name}.wav")
        with wave.open(full_name, "rb") as w:
            sample_rate = w.getframerate()
            data.append([w.getparams(), w.readframes(w.getnframes())])
    return data, sample_rate


def encode_audio_string(hash_text: list):
    wav_binary = io.BytesIO(b"")
    with wave.open(wav_binary, "wb") as fout:
        for idx, hash_info in enumerate(hash_text):
            data, sample_rate = concatenate_wavs(hash_info["hash"])
            pause_frames = 2 * sample_rate
            pause_data = b"\x00" * pause_frames
            if idx == 0:
                fout.setparams(data[0][0])
            for i in range(len(data)):
                fout.writeframes(data[i][1])
                fout.writeframes(pause_data)

    audio_base64 = base64.b64encode(wav_binary.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{audio_base64}"


def encode_single_voice_audio(text_hash: str, voice_name: str):
    """Encode a single voice audio file as base64 data URL"""
    full_name = os.path.join(DATA_FOLDER, f"{text_hash}.{voice_name}.wav")
    try:
        with open(full_name, "rb") as f:
            audio_data = f.read()
        audio_base64 = base64.b64encode(audio_data).decode("ascii")
        return f"data:audio/wav;base64,{audio_base64}"
    except FileNotFoundError:
        logger.error("Audio file not found: %s", full_name)
        return None


def remove_sentence(user_id: int, hash_text: str):
    return SentenceManager.delete_sentence(user_id, hash_text)


def get_phrases(user_id: int, sort_type: str, return_count=1, offset=0):
    if sort_type == "review":
        return SentenceManager.get_sentences_for_review(user_id, return_count, offset)
    elif sort_type == "all":
        return SentenceManager.get_all_sentences(user_id, return_count, offset)
    else:
        return SentenceManager.get_random_sentences(user_id, return_count, offset)


def save_generated_sentence(user_id: int, sentence_data: dict):
    """Save a generated sentence with its audio files"""
    logger.debug("save_generated_sentence called with data: %s", sentence_data)

    # Get the original text with markers if available
    # This is the text the user originally entered with {{}} markers
    original_text_with_markers = sentence_data.get("original_text", sentence_data["ja_text"])
    logger.debug("Original text with markers: %s", original_text_with_markers)

    try:
        # Generate audio content using clean ja_text (without markers)
        wav_data = generate_audio_content(sentence_data)
    except Exception as e:
        logger.warning("TTS generation failed, saving sentence without audio: %s", e)
        wav_data = []

    # Pass the original text with markers to save_sentence_data
    # save_sentence_data will extract the grammar pattern and store both clean and rendered text
    return save_sentence_data(
        user_id,
        original_text_with_markers,  # Pass text with {{}} markers
        sentence_data["en_text"],
        sentence_data["cn_text"],
        wav_data,
        sentence_data["explain"],
        sentence_data["reading"],
    )
