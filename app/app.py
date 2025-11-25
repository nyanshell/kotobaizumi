import json
import os
import re

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from .database import SentenceManager, UserManager
from .settings import logger
from .utils import (
    encode_audio_string,
    encode_single_voice_audio,
    generate_sentence_content,
    get_available_voices,
    get_phrases,
    remove_sentence,
    save_generated_sentence,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-change-this")


@app.template_filter("highlight_grammar")
def highlight_grammar_filter(text):
    """Highlight grammar patterns in Japanese text"""
    if not text:
        return text
    # Replace {{pattern}} with highlighted spans
    pattern = re.compile(r"{{([^}]+)}}")
    highlighted = pattern.sub(
        r'<span class="bg-green-200 text-green-800 px-1 py-0.5 rounded font-medium">\1</span>',
        text,
    )
    logger.debug(f"Highlighting grammar patterns in text: {text} -> {highlighted}")
    return highlighted


@app.before_request
def log_request():
    logger.info(f"REQUEST: {request.method} {request.path}")
    logger.info(
        f"User authenticated: {current_user.is_authenticated if hasattr(current_user, 'is_authenticated') else 'N/A'}"
    )
    if request.method == "POST":
        logger.info(f"Form data: {dict(request.form)}")


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    user_data = UserManager.get_user_by_id(int(user_id))
    if user_data:
        return User(user_data["id"], user_data["username"])
    return None


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user_data = UserManager.authenticate_user(username, password)
        if user_data:
            user = User(user_data["id"], user_data["username"])
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    sort_type = request.args.get("sort", "random")

    # Set default count based on sort type
    default_count = {"random": 1, "all": 10}.get(sort_type, 10)

    try:
        return_count = int(request.args.get("count", default_count))
    except ValueError:
        return_count = default_count

    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1

    offset = (page - 1) * return_count

    phrase_meta = get_phrases(
        current_user.id, sort_type, return_count=return_count, offset=offset
    )
    logger.debug(f"Phrase meta data retrieved: {phrase_meta}")

    # Add available voices to each sentence
    if phrase_meta:
        for sentence in phrase_meta:
            sentence["available_voices"] = get_available_voices(sentence["hash"])
        audio_string = encode_audio_string(phrase_meta)
    else:
        audio_string = None

    return render_template(
        "index.html", audio_string=audio_string, data=phrase_meta, sort_type=sort_type
    )


@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if not text:
            flash("Please enter some text")
            return redirect(url_for("generate"))

        try:
            sentence_data = generate_sentence_content(text)
            session_data = {
                "ja_text": sentence_data["ja_text"],
                "en_text": sentence_data["en_text"],
                "cn_text": sentence_data["cn_text"],
                "reading": sentence_data["reading"],
                "explain": sentence_data["explain"],
            }
            session["pending_sentence"] = session_data
            session["original_text"] = text
            return render_template("confirm.html", sentence_data=sentence_data)
        except Exception as e:
            flash(f"Error generating sentence: {str(e)}")
            return redirect(url_for("generate"))

    return render_template("generate.html")


@app.route("/confirm", methods=["POST"])
@login_required
def confirm():
    logger.info("=== CONFIRM ROUTE START ===")
    action = request.form.get("action")
    logger.info(f"Action received: {action}")
    logger.info(f"Current user ID: {current_user.id}")
    logger.info(f"Form data keys: {list(request.form.keys())}")

    # Log session contents
    logger.info(f"Session keys: {list(session.keys())}")
    has_pending = "pending_sentence" in session
    has_original = "original_text" in session
    logger.info(
        f"Has pending_sentence: {has_pending}, has original_text: {has_original}"
    )

    # Treat any POST with sentence data as save action if action is missing
    if action == "save" or (action is None and request.form.get("ja_text")):
        if action is None:
            logger.info(
                "Action was None, but treating as save since ja_text is present"
            )
        logger.info("Processing save action")
        sentence_data = session.get("pending_sentence")
        logger.info(f"Retrieved sentence_data: {sentence_data is not None}")

        if sentence_data:
            logger.info(
                f"Original sentence_data keys: {list(sentence_data.keys()) if sentence_data else 'None'}"
            )

            # Allow user to edit the translations
            original_ja = sentence_data.get("ja_text", "")
            form_ja = request.form.get("ja_text", "")
            logger.info(f"JA text: original='{original_ja}', form='{form_ja}'")

            sentence_data["ja_text"] = request.form.get(
                "ja_text", sentence_data["ja_text"]
            )
            sentence_data["en_text"] = request.form.get(
                "en_text", sentence_data["en_text"]
            )
            sentence_data["cn_text"] = request.form.get(
                "cn_text", sentence_data["cn_text"]
            )
            sentence_data["reading"] = request.form.get(
                "reading", sentence_data["reading"]
            )
            sentence_data["explain"] = request.form.get(
                "explain", sentence_data["explain"]
            )

            logger.info(f"Updated sentence_data: {sentence_data}")

            # Save the edited sentence data
            try:
                logger.info("About to call save_generated_sentence")
                # Pass the original text with markers if available
                original_text = session.get("original_text")
                if original_text:
                    sentence_data["original_text"] = original_text
                result = save_generated_sentence(current_user.id, sentence_data)
                logger.info(f"save_generated_sentence returned: {result}")

                if "error" not in result:
                    logger.info("Save successful, showing success page")
                    flash("Sentence saved successfully!")
                    session.pop("pending_sentence", None)
                    session.pop("original_text", None)
                    # Show the saved sentence instead of redirecting
                    return render_template(
                        "confirm.html", sentence_data=result, saved=True
                    )
                else:
                    logger.error(f"Save failed with error: {result['error']}")
                    flash(f"Error saving sentence: {result['error']}")
            except Exception as e:
                logger.error(f"Exception during save: {e}", exc_info=True)
                flash(f"Error saving sentence: {str(e)}")
        else:
            logger.warning("No sentence data found in session")
            flash("No sentence data found")
    else:
        logger.info(f"Non-save action: {action}")

    logger.info("Cleaning up session and redirecting to generate")
    session.pop("pending_sentence", None)
    session.pop("original_text", None)
    return redirect(url_for("generate"))


@app.route("/delete/<string:hash_text>", methods=["DELETE"])
@login_required
def delete_sentence(hash_text):
    if remove_sentence(current_user.id, hash_text):
        return json.dumps({"result": "done!"})
    else:
        return json.dumps({"result": "error"}), 400


@app.route("/audio/<string:hash_text>/<string:voice_name>")
@login_required
def get_voice_audio(hash_text, voice_name):
    # Verify the user owns this sentence
    sentence = SentenceManager.get_sentence_by_hash(current_user.id, hash_text)
    if not sentence:
        return json.dumps({"result": "error"}), 404

    # Track the audio play for specific voice and overall sentence
    SentenceManager.track_audio_play(sentence["id"], voice_name)
    SentenceManager.track_sentence_play(sentence["id"])

    audio_data = encode_single_voice_audio(hash_text, voice_name)
    if audio_data:
        return json.dumps({"audio": audio_data})
    else:
        return json.dumps({"result": "error"}), 404


@app.route("/audio-stats/<string:hash_text>")
@login_required
def get_audio_stats(hash_text):
    # Verify the user owns this sentence
    sentence = SentenceManager.get_sentence_by_hash(current_user.id, hash_text)
    if not sentence:
        return json.dumps({"result": "error"}), 404

    stats = SentenceManager.get_grammar_play_stats(sentence["id"])
    return json.dumps({"stats": stats})


@app.route("/combined-audio/<string:hash_text>")
@login_required
def get_combined_audio(hash_text):
    # Verify the user owns this sentence
    sentence = SentenceManager.get_sentence_by_hash(current_user.id, hash_text)
    if not sentence:
        return json.dumps({"result": "error"}), 404

    # Generate combined audio for this single sentence
    audio_data = encode_audio_string([{"hash": hash_text}])
    if audio_data:
        return json.dumps({"audio": audio_data})
    else:
        return json.dumps({"result": "error"}), 404


@app.route("/track-combined-audio/<string:hash_text>", methods=["POST"])
@login_required
def track_combined_audio_play(hash_text):
    """Track when combined audio is played"""
    # Verify the user owns this sentence
    sentence = SentenceManager.get_sentence_by_hash(current_user.id, hash_text)
    if not sentence:
        return json.dumps({"result": "error"}), 404

    # Track the play count for combined audio (use 'combined' as voice name)
    SentenceManager.track_audio_play(sentence["id"], "combined")
    SentenceManager.track_sentence_play(sentence["id"])

    return json.dumps({"result": "success"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
