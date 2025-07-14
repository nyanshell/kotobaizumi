"""Tests for utility functions."""

import base64
import io
import wave
from unittest.mock import patch

from app.utils import (
    encode_audio_string,
    explain_grammar,
    extract_grammar_pattern,
    generate_sentence_content,
    save_generated_sentence,
    translate,
)


class TestTranslationFunctions:
    """Test cases for translation and AI functions."""

    def test_translate_basic(self, mock_openai):
        """Test basic translation functionality."""
        text = "Hello world"
        context = [{"role": "system", "content": "Translate to Japanese"}]

        result = translate(text, context)

        assert result == "Test translation response"
        mock_openai.chat.completions.create.assert_called_once()

    def test_explain_grammar_with_pattern(self, mock_openai):
        """Test grammar explanation with valid pattern."""
        text = "新学年を迎える{{にあたって}}、計画を立てました。"

        result = explain_grammar(text)

        assert result == "Test translation response"
        mock_openai.chat.completions.create.assert_called_once()

    def test_explain_grammar_without_pattern(self, mock_openai):
        """Test grammar explanation without pattern returns empty string."""
        text = "普通の文章です。"

        result = explain_grammar(text)

        assert result == ""
        mock_openai.chat.completions.create.assert_not_called()

    @patch("app.utils.translate")
    def test_generate_sentence_content(self, mock_translate, mock_azure_speech):
        """Test sentence content generation."""
        mock_translate.side_effect = [
            "Test explanation",  # explain_grammar
            "Test Chinese",  # Chinese translation
            "Test English",  # English translation
            "Test reading",  # Reading
        ]

        text = "テスト{{文章}}です。"

        result = generate_sentence_content(text)

        assert result["ja_text"] == "テスト文章です。"
        assert result["en_text"] == "Test English"
        assert result["cn_text"] == "Test Chinese"
        assert result["explain"] == "Test explanation"
        assert result["reading"] == "Test reading"
        assert "wav_data" in result
        assert len(result["wav_data"]) == 5  # 3 JP + EN + ZH


class TestGrammarFunctions:
    """Test cases for grammar pattern extraction and processing."""

    def test_extract_grammar_pattern_with_pattern(self):
        """Test extracting grammar pattern from text with {{}} markers."""
        input_text = "新学年を迎える{{にあたって}}、計画を立てました。"
        clean_text, grammar = extract_grammar_pattern(input_text)

        assert clean_text == "新学年を迎えるにあたって、計画を立てました。"
        assert grammar == "にあたって"

    def test_extract_grammar_pattern_no_pattern(self):
        """Test extracting grammar pattern from text without {{}} markers."""
        input_text = "普通の文章です。"
        clean_text, grammar = extract_grammar_pattern(input_text)

        assert clean_text == "普通の文章です。"
        assert grammar is None

    def test_extract_grammar_pattern_multiple_patterns(self):
        """Test extracting grammar pattern from text with multiple {{}} markers."""
        input_text = "{{これは}}テスト{{文章}}です。"
        clean_text, grammar = extract_grammar_pattern(input_text)

        # Should extract only the first pattern
        assert clean_text == "これはテスト文章です。"
        assert grammar == "これは"

    def test_extract_grammar_pattern_empty_string(self):
        """Test extracting grammar pattern from empty string."""
        input_text = ""
        clean_text, grammar = extract_grammar_pattern(input_text)

        assert clean_text == ""
        assert grammar is None

    def test_extract_grammar_pattern_empty_markers(self):
        """Test extracting grammar pattern from text with empty {{}} markers."""
        input_text = "テスト{{}}文章です。"
        clean_text, grammar = extract_grammar_pattern(input_text)

        # Empty markers should be treated as no pattern found
        assert clean_text == "テスト{{}}文章です。"
        assert grammar is None

    def test_extract_grammar_pattern_whitespace_only_markers(self):
        """Test extracting grammar pattern from text with whitespace-only {{}} markers."""
        input_text = "テスト{{  }}文章です。"
        clean_text, grammar = extract_grammar_pattern(input_text)

        # Whitespace-only markers should be treated as no pattern found
        assert clean_text == "テスト{{  }}文章です。"
        assert grammar is None


class TestAudioFunctions:
    """Test cases for audio processing functions."""

    def test_encode_audio_string_empty_list(self):
        """Test audio encoding with empty sentence list."""
        result = encode_audio_string([])

        # Should return a data URL for an empty WAV file
        assert result.startswith("data:audio/wav;base64,")

        # Decode and verify it's valid base64
        base64_data = result.split(",")[1]
        decoded = base64.b64decode(base64_data)
        assert len(decoded) > 0

    @patch("app.utils.concatenate_wavs")
    def test_encode_audio_string_with_sentences(self, mock_concatenate):
        """Test audio encoding with sentence data."""
        # Mock concatenate_wavs to return fake WAV data
        mock_params = (1, 1, 2, "NONE", "not compressed", "not compressed")
        mock_concatenate.return_value = (
            [[mock_params, b"fake_audio_data_1"], [mock_params, b"fake_audio_data_2"]],
            44100,
        )

        sentences = [{"hash": "test_hash_1"}, {"hash": "test_hash_2"}]

        result = encode_audio_string(sentences)

        assert result.startswith("data:audio/wav;base64,")
        assert len(result) > 50  # Should have significant content

    @patch("app.utils.os.path.join")
    @patch("app.utils.wave.open")
    def test_concatenate_wavs(self, mock_wave_open, mock_path_join):
        """Test WAV file concatenation."""
        from app.utils import concatenate_wavs

        # Mock wave file objects
        mock_wav1 = io.BytesIO()
        mock_wav2 = io.BytesIO()

        # Create actual WAV data for testing
        with wave.open(mock_wav1, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\x00\x00" * 100)

        with wave.open(mock_wav2, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(b"\x00\x00" * 100)

        mock_wav1.seek(0)
        mock_wav2.seek(0)

        mock_wave_open.side_effect = [
            wave.open(mock_wav1, "rb"),
            wave.open(mock_wav2, "rb"),
        ]

        data, sample_rate = concatenate_wavs("test_hash")

        assert sample_rate == 44100
        assert len(data) == 2  # Should have data from 2 files


class TestSentenceSaving:
    """Test cases for sentence saving functions."""

    @patch("app.utils.SentenceManager.save_sentence")
    @patch("app.utils.save_wav")
    def test_save_generated_sentence_success(self, mock_save_wav, mock_save_sentence):
        """Test successful sentence saving."""
        mock_save_sentence.return_value = True

        sentence_data = {
            "ja_text": "テスト",
            "en_text": "Test",
            "cn_text": "测试",
            "reading": "テスト",
            "explain": "Explanation",
            "wav_data": [("model1", b"audio1"), ("model2", b"audio2")],
        }

        result = save_generated_sentence(1, sentence_data)

        assert "hash" in result
        assert result["ja_text"] == "テスト"
        assert "error" not in result

        # Verify WAV files were saved
        assert mock_save_wav.call_count == 2

    @patch("app.utils.SentenceManager.save_sentence")
    @patch("app.utils.save_wav")
    def test_save_generated_sentence_failure(self, mock_save_wav, mock_save_sentence):
        """Test sentence saving failure."""
        mock_save_sentence.return_value = False

        sentence_data = {
            "ja_text": "テスト",
            "en_text": "Test",
            "cn_text": "测试",
            "reading": "テスト",
            "explain": "Explanation",
            "wav_data": [("model1", b"audio1")],
        }

        result = save_generated_sentence(1, sentence_data)

        assert "error" in result
        assert "Failed to save sentence" in result["error"]


class TestUtilityFunctions:
    """Test cases for utility helper functions."""

    @patch("app.utils.open", create=True)
    def test_save_wav(self, mock_open):
        """Test WAV file saving."""
        from app.utils import save_wav

        mock_file = mock_open.return_value.__enter__.return_value

        save_wav("test.wav", b"fake_audio_data")

        mock_open.assert_called_once()
        mock_file.write.assert_called_once_with(b"fake_audio_data")

    def test_remove_sentence_with_user_id(self):
        """Test sentence removal function."""
        from app.utils import remove_sentence

        with patch("app.utils.SentenceManager.delete_sentence") as mock_delete:
            mock_delete.return_value = True

            result = remove_sentence(1, "test_hash")

            assert result is True
            mock_delete.assert_called_once_with(1, "test_hash")

    def test_get_phrases_review_mode(self):
        """Test getting phrases in review mode."""
        from app.utils import get_phrases

        with patch("app.utils.SentenceManager.get_sentences_for_review") as mock_get:
            mock_get.return_value = [{"id": 1, "ja_text": "テスト"}]

            result = get_phrases(1, "review", 5)

            assert len(result) == 1
            mock_get.assert_called_once_with(1, 5)

    def test_get_phrases_random_mode(self):
        """Test getting phrases in random mode."""
        from app.utils import get_phrases

        with patch("app.utils.SentenceManager.get_random_sentences") as mock_get:
            mock_get.return_value = [{"id": 1, "ja_text": "ランダム"}]

            result = get_phrases(1, "random", 3)

            assert len(result) == 1
            mock_get.assert_called_once_with(1, 3)
