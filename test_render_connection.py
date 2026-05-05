import os
from dotenv import load_dotenv
import httpx

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
print(f"Ключ: {api_key[:20]}...{api_key[-10:] if api_key else 'НЕ НАЙДЕН'}")

async def test_key():
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        print(f"Статус: {response.status_code}")
        if response.status_code == 200:
            print("✅ Ключ работает!")
            data = response.json()
            models = [m['id'] for m in data.get('data', []) if 'gpt' in m['id']]
            print(f"Доступные модели: {models}")
        else:
            print(f"❌ Ошибка: {response.text[:200]}")

import asyncio
asyncio.run(test_key())