import logging
import time
from stt import listen
from bot import get_response
from tts import speak
import random

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class Bot:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

def main():
    logging.info("🤖 Witaj! Rozpoczynamy rozmowę. Powiedz 'do widzenia', aby zakończyć.")
    logging.info("Komendy: 'Dodaj bota <nazwa> jako <charakter>', 'Idź bot <nazwa>'")

    # Pusta lista botów na start
    bots = []
    last_input = None  # Przechowuje ostatnią wypowiedź (użytkownika lub bota)

    # Główna pętla rozmowy
    while True:
        try:
            user_input = listen()  # listen ma teraz timeout=5 sekund
            if user_input:
                logging.info(f"🧍 Ty: {user_input}")
                last_input = user_input

                # Obsługa komend
                if user_input.lower().startswith("dodaj bota"):
                    try:
                        # Poprawione parsowanie: np. "Dodaj bota Rafał jako pisarz" -> nazwa: "Rafał"
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
                        else:
                            response = f"Nie znaleziono bota {bot_name}."
                        logging.info(f"🤖 System: {response}")
                        speak(response)
                    except:
                        response = "Błąd: Podaj poprawną nazwę bota, np. 'Idź bot Rafał'."
                        logging.info(f"🤖 System: {response}")
                        speak(response)
                    continue

                if "do widzenia" in user_input.lower():
                    response = "Do widzenia! Kończę rozmowę."
                    logging.info(f"🤖 System: {response}")
                    speak(response)
                    break

            # Jeśli są boty
            if bots:
                # Jeśli użytkownik mówił, każdy bot odpowiada użytkownikowi
                if user_input:
                    for bot in bots:
                        response = get_response(user_input, bot.system_prompt)
                        logging.info(f"🤖 {bot.name}: {response}")
                        try:
                            speak(f"{bot.name} mówi: {response}")
                            last_input = response
                            time.sleep(0.5)
                        except Exception as e:
                            logging.error(f"Błąd TTS dla {bot.name}: {str(e)}")

                # Boty rozmawiają między sobą (zawsze, jeśli jest co najmniej jeden bot)
                logging.info("🤖 Boty rozmawiają między sobą...")
                # Losowy bot mówi
                current_bot = random.choice(bots)
                context = last_input if last_input else "Cześć, co słychać?"
                response = get_response(context, current_bot.system_prompt)
                logging.info(f"🤖 {current_bot.name}: {response}")
                try:
                    speak(f"{current_bot.name} mówi: {response}")
                    last_input = response
                    time.sleep(0.5)
                except Exception as e:
                    logging.error(f"Błąd TTS dla {current_bot.name}: {str(e)}")

            # Jeśli nie ma botów i użytkownik coś powiedział (poza komendami)
            if not bots and user_input and not user_input.lower().startswith(("dodaj bota", "do widzenia")):
                response = "Nie ma żadnych botów. Dodaj bota komendą 'Dodaj bota <nazwa> jako <charakter>'."
                logging.info(f"🤖 System: {response}")
                speak(response)

        except Exception as e:
            logging.error(f"Błąd w głównej pętli: {str(e)}")
            continue

def get_response(user_input, system_prompt="Jesteś pomocnym asystentem, który odpowiada w języku polskim."):
    from openai import OpenAI
    from dotenv import load_dotenv
    import os

    load_dotenv("klucz.env")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            max_tokens=100,
            temperature=0.8,
            top_p=0.95
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd API Open AI: {str(e)}"

if __name__ == "__main__":
    main()