from openai import OpenAI
from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv("klucz.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_response(user_input):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Jesteś pomocnym asystentem, który odpowiada w języku polskim."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=100,
            temperature=0.8,
            top_p=0.95
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd API Open AI: {str(e)}"