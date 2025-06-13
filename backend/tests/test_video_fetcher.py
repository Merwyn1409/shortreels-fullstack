import asyncio
from app.video_fetcher import fetch_media

async def test():
    text ='I have, for the first time, found what I can truly love—I have found you. You are my sympathy—my better self—my good angel; I am bound to you with a strong attachment. I think you are good, gifted, lovely: a fervent, a solemn passion is conceived in my heart; '
    result = await fetch_media(text)
    print("Test Results:")
    for item in result:
        print(f"\noriginal: {item['original']}")
        print(f"clean_sentence: {item['clean sentence']}")
        print(f"Videos: {item['videos']}")

asyncio.run(test())