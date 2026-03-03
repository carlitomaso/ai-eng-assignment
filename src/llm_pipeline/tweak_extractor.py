"""
Step 1: Tweak Extraction & Parsing

This module extracts structured modifications from tweak text using LLM processing.
It converts natural language descriptions of recipe changes into structured
ModificationObject instances.
"""

import json
import os
from typing import Optional

from loguru import logger
from openai import OpenAI
from pydantic import ValidationError

from .models import ModificationObject, Recipe, Tweak
from .prompts import build_simple_prompt


class TweakExtractor:
    """Extracts structured modifications from tweak text using LLM processing."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        """
        Initialize the TweakExtractor.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: OpenAI model to use for extraction
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        logger.info(f"Initialized TweakExtractor with model: {model}")

    def extract_modification(
        self,
        tweak: Tweak,
        recipe: Recipe,
        max_retries: int = 2,
    ) -> Optional[ModificationObject]:
        """
        Extract a structured modification from a tweak.

        Args:
            tweak: Tweak object containing modification text
            recipe: Original recipe being modified
            max_retries: Number of retry attempts if parsing fails

        Returns:
            ModificationObject if extraction successful, None otherwise
        """
        if not tweak.has_modification:
            logger.warning("Tweak has no modification flag set")
            return None

        # Build the prompt - use simple prompt to avoid format string issues
        prompt = build_simple_prompt(
            tweak.text, recipe.title, recipe.ingredients, recipe.instructions
        )

        logger.debug(
            "Extracting modification from tweak: {}...".format(tweak.text[:100])
        )

        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,  # Low temperature for consistent extractions
                    max_tokens=1000,
                )

                raw_output = response.choices[0].message.content
                logger.debug(f"LLM raw output: {raw_output}")

                # Check if we got a response
                if not raw_output:
                    logger.warning(f"Attempt {attempt + 1}: Empty response from LLM")
                    continue

                # Parse and validate the JSON response
                modification_data = json.loads(raw_output)
                modification = ModificationObject(**modification_data)

                logger.info(
                    f"Successfully extracted {modification.modification_type} "
                    f"modification with {len(modification.edits)} edits"
                )
                return modification

            except json.JSONDecodeError as e:
                logger.warning(f"Attempt {attempt + 1}: Failed to parse JSON: {e}")
                if attempt == max_retries:
                    logger.error(f"Max retries reached. Raw output: {raw_output}")

            except ValidationError as e:
                logger.warning(f"Attempt {attempt + 1}: Validation error: {e}")
                if attempt == max_retries:
                    logger.error(
                        f"Max retries reached. Invalid data: {modification_data}"
                    )

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Unexpected error: {e}")
                if attempt == max_retries:
                    return None

        return None

    def extract_single_modification(
        self, tweaks: list[Tweak], recipe: Recipe
    ) -> tuple[ModificationObject, Tweak] | tuple[None, None]:
        """
        Extract modification from a single randomly selected tweak.

        Args:
            tweaks: List of tweaks to choose from
            recipe: Original recipe being modified

        Returns:
            Tuple of (ModificationObject, source_Tweak) if successful, (None, None) otherwise
        """
        import random

        # Filter to tweaks with modifications
        modification_tweaks = [t for t in tweaks if t.has_modification]

        if not modification_tweaks:
            logger.warning("No tweaks with modifications found")
            return None, None

        # Select one random tweak
        selected_tweak = random.choice(modification_tweaks)
        logger.info(f"Selected tweak: {selected_tweak.text[:100]}...")

        modification = self.extract_modification(selected_tweak, recipe)
        if modification:
            logger.info("Successfully extracted modification from selected tweak")
            return modification, selected_tweak
        else:
            logger.warning("Failed to extract modification from selected tweak")
            return None, None

    def test_extraction(
        self, tweak_text: str, recipe_data: dict
    ) -> Optional[ModificationObject]:
        """
        Test extraction with raw text and recipe data.

        Args:
            tweak_text: Raw tweak text
            recipe_data: Raw recipe dictionary

        Returns:
            ModificationObject if successful
        """
        tweak = Tweak(text=tweak_text, has_modification=True)
        recipe = Recipe(
            recipe_id=recipe_data.get("recipe_id", "test"),
            title=recipe_data.get("title", "Test Recipe"),
            ingredients=recipe_data.get("ingredients", []),
            instructions=recipe_data.get("instructions", []),
        )

        return self.extract_modification(tweak, recipe)
