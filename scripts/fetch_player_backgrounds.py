import os
import time
import requests
from duckduckgo_search import DDGS
from PIL import Image
from io import BytesIO

# The players currently featured on the Point-in-Time Ledger
PLAYERS = [
    "Russell Wilson",
    "Aaron Rodgers",
    "Deshaun Watson",
    "Ezekiel Elliott",
    "Jamal Adams",
    "Julio Jones",
    "Le'Veon Bell",
    "Carson Wentz",
    "Kenny Golladay",
    "Von Miller"
]

# Output directory in the Next.js public folder
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "public", "players")

def sanitize_filename(name):
    return name.lower().replace(" ", "_").replace("'", "") + ".jpg"

def download_image(url, filepath):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Verify it's a valid image
        img = Image.open(BytesIO(response.content))
        
        # We want wide/landscape images for backgrounds
        width, height = img.size
        target_ratio = 16 / 9
        
        # Convert to RGB if necessary (e.g., PNG with alpha)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Optional: Crop to 16:9 to ensure it fits nicely as a background
        current_ratio = width / height
        if current_ratio > target_ratio:
            # Image is too wide
            new_width = int(target_ratio * height)
            offset = (width - new_width) / 2
            img = img.crop((offset, 0, width - offset, height))
        elif current_ratio < target_ratio:
            # Image is too tall
            new_height = int(width / target_ratio)
            offset = (height - new_height) / 2
            img = img.crop((0, offset, width, height - offset))
            
        # Resize to save space
        img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
        
        img.save(filepath, "JPEG", quality=85)
        return True
    except Exception as e:
        print(f"Error downloading or processing image {url}: {e}")
        return False

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with DDGS() as ddgs:
        for player in PLAYERS:
            print(f"Searching for {player}...")
            # Query for iconic action shots in high quality
            query = f"{player} nfl action photo high resolution wallpaper"
            
            try:
                # Get top 5 images to try downloading
                results = list(ddgs.images(
                    query,
                    region="wt-wt",
                    safesearch="moderate",
                    size="Wallpaper",
                    layout="Wide",
                    max_results=5
                ))
                
                if not results:
                    print(f"No results found for {player}")
                    continue
                    
                filename = sanitize_filename(player)
                filepath = os.path.join(OUTPUT_DIR, filename)
                
                # Try downloading images until one succeeds
                success = False
                for result in results:
                    image_url = result.get("image")
                    print(f"Attempting to download: {image_url}")
                    if download_image(image_url, filepath):
                        print(f"Successfully saved {filename}")
                        success = True
                        break
                    time.sleep(1) # Be nice to the servers
                    
                if not success:
                    print(f"Failed to download any images for {player}")
                    
            except Exception as e:
                print(f"Search failed for {player}: {e}")
                
            time.sleep(2) # Prevent rate limiting from DDG

if __name__ == "__main__":
    main()
