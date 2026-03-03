import json
import os
import argparse
import sys
from pathlib import Path
from llm_pipeline.models import Recipe
from llm_pipeline.prompts import build_simple_prompt

def find_recipe_file(recipe_id: str, data_dir: Path) -> Path:
    """Find a recipe file matching the given ID in the data directory."""
    pattern = f"recipe_{recipe_id}_*.json"
    matches = list(data_dir.glob(pattern))
    
    if not matches:
        # Try exact match if pattern fails
        exact_match = data_dir / f"recipe_{recipe_id}.json"
        if exact_match.exists():
            return exact_match
        return None
    
    # Return the first match (usually only one)
    return matches[0]

def main():
    parser = argparse.ArgumentParser(description="Generate a manual LLM prompt for a recipe.")
    parser.add_argument(
        "--recipe_id", "-r", 
        type=str, 
        help="The ID of the recipe to use (e.g., 10813). If omitted, defaults to the cookie recipe."
    )
    args = parser.parse_args()

    # Base data directory (relative to src/)
    data_dir = Path("../data")
    
    if args.recipe_id:
        recipe_path = find_recipe_file(args.recipe_id, data_dir)
        if not recipe_path:
            print(f"Error: No recipe file found for ID '{args.recipe_id}' in {data_dir}")
            sys.exit(1)
    else:
        # Default to the chocolate chip cookie recipe
        recipe_path = data_dir / "recipe_10813_best-chocolate-chip-cookies.json"

    if not recipe_path.exists():
        print(f"Error: Recipe file not found at {recipe_path}")
        sys.exit(1)

    print(f"Loading recipe from: {recipe_path}")

    with open(recipe_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Parse recipe
    recipe = Recipe(
        recipe_id=data.get("recipe_id", "unknown"),
        title=data.get("title", "Unknown Recipe"),
        ingredients=data.get("ingredients", []),
        instructions=data.get("instructions", [])
    )
    
    # Find reviews with modifications
    reviews = [r for r in data.get("reviews", []) if r.get("has_modification")]
    
    if not reviews:
        print(f"No reviews with modifications found in recipe: {recipe.title}")
        return

    # Select the first review for consistency in manual mode
    selected_review = reviews[0]
    
    # Generate the prompt
    prompt = build_simple_prompt(
        selected_review["text"], 
        recipe.title, 
        recipe.ingredients, 
        recipe.instructions
    )

    print("\n" + "="*80)
    print(f"MANUAL LLM PROMPT FOR: {recipe.title}")
    print("="*80 + "\n")
    print(prompt)
    print("\n" + "="*80)
    print(f"SOURCE REVIEW BY: {selected_review.get('username', 'Unknown')}")
    print("="*80)

if __name__ == "__main__":
    main()
