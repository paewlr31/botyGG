import os
import tempfile
from gtts import gTTS
from playsound import playsound
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
#tutaj mp3 
def speak(text):
    if not text or not text.strip():
        return
    try:
        logging.info(f"Mówię: {text}")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=text, lang="pl")
            tts.save(fp.name)
            temp_path = fp.name
        playsound(temp_path)
        os.remove(temp_path)
    except Exception as e:
        logging.error(f"Błąd w TTS: {e}")
