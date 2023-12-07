import os

import azure.cognitiveservices.speech as speechsdk

speech_config = speechsdk.SpeechConfig(
    subscription=os.getenv('AZURE_SERVICE_TOKEN'),
    region='japaneast',
)
audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)


# The language of the voice that speaks.
speech_config.speech_synthesis_voice_name='ja-JP-AoiNeural'
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

def tts(text, save_path=None):
    ssml_string = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
    <voice name='ja-JP-AoiNeural' style='cheerful'>
        <prosody rate='-10%'>
            {text}
        </prosody>
    </voice>
    </speak>
    """
    speech_synthesis_result = speech_synthesizer.speak_ssml_async(ssml_string).get()
    # speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()
    if speech_synthesis_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        # print("Speech synthesized for text [{}]".format(text))
        # return speech_synthesis_result.data
        # if save_path is not None:
        #     save(text, speech_synthesis_result.audio_data, save_path)
        return speech_synthesis_result.audio_data
    elif speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        print("Speech synthesis canceled: {}".format(cancellation_details.reason))
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            if cancellation_details.error_details:
                print("Error details: {}".format(cancellation_details.error_details))
                print("Did you set the speech resource key and region values?")
    print(speech_synthesis_result.reason)


text = '全国に約25,000社あり、長野県の諏訪湖近くの諏訪大社（旧称：諏訪神社）を総本社とする。また、諏訪神社を中心とする神道の信仰を諏訪信仰（すわしんこう）という。'
wav_data = tts(text)
print(len(wav_data))