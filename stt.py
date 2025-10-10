import speech_recognition as sr

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Mów teraz... (5 sekund na rozpoczęcie)")
        try:
            audio = r.listen(source, timeout=5)  # 5 s
            text = r.recognize_google(audio, language="pl-PL")
            return text
        except sr.WaitTimeoutError:
            return ""  #czekanie
        except sr.UnknownValueError:
            return ""  #wtf
        except sr.RequestError as e:
            return f"Błąd połączenia ze STT: {str(e)}"