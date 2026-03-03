import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def extract_review_data(review_elem) -> Dict:
    """Extract review/tweak data from a review element. (Consistent with v2)"""
    review_data = {}

    # Try to extract review text
    text_selectors = [
        ("div", {"class": "ugc-review__text"}),
        ("div", {"class": re.compile(r"ugc-review__text")}),
        ("div", {"class": re.compile(r"recipe-review__text")}),
        ("div", {"class": re.compile(r"ReviewText")}),
        ("div", {"class": re.compile(r"ugc-review-body")}),
        ("p", {"class": re.compile(r"review")}),
    ]

    for tag, attrs in text_selectors:
        text_elem = review_elem.find(tag, attrs)
        if text_elem:
            review_text = text_elem.get_text(strip=True)
            if review_text:
                review_data["text"] = review_text
                break

    # Try to extract rating
    rating_selectors = [
        ("div", {"class": "ugc-review__rating"}),
        ("div", {"class": re.compile(r"ugc-review__rating")}),
        ("span", {"class": re.compile(r"rating-stars")}),
        ("div", {"class": re.compile(r"RatingStar")}),
        ("span", {"aria-label": re.compile(r"rated \d+ out of 5")}),
    ]

    for tag, attrs in rating_selectors:
        rating_elem = review_elem.find(tag, attrs)
        if rating_elem:
            aria_label = rating_elem.get("aria-label", "")
            rating_match = re.search(r"rated (\d+)", aria_label)
            if rating_match:
                review_data["rating"] = int(rating_match.group(1))
            else:
                stars = rating_elem.find_all("svg", {"class": "icon-star"})
                if stars:
                    review_data["rating"] = len(stars)
            break

    # Try to extract username
    user_selectors = [
        ("span", {"class": re.compile(r"recipe-review__author")}),
        ("span", {"class": re.compile(r"reviewer-name")}),
        ("a", {"class": re.compile(r"cook-name")}),
    ]

    for tag, attrs in user_selectors:
        user_elem = review_elem.find(tag, attrs)
        if user_elem:
            review_data["username"] = user_elem.get_text(strip=True)
            break

    # Look for modifications/tweaks in review text
    if review_data.get("text"):
        tweak_patterns = [
            r"I (added|used|substituted|replaced|made with|changed)",
            r"(instead of|rather than|in place of)",
            r"(next time|will make again|definitely make)",
            r"(doubled|tripled|halved|increased|decreased)",
            r"(more|less|extra) ([\w\s]+)",
        ]

        for pattern in tweak_patterns:
            if re.search(pattern, review_data["text"], re.IGNORECASE):
                review_data["has_modification"] = True
                break

    return review_data


def extract_recipe_from_json_ld(data: Any) -> Optional[Dict]:
    """Extract recipe data from various JSON-LD formats."""
    if isinstance(data, dict):
        types = data.get("@type", [])
        if isinstance(types, list) and "Recipe" in types:
            return data
        elif types == "Recipe":
            return data
    elif isinstance(data, list):
        for item in data:
            recipe = extract_recipe_from_json_ld(item)
            if recipe:
                return recipe
    return None


def scrape_allrecipes_with_playwright(url: str) -> Optional[Dict]:
    """
    Scrape recipe data from an AllRecipes URL using Playwright for rendering.
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            # Use a modern user-agent
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            print(f"Navigating to: {url}")
            # Increase timeout and wait until network is idle
            page.goto(url, wait_until="load", timeout=60000)
            
            # Wait specifically for the carousel if it exists, but don't fail if it doesn't
            try:
                page.wait_for_selector(".mm-recipes-ugc-threaded-carousel__cards", timeout=10000)
                print("✓ Found featured tweaks carousel")
            except:
                print("⚠ Carousel selector not found within timeout (might not exist for this recipe)")

            # Scroll down to ensure lazy-loaded reviews trigger
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(2000)

            content = page.content()
            soup = BeautifulSoup(content, "html.parser")
            browser.close()

            # --- Extraction Logic (identical to v2 but using rendered soup) ---
            recipe_data = {
                "url": url,
                "scraped_at": datetime.now().isoformat(),
            }

            # ID extraction
            url_parts = url.split("/")
            for i, part in enumerate(url_parts):
                if part == "recipe" and i + 1 < len(url_parts):
                    recipe_data["recipe_id"] = url_parts[i + 1]
                    break

            # Title extraction
            title_element = soup.find("h1")
            if title_element:
                recipe_data["title"] = title_element.text.strip()

            # Structured Data (JSON-LD)
            json_ld_scripts = soup.find_all("script", type="application/ld+json")
            recipe_found = None
            for json_ld in json_ld_scripts:
                try:
                    structured_data = json.loads(json_ld.string)
                    recipe_found = extract_recipe_from_json_ld(structured_data)
                    if recipe_found:
                        break
                except:
                    continue

            if recipe_found:
                recipe_data["title"] = recipe_found.get("name", recipe_data.get("title", ""))
                recipe_data["description"] = recipe_found.get("description", "")
                if "aggregateRating" in recipe_found:
                    recipe_data["rating"] = {
                        "value": recipe_found["aggregateRating"].get("ratingValue"),
                        "count": recipe_found["aggregateRating"].get("ratingCount"),
                    }
                recipe_data["ingredients"] = recipe_found.get("recipeIngredient", [])
                instructions = recipe_found.get("recipeInstructions", [])
                if instructions:
                    recipe_data["instructions"] = [
                        inst.get("text", inst.get("name", "")) if isinstance(inst, dict) else str(inst)
                        for inst in instructions
                    ]
                recipe_data["servings"] = str(recipe_found.get("recipeYield", [""])[0]) if isinstance(recipe_found.get("recipeYield"), list) else str(recipe_found.get("recipeYield", ""))

            # --- FEATURED TWEAKS (CAROUSEL) ---
            recipe_data["featured_tweaks"] = []
            carousel_cards = soup.find_all("div", {"class": "mm-recipes-ugc-threaded-carousel__cards"})
            
            if carousel_cards:
                print("\n" + "="*80)
                print(f"DEBUG: FOUND FEATURED TWEAKS CAROUSEL FOR: {recipe_data.get('title')}")
                print("="*80)
                potential_tweaks = []
                for i, card in enumerate(carousel_cards):
                    # Target individual cards within carousel
                    text_divs = card.find_all("div", {"class": "mm-recipes-ugc-shared-item-card__text"})
                    for text_div in text_divs:
                        text = text_div.get_text(strip=True)

                        tweak_data = {
                            "text": text,
                            "is_featured": True
                        }

                        potential_tweaks.append(tweak_data)
                
                recipe_data["featured_tweaks"] = potential_tweaks
                print("="*80 + "\n")

            # --- NORMAL REVIEWS ---
            recipe_data["reviews"] = []
            review_selectors = [
                ("div", {"class": "ugc-review"}),
                ("div", {"class": re.compile(r"ReviewCard__container")}),
            ]
            reviews_found = []
            for tag, attrs in review_selectors:
                reviews_found = soup.find_all(tag, attrs, limit=50)
                if reviews_found: break

            for review_elem in reviews_found[:30]:
                review_data = extract_review_data(review_elem)
                if review_data and review_data.get("text"):
                    recipe_data["reviews"].append(review_data)

            return recipe_data

        except Exception as e:
            print(f"Error scraping {url}: {str(e)}")
            return None


def save_recipe_data(recipe_data: Dict) -> str:
    """Save recipe data to JSON (Consistent with v2)"""
    recipe_id = recipe_data.get("recipe_id", "unknown")
    title_slug = re.sub(r"[^a-z0-9]+", "-", recipe_data.get("title", "").lower())[:50]
    filename = f"data/recipe_{recipe_id}_{title_slug}.json"
    
    import os
    os.makedirs("data", exist_ok=True)
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(recipe_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved rendered recipe data to {filename}")
    return filename


def scrape_sitemap_recipes(limit: int = 50) -> List[str]:
    """
    Scrape recipe URLs from AllRecipes sitemap. (Consistent with v2)
    """
    sitemap_url = "https://www.allrecipes.com/sitemap_1.xml"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(sitemap_url, headers=headers)
        response.raise_for_status()

        # Parse XML to find recipe URLs
        soup = BeautifulSoup(response.content, "xml")
        urls = []

        for loc in soup.find_all("loc"):
            url = loc.text
            if "/recipe/" in url and url not in urls:
                urls.append(url)
                if len(urls) >= limit:
                    break

        return urls

    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        # Fallback to hardcoded popular recipes
        return [
            "https://www.allrecipes.com/recipe/10813/best-chocolate-chip-cookies/",
            "https://www.allrecipes.com/recipe/11679/homemade-mac-and-cheese/",
            "https://www.allrecipes.com/recipe/23600/worlds-best-lasagna/",
            "https://www.allrecipes.com/recipe/24059/creamy-rice-pudding/",
            "https://www.allrecipes.com/recipe/20144/banana-banana-bread/",
        ][:limit]


def main():
    """Main function for v3 playwright scraper with multi-recipe support."""
    import os
    os.makedirs("data", exist_ok=True)

    # Test with a single recipe first
    test_url = "https://www.allrecipes.com/recipe/10813/best-chocolate-chip-cookies/"
    
    print("=" * 60)
    print("STARTING PLAYWRIGHT SCRAPER (V3) - MULTI-RECIPE MODE")
    print("=" * 60)
    
    print(f"\n[TEST] Scraping: {test_url}")
    recipe_data = scrape_allrecipes_with_playwright(test_url)
    if recipe_data:
        save_recipe_data(recipe_data)
        print("✓ Success")
    else:
        print("✗ Failed")

    # Now get more recipes from sitemap
    print("\n" + "=" * 60)
    print("Fetching more recipe URLs from sitemap...")
    
    recipe_urls = scrape_sitemap_recipes(limit=5)
    print(f"Found {len(recipe_urls)} recipe URLs to scrape")

    successful = 0
    for i, url in enumerate(recipe_urls, 1):
        print(f"\n[{i}/{len(recipe_urls)}] Scraping: {url}")
        recipe_data = scrape_allrecipes_with_playwright(url)
        if recipe_data:
            save_recipe_data(recipe_data)
            successful += 1
            print("  ✓ Success")
        else:
            print("  ✗ Failed")

    print("\n" + "=" * 60)
    print(f"Summary: Successfully scraped {successful + (1 if 'recipe_data' in locals() and recipe_data else 0)}/{len(recipe_urls) + 1} recipes")

if __name__ == "__main__":
    main()
