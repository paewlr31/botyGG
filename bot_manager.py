from openai import OpenAI
import random
import logging

class Bot:
    def __init__(self, name, system_prompt):
        self.name = name
        self.system_prompt = system_prompt

class BotManager:
    def __init__(self, openai_api_key):
        self.bots = []
        self.client = OpenAI(api_key=openai_api_key)
        self.last_input = None
        self.last_speaker = None
        self.silence_counter = 0

    def add_bot(self, name, system_prompt):
        self.bots.append(Bot(name, system_prompt))
        logging.info(f"Dodano bota {name} z promptem: {system_prompt}")

    def remove_bot(self, name):
        bots_before = len(self.bots)
        self.bots = [bot for bot in self.bots if bot.name.lower() != name.lower()]
        if len(self.bots) < bots_before:
            if self.last_speaker and self.last_speaker.lower() == name.lower():
                self.last_speaker = None
            return True
        return False

    def get_response(self, user_input, system_prompt):
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=30,
                temperature=0.8,
                top_p=0.95
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Błąd API Open AI: {str(e)}")
            return f"Błąd API Open AI: {str(e)}"

    def process_user_input(self, user_input, log, send_to_bots, speak):
        self.silence_counter = 0
        self.last_input = user_input
        self.last_speaker = None

        if not self.bots:
            log("Nie ma żadnych botów. Dodaj bota komendą 'Dodaj bota <nazwa> jako <charakter>'.")
            speak("Nie ma żadnych botów. Dodaj bota.")
            return

        for bot in self.bots:
            response = self.get_response(user_input, bot.system_prompt)
            log(f"🤖 {bot.name}: {response}")
            speak(f"{bot.name} mówi: {response}")
            send_to_bots({"type": "response", "bot_name": bot.name, "message": response})
            self.last_input = response
            self.last_speaker = bot.name

        self.handle_bot_conversation(log, send_to_bots, speak)

    def process_bot_message(self, bot_name, message, log, send_to_bots, speak):
        self.silence_counter = 0
        self.last_input = message
        self.last_speaker = bot_name
        send_to_bots({"type": "response", "bot_name": bot_name, "message": message})
        self.handle_bot_conversation(log, send_to_bots, speak)

    def handle_bot_conversation(self, log, send_to_bots, speak):
        if len(self.bots) < 2 or self.silence_counter >= 2:
            return
        available_bots = [bot for bot in self.bots if bot.name != self.last_speaker]
        if not available_bots:
            return
        current_bot = random.choice(available_bots)
        context = self.last_input if self.last_input else "Cześć, co słychać?"
        response = self.get_response(context, current_bot.system_prompt)
        log(f"🤖 {current_bot.name}: {response}")
        send_to_bots({"type": "response", "bot_name": current_bot.name, "message": response})