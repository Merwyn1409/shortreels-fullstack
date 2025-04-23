import asyncio
from video_fetcher import fetch_media

async def test_fetch():
    text = "Strong women don’t wait for permission they create inspire and lead. Every reel is a story of resilience power and confidence. Keep pushing boundaries embracing challenges and proving that nothing is impossible."
    result = await fetch_media(text)
    print(result)  # Print the fetched videos for each sentence

if __name__ == "__main__":
    asyncio.run(test_fetch())  # Run the async function
