import speech_recognition as sr

def listen():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Mów teraz...")
        audio = r.listen(source)
    try:
        text = r.recognize_google(audio, language="pl-PL")
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        return "Błąd połączenia ze STT"