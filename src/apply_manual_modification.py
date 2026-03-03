import json
import os
import argparse
import sys
from pathlib import Path
from llm_pipeline.models import (
    Recipe, Review, ModificationObject, 
    EnhancedRecipe, SourceReview
)
from llm_pipeline.recipe_modifier import RecipeModifier
from llm_pipeline.enhanced_recipe_generator import EnhancedRecipeGenerator

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
    parser = argparse.ArgumentParser(description="Apply a manual LLM modification to a recipe.")
    parser.add_argument(
        "--recipe_id", "-r", 
        type=str, 
        help="The ID of the recipe to use (e.g., 10813). If omitted, defaults to the cookie recipe."
    )
    args = parser.parse_args()

    # File paths
    data_dir = Path("../data")
    json_output_path = Path("llm_output.json")
    output_dir = Path("../data/enhanced")
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.recipe_id:
        recipe_path = find_recipe_file(args.recipe_id, data_dir)
        if not recipe_path:
            print(f"Error: No recipe file found for ID '{args.recipe_id}' in {data_dir}")
            sys.exit(1)
    else:
        # Default to the chocolate chip cookie recipe
        recipe_path = data_dir / "recipe_10813_best-chocolate-chip-cookies.json"

    # 1. Check for manual LLM output
    if not json_output_path.exists():
        print(f"Error: {json_output_path} not found.")
        print("Please save the JSON from the browser into a file named 'src/llm_output.json'.")
        return

    # 2. Load the original recipe
    if not recipe_path.exists():
        print(f"Error: Recipe file not found at {recipe_path}")
        sys.exit(1)

    with open(recipe_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recipe = Recipe(
        recipe_id=data.get("recipe_id", "unknown"),
        title=data.get("title", "Unknown Recipe"),
        ingredients=data.get("ingredients", []),
        instructions=data.get("instructions", []),
        description=data.get("description"),
        servings=data.get("servings")
    )

    # Use the same review that generated the prompt (first one with modification)
    reviews_data = [r for r in data.get("reviews", []) if r.get("has_modification")]
    if not reviews_data:
        print(f"Error: No reviews with modifications found in the source recipe '{recipe.title}'.")
        return
    
    source_review_data = reviews_data[0]
    source_review = Review(
        text=source_review_data["text"],
        username=source_review_data.get("username"),
        rating=source_review_data.get("rating"),
        has_modification=True
    )

    # 3. Parse the manual LLM JSON
    try:
        with open(json_output_path, "r", encoding="utf-8") as f:
            modification_data = json.load(f)
        
        modification = ModificationObject(**modification_data)
        print("✓ Successfully parsed manual LLM output.")
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return

    # 4. Apply modifications
    modifier = RecipeModifier()
    modified_recipe, change_records = modifier.apply_modification(recipe, modification)

    # 5. Generate Enhanced Recipe
    generator = EnhancedRecipeGenerator(pipeline_version="manual-1.0.0")
    enhanced_recipe = generator.generate_enhanced_recipe(
        recipe, modified_recipe, modification, source_review, change_records
    )

    # 6. Save result
    output_filename = f"manual_enhanced_{recipe.recipe_id}.json"
    output_path = output_dir / output_filename
    generator.save_enhanced_recipe(enhanced_recipe, str(output_path))

    print("\n" + "="*60)
    print("SUCCESS: Enhanced recipe generated manually!")
    print(f"Recipe: {recipe.title}")
    print(f"Saved to: {output_path}")
    print(f"Total changes made: {len(change_records)}")
    print("="*60)

if __name__ == "__main__":
    main()
