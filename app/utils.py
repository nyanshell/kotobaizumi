import base64
import hashlib
import io
import os
import re
import wave

from .database import SentenceManager
from .settings import logger

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

# Initialize LLM client based on provider
if LLM_PROVIDER == "openai":
    from openai import OpenAI

    _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
    logger.debug("Using OpenAI as LLM provider")

elif LLM_PROVIDER == "gemini":
    from google import genai
    from google.genai import types

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY environment variable is required when using Gemini"
        )
    _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    logger.debug("Using Gemini as LLM provider")
else:
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}. Use 'openai' or 'gemini'"
    )

# TTS Configuration
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "gemini").lower()

# Default to ./data directory relative to the project root
DEFAULT_DATA_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DATA_FOLDER = os.getenv("DATA_FOLDER", DEFAULT_DATA_FOLDER)
META_FILE = os.getenv("META_FILE", "meta.json")

# Initialize TTS clients based on provider
_gemini_tts_client = None  # Lazy initialization
PLAYBACK_ORDER = []

if "gemini" in TTS_PROVIDER:
    TTS_MODEL = os.getenv("TTS_MODEL", "gemini-2.5-pro-tts")
    TTS_VOICE_NAME = os.getenv("TTS_VOICE_NAME", "Leda")
    GEMINI_JP_VOICE_1 = "Leda"
    GEMINI_JP_VOICE_2 = "Zephyr"
    PLAYBACK_ORDER += [GEMINI_JP_VOICE_1, GEMINI_JP_VOICE_2]
    logger.debug(
        "Using Google Gemini TTS as TTS provider with voices: %s (normal), Zephyr (slow)",
        TTS_VOICE_NAME,
    )

if "azure" in TTS_PROVIDER:
    import azure.cognitiveservices.speech as speechsdk

    service_region = os.getenv("REGION", "japaneast")
    speech_key = os.getenv("AZURE_SERVICE_TOKEN")
    if not speech_key:
        raise ValueError(
            "AZURE_SERVICE_TOKEN environment variable is required when using Azure TTS"
        )

    JP_MODEL_1 = "ja-JP-AoiNeural"
    JP_MODEL_2 = "ja-JP-Nanami:DragonHDLatestNeural"
    JP_MODEL_3 = "ja-JP-Masaru:DragonHDLatestNeural"
    JP_MODEL_2_DEPRECATED = "ja-JP-MayuNeural"
    JP_MODEL_3_DEPRECATED = "ja-JP-DaichiNeural"
    PLAYBACK_ORDER += [
        JP_MODEL_1,
        JP_MODEL_2,
        JP_MODEL_3,
        JP_MODEL_2_DEPRECATED,
        JP_MODEL_3_DEPRECATED,
    ]

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
    logger.debug("Using Azure as TTS provider")

else:
    raise ValueError(
        f"Unsupported TTS_PROVIDER: {TTS_PROVIDER}. Use 'gemini' or 'azure'"
    )

PLAYBACK_ORDER += ["en", "zh"]
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
        "content": "你是一个专业的译者，将用户输入的句子翻译成中文。除了翻译之外不要有任何额外的输出。",
    },
    {
        "role": "user",
        "content": "１万円の安いギターでもギタリストにかかれば、高いギターを弾いているかのように錯覚してしまう。",
    },
    {
        "role": "assistant",
        "content": "即便是一把价值一万日元的廉价吉他，只要到了吉他手的手里，也会让人产生仿佛在弹奏昂贵名琴的错觉。",
    },
]
EN_TRANSLATION_PROMPT = [
    {
        "role": "system",
        "content": """You're a professional translator who translates sentences entered by users
        into English.Don't say anything other than the translation.""",
    },
    {
        "role": "user",
        "content": "１万円の安いギターでもギタリストにかかれば、高いギターを弾いているかのように錯覚してしまう。",
    },
    {
        "role": "assistant",
        "content": "In the hands of a skilled guitarist, even a cheap 10,000 yen guitar can sound as if they're playing an expensive one.",
    },
]
GRAMMAR_PROMPT_OPENAI = [
    {
        "role": "system",
        "content": """You're a language teacher who teaching user Japanese language,
        The user will give you the grammar point and example sentence.
        Explain the grammar in Japanese. And add more examples. Add Hiragana readings for kanji words(Only the first time).
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

GRAMMAR_PROMPT_GEMINI = [
    {
        "role": "system",
        "content": """You are a Japanese language teacher. The user provides a grammar point and example sentence.

Instructions:
- Explain the grammar directly in Japanese without greetings or acknowledgments
- Add 2-3 example sentences with English translations in parentheses
- Only add readings (in parentheses) for important kanji words, not every kanji
- Use ** to emphasize the grammar point
- Use clean markdown format
- Start your response immediately with the explanation""",
    },
    {
        "role": "user",
        "content": "Show me the usage of 「辛さ」 in the sentence この辛さは耐えられない。",
    },
    {
        "role": "assistant",
        "content": """「辛さ（つらさ）」は日本語の名詞で、「苦しさ」や「困難さ」を表現する際に使われます。「辛さ」は物理的な痛みだけでなく、心理的な困難やストレスについても言及することができます。

例文：

**辛さ**を我慢することは、強さではない。 (Enduring pain/hardship is not a strength.)
この料理の**辛さ**は何とも言えません。 (The spiciness of this dish is indescribable.)
彼女の失恋（しつれん）の**辛さ**を私には理解できない。 (I can't understand the pain of her broken heart.)""",
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


def _call_llm_api(messages: list[dict]) -> str | None:
    """Call the configured LLM API with the given messages.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys.
                 Format follows OpenAI's chat completion API.

    Returns:
        Generated text response from the LLM.

    Raises:
        RuntimeError: If the API call fails.
    """
    if LLM_PROVIDER == "openai":
        response = _openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
        )
        result = response.choices[0].message.content
        logger.debug("OpenAI API call successful")
        return result

    elif LLM_PROVIDER == "gemini":
        # Convert OpenAI-style messages to Gemini format with proper roles
        system_instruction = None
        contents = []

        for message in messages:
            role = message["role"]
            content = message["content"]

            if role == "system":
                # Extract system instruction (use the last one if multiple)
                system_instruction = content
            elif role == "user":
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=content)])
                )
            elif role == "assistant":
                # In Gemini SDK, assistant responses use "model" role
                contents.append(
                    types.Content(role="model", parts=[types.Part(text=content)])
                )

        # Generate content with system instruction if present
        if system_instruction:
            response = _gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
                ),
            )
        else:
            response = _gemini_client.models.generate_content(
                model=GEMINI_MODEL, contents=contents
            )

        logger.debug("Gemini API call successful")
        return response.text


def explain_grammar(text: str) -> str:
    grammar_pattern = extract_grammar.search(text)
    if grammar_pattern is not None:
        # Use provider-specific grammar prompt
        grammar_prompt = (
            GRAMMAR_PROMPT_GEMINI if LLM_PROVIDER == "gemini" else GRAMMAR_PROMPT_OPENAI
        )
        return translate(
            f"Show me the usage of 「{grammar_pattern.group(1)}」 in the sentence {text}",
            grammar_prompt,
        )
    return ""


def translate(text: str, context_messages: list) -> str:
    """Translate text using the configured LLM provider.

    Args:
        text: The text to translate or process.
        context_messages: List of context messages in OpenAI format.

    Returns:
        Translated or processed text.

    Raises:
        RuntimeError: If translation fails.
    """
    try:
        messages = context_messages + [{"role": "user", "content": text}]
        result = _call_llm_api(messages)
        logger.debug("Translation successful for text: %s", text)
        return result
    except Exception as e:
        logger.error("Failed to translate text: %s", text)
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
            return {
                "error": "Empty grammar markers {{}} are not allowed. Please provide a grammar pattern like {{pattern}}."
            }
    else:
        clean_text, grammar_pattern = extract_grammar_pattern(text)

    # Use clean text for hashing and audio generation
    text_hash = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
    for name, wav in wav_data:
        save_wav(f"{text_hash}.{name}.wav", wav)

    success = SentenceManager.save_sentence(
        user_id,
        text_hash,
        clean_text,
        en_text,
        zh_text,
        reading,
        explain,
        text,
        grammar_pattern,
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


def tts_gemini(
    text: str,
    language_code: str,
    voice_name: str | None = None,
    prompt: str | None = None,
) -> bytes:
    """Generate TTS audio using Google Gemini TTS.

    Args:
        text: Text to synthesize
        language_code: Language code (e.g., 'ja-JP', 'en-US', 'zh-CN')
        voice_name: Voice name (defaults to TTS_VOICE_NAME)
        prompt: Optional prompt for styling instructions (e.g., "Speak slowly and clearly")

    Returns:
        Audio data in WAV format

    Raises:
        RuntimeError: If TTS synthesis fails
    """
    global _gemini_tts_client

    try:
        # Lazy initialization of Gemini TTS client
        if _gemini_tts_client is None:
            from google.cloud import texttospeech

            _gemini_tts_client = texttospeech.TextToSpeechClient()
            logger.debug("Initialized Google Gemini TTS client")

        if voice_name is None:
            voice_name = TTS_VOICE_NAME

        from google.cloud import texttospeech

        # Create synthesis input with optional prompt
        if prompt:
            synthesis_input = texttospeech.SynthesisInput(text=text, prompt=prompt)
            logger.debug("Using prompt for TTS: %s", prompt)
        else:
            synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
            model_name=TTS_MODEL,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16
        )

        response = _gemini_tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        logger.debug(
            "Gemini TTS synthesis successful for voice: %s (prompt: %s)",
            voice_name,
            "yes" if prompt else "no",
        )
        return response.audio_content
    except Exception as e:
        logger.error("Gemini TTS API error: %s", e)
        logger.error("Failed to synthesize text: %s", text[:100])
        raise RuntimeError(f"Gemini TTS synthesis failed: {e}") from e


def tts_azure(text: str, synthesizer, ssml=False) -> bytes:
    """Generate TTS audio using Azure Speech Services.

    Args:
        text: Text to synthesize (or SSML string if ssml=True)
        synthesizer: Azure speech synthesizer instance
        ssml: Whether the text is SSML format

    Returns:
        Audio data in WAV format

    Raises:
        RuntimeError: If TTS synthesis fails
    """
    try:
        import azure.cognitiveservices.speech as speechsdk

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
        logger.error("Failed to synthesize text: %s", text[:100])
        raise RuntimeError(f"Azure TTS synthesis failed: {e}") from e


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

    logger.info("Starting TTS synthesis for multiple voices using %s", TTS_PROVIDER)
    wav_data = []
    if "gemini" in TTS_PROVIDER:
        wav_data += [
            (
                GEMINI_JP_VOICE_1,
                tts_gemini(clean_text, "ja-JP", voice_name=GEMINI_JP_VOICE_1),
            ),
            (
                GEMINI_JP_VOICE_2,
                tts_gemini(
                    clean_text,
                    "ja-JP",
                    voice_name=GEMINI_JP_VOICE_2,
                    prompt="Speak clearly for language learning purposes. Use a gentle, educational tone.",
                ),
            ),
        ]
        if "azure" not in TTS_PROVIDER:
            wav_data += [
                (
                    "en",
                    tts_gemini(
                        en_text,
                        "en-US",
                        prompt="Speak as a native speaker",
                        voice_name=TTS_VOICE_NAME,
                    ),
                ),
                (
                    "zh",
                    tts_gemini(
                        zh_text,
                        "cmn-CN",
                        prompt="Speak as a native speaker",
                        voice_name=TTS_VOICE_NAME,
                    ),
                ),
            ]
    if "azure" in TTS_PROVIDER:
        # Use Azure TTS with multiple Japanese voices
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

        wav_data += [
            (
                JP_MODEL_1,
                tts_azure(jp1_ssml_string, jp_speech_synthesizer, ssml=True),
            ),
            (
                JP_MODEL_2,
                tts_azure(jp2_ssml_string, jp_speech_synthesizer, ssml=True),
            ),
            (
                JP_MODEL_3,
                tts_azure(jp3_ssml_string, jp_speech_synthesizer, ssml=True),
            ),
            ("en", tts_azure(en_text, en_speech_synthesizer)),
            ("zh", tts_azure(zh_text, zh_speech_synthesizer)),
        ]
    if "azure" not in TTS_PROVIDER and "gemini" not in TTS_PROVIDER:
        raise ValueError(f"Unsupported TTS_PROVIDER: {TTS_PROVIDER}")

    logger.info("All TTS synthesis completed successfully")
    return wav_data


def concatenate_wavs(text_hash):
    data = []
    sample_rate = 0
    for model_name in PLAYBACK_ORDER:
        full_name = os.path.join(DATA_FOLDER, f"{text_hash}.{model_name}.wav")
        if not os.path.exists(full_name):
            logger.warning("Audio file not found, skipping: %s", full_name)
            continue
        try:
            with wave.open(full_name, "rb") as w:
                sample_rate = w.getframerate()
                data.append([w.getparams(), w.readframes(w.getnframes())])
        except (wave.Error, OSError) as e:
            logger.error("Failed to read audio file %s: %s", full_name, e)
            continue
    return data, sample_rate


def encode_audio_string(hash_text: list):
    wav_binary = io.BytesIO(b"")
    has_data = False

    try:
        with wave.open(wav_binary, "wb") as fout:
            for _, hash_info in enumerate(hash_text):
                data, sample_rate = concatenate_wavs(hash_info["hash"])
                if not data:
                    logger.warning(
                        "No audio data available for hash: %s", hash_info["hash"]
                    )
                    continue

                pause_frames = 2 * sample_rate
                pause_data = b"\x00" * pause_frames

                if not has_data:
                    fout.setparams(data[0][0])
                    has_data = True

                for i in range(len(data)):
                    fout.writeframes(data[i][1])
                    fout.writeframes(pause_data)
    except wave.Error as e:
        if has_data:
            logger.error("Wave file error: %s", e)
        else:
            logger.warning("No audio data available for any sentences")
        return None
    except (OSError, IndexError) as e:
        logger.error("Error processing audio data: %s", e)
        return None

    if not has_data:
        logger.warning("No audio data available for any sentences")
        return None

    audio_base64 = base64.b64encode(wav_binary.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{audio_base64}"


def get_available_voices(text_hash: str) -> list[dict]:
    """Get list of available voice files for a given sentence hash.

    Args:
        text_hash: The sentence hash to check

    Returns:
        List of dictionaries with voice information:
        [{"name": "voice_name", "display_name": "Display Name", "color": "css-color"}]
    """
    available_voices = []

    # Define voice display names and colors
    voice_info = {
        "Leda": {"display_name": "Leda (JP)", "color": "green"},
        "Zephyr": {"display_name": "Zephyr (Slow JP)", "color": "purple"},
        "ja-JP-AoiNeural": {"display_name": "Aoi", "color": "green"},
        "ja-JP-Nanami:DragonHDLatestNeural": {"display_name": "Nanami", "color": "green"},
        "ja-JP-Masaru:DragonHDLatestNeural": {"display_name": "Masaru", "color": "green"},
        "ja-JP-MayuNeural": {"display_name": "Mayu", "color": "green"},
        "ja-JP-DaichiNeural": {"display_name": "Daichi", "color": "green"},
        "en": {"display_name": "English", "color": "blue"},
        "zh": {"display_name": "Chinese", "color": "red"},
    }

    # Check for all possible voice names from both TTS providers
    # This ensures backward compatibility with files created by different providers
    all_possible_voices = [
        # Gemini voices
        "Leda",
        "Zephyr",
        # Azure voices
        "ja-JP-AoiNeural",
        "ja-JP-Nanami:DragonHDLatestNeural",
        "ja-JP-Masaru:DragonHDLatestNeural",
        "ja-JP-MayuNeural",
        "ja-JP-DaichiNeural",
        # Common voices for both providers
        "en",
        "zh",
    ]

    for voice_name in all_possible_voices:
        full_name = os.path.join(DATA_FOLDER, f"{text_hash}.{voice_name}.wav")
        if os.path.exists(full_name):
            info = voice_info.get(
                voice_name, {"display_name": voice_name, "color": "gray"}
            )
            available_voices.append(
                {
                    "name": voice_name,
                    "display_name": info["display_name"],
                    "color": info["color"],
                }
            )

    return available_voices


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
    if sort_type == "all":
        return SentenceManager.get_all_sentences(user_id, return_count, offset)
    else:
        return SentenceManager.get_random_sentences(user_id, return_count, offset)


def save_generated_sentence(user_id: int, sentence_data: dict):
    """Save a generated sentence with its audio files"""
    logger.debug("save_generated_sentence called with data: %s", sentence_data)

    # Get the original text with markers if available
    # This is the text the user originally entered with {{}} markers
    original_text_with_markers = sentence_data.get(
        "original_text", sentence_data["ja_text"]
    )
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
