from stt import listen
from bot import get_response
from tts import speak
import logging
import time

#speech to text
#open ai
#test to speech

#bot glowny i towarzyszace

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    logging.info("🤖 Witaj! Rozpoczynamy rozmowę. Powiedz 'do widzenia', aby zakończyć.")
    while True:
        user_input = listen()
        if user_input == "":
            continue
        logging.info(f"🧍 Ty: {user_input}")
        response = get_response(user_input)
        logging.info(f"🤖 Bot: {response}")
        try:
            speak(response)
            time.sleep(0.5)  # Krótkie opóźnienie między wypowiedziami zeby sie nie przeladowalo
        except Exception as e:
            logging.error(f"Błąd TTS w main: {str(e)}")
        if "do widzenia" in user_input.lower():
            break

if __name__ == "__main__":
    main()