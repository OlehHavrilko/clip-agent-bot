import asyncio
from app.searcher import search_and_download

async def main():
    # Test data
    scene_data = {
        "search_queries": [
            "famous movie quote",
            "popular scene",
            "classic dialogue"
        ]
    }
    job_id = "test123"
    
    try:
        result = await search_and_download(scene_data, job_id)
        print(f"Download successful: {result}")
    except Exception as e:
        print(f"Download failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())