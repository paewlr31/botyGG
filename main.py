import logging
import time
import random
from stt import listen
from bot import get_response
from tts import speak
import numpy as np
import sounddevice as sd 
import ggwave  
from gglink  import send_via_ggwave, receive_via_ggwave, play_ggwave_like_sound 

class Bot:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

def main():
    logging.info("🤖 Witaj! Rozpoczynamy rozmowę. Powiedz 'do widzenia', aby zakończyć.")
    logging.info("Komendy: 'Dodaj bota <nazwa> jako <charakter>', 'Idź bot <nazwa>'")

    bots = []
    last_input = None
    last_speaker = None
    silence_counter = 0  

    while True:
        try:
            user_input = listen()  

            if user_input:
                silence_counter = 0
                logging.info(f"🧍 Ty: {user_input}")
                last_input = user_input
                last_speaker = None  

                # ======= KOMENDY =======
                if user_input.lower().startswith("dodaj bota"):
                    try:
                        parts = user_input.lower().split(" jako ")
                        bot_name = parts[0].replace("dodaj bota ", "").strip()
                        bot_character = parts[1].strip()
                        bots.append(Bot(bot_name, f"Jesteś {bot_character}, który odpowiada w języku polskim."))
                        response = f"Dodano bota {bot_name} jako {bot_character}."
                        logging.info(f"🤖 System: {response}")
                        speak(response)
                    except IndexError:
                        response = "Błąd: Podaj nazwę bota i charakter, np. 'Dodaj bota Rafał jako pisarz'."
                        logging.info(f"🤖 System: {response}")
                        speak(response)
                    continue

                if user_input.lower().startswith("idź bot"):
                    try:
                        bot_name = user_input.lower().replace("idź bot ", "").strip()
                        bots_before = len(bots)
                        bots = [bot for bot in bots if bot.name.lower() != bot_name.lower()]
                        if len(bots) < bots_before:
                            response = f"Usunięto bota {bot_name}."
                            if last_speaker and last_speaker.lower() == bot_name.lower():
                                last_speaker = None
                        else:
                            response = f"Nie znaleziono bota {bot_name}."
                        logging.info(f"🤖 System: {response}")
                        speak(response)
                    except Exception:
                        response = "Błąd: Podaj poprawną nazwę bota, np. 'Idź bot Rafał'."
                        logging.info(f"🤖 System: {response}")
                        speak(response)
                    continue

                if "do widzenia" in user_input.lower():
                    response = "Do widzenia! Kończę rozmowę."
                    logging.info(f"🤖 System: {response}")
                    speak(response)
                    break

            else:
             
                silence_counter += 1

            if bots:
          
                if user_input:
                    for bot in bots:
                        response = get_response(user_input, bot.system_prompt)
                        logging.info(f"🤖 {bot.name}: {response}")
                        try:
                            speak(f"{bot.name} mówi: {response}")
                            last_input = response
                            last_speaker = bot.name
                            time.sleep(0.5)
                        except Exception as e:
                            logging.error(f"Błąd TTS dla {bot.name}: {str(e)}")

                # ======= BOT↔BOT – GGWAVE TRYB =======
                if silence_counter >= 2 and len(bots) > 1:
                    current_bot = random.choice([b for b in bots if b.name != last_speaker])
                    context = last_input if last_input else "Cześć, co słychać?"
                    response = get_response(context, current_bot.system_prompt)

                    logging.info(f"🤖 {current_bot.name}: {response}")

                    # Wyślij przez GGWave
                    send_via_ggwave(response)
                    # Odbierz z mikrofonu
                    decoded = receive_via_ggwave(timeout=3.0)
                    if decoded:
                        logging.info(f"📡 {current_bot.name} (GGWave odebrane): {decoded}")
                        last_input = decoded
                    else:
                        logging.warning("⚠️ GGWave nie odebrał niczego, fallback do TTS")
                        speak(f"{current_bot.name} mówi: {response}")
                        last_input = response

                    last_speaker = current_bot.name

           
                elif len(bots) >= 1:
                    available_bots = [bot for bot in bots if bot.name != last_speaker]
                    if available_bots:
                        logging.info("🤖 Boty rozmawiają między sobą (tryb normalny)...")
                        current_bot = random.choice(available_bots)
                        context = last_input if last_input else "Cześć, co słychać?"
                        response = get_response(context, current_bot.system_prompt)
                        logging.info(f"🤖 {current_bot.name}: {response}")
                        try:
                            speak(f"{current_bot.name} mówi: {response}")
                            last_input = response
                            last_speaker = current_bot.name
                            time.sleep(0.5)
                        except Exception as e:
                            logging.error(f"Błąd TTS dla {current_bot.name}: {str(e)}")

            if not bots and user_input and not user_input.lower().startswith(("dodaj bota", "do widzenia")):
                response = "Nie ma żadnych botów. Dodaj bota komendą 'Dodaj bota <nazwa> jako <charakter>'."
                logging.info(f"🤖 System: {response}")
                speak(response)

        except Exception as e:
            logging.error(f"Błąd w głównej pętli: {str(e)}")
            continue

if __name__ == "__main__":
    main()