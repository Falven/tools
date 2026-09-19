"""Deterministic vegetarian dinner planning and grocery-list generation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

__all__ = ["make_vegetarian_weeknight_grocery_list"]


_RECIPES: list[dict[str, Any]] = [
    {
        "name": "Peanut tofu and broccoli rice bowls",
        "diet": "vegan",
        "minutes": 25,
        "protein_g": 31,
        "tags": {"soy", "peanut", "gluten"},
        "ingredients": [
            ("extra-firm tofu", 14, "oz", "Refrigerated"),
            ("broccoli florets", 12, "oz", "Produce"),
            ("red bell pepper", 1, "each", "Produce"),
            ("brown rice, dry", 0.75, "cup", "Grains & bakery"),
            ("peanut butter", 3, "tbsp", "Pantry"),
            ("low-sodium soy sauce", 2, "tbsp", "Pantry"),
            ("lime", 1, "each", "Produce"),
            ("garlic", 2, "clove", "Produce"),
            ("neutral cooking oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Start the rice.",
            "Brown cubed tofu in oil, then add broccoli and sliced pepper.",
            "Stir peanut butter, soy sauce, lime juice, garlic, and a splash of water together; add to the pan and serve over rice.",
        ],
    },
    {
        "name": "Tempeh and black bean fajita bowls",
        "diet": "vegan",
        "minutes": 30,
        "protein_g": 32,
        "tags": {"soy"},
        "ingredients": [
            ("tempeh", 8, "oz", "Refrigerated"),
            ("black beans", 1, "15-oz can", "Canned goods"),
            ("bell peppers", 2, "each", "Produce"),
            ("yellow onion", 1, "each", "Produce"),
            ("brown rice, dry", 0.75, "cup", "Grains & bakery"),
            ("salsa", 0.5, "cup", "Condiments"),
            ("avocado", 1, "each", "Produce"),
            ("lime", 1, "each", "Produce"),
            ("chili powder", 2, "tsp", "Spices"),
            ("ground cumin", 1, "tsp", "Spices"),
            ("neutral cooking oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Start the rice.",
            "Sauté sliced tempeh, peppers, and onion with oil, chili powder, and cumin.",
            "Serve with warmed black beans, salsa, avocado, and lime over rice.",
        ],
    },
    {
        "name": "Lentil pasta with white beans and spinach",
        "diet": "vegan",
        "minutes": 20,
        "protein_g": 34,
        "tags": {"legumes"},
        "ingredients": [
            ("red lentil pasta", 8, "oz", "Grains & bakery"),
            ("cannellini beans", 1, "15-oz can", "Canned goods"),
            ("baby spinach", 5, "oz", "Produce"),
            ("marinara sauce", 2, "cup", "Canned goods"),
            ("nutritional yeast", 3, "tbsp", "Pantry"),
            ("garlic", 2, "clove", "Produce"),
            ("olive oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Boil the lentil pasta.",
            "Warm olive oil and garlic; add marinara, drained beans, and spinach.",
            "Toss with pasta and nutritional yeast.",
        ],
    },
    {
        "name": "Chickpea and edamame coconut curry",
        "diet": "vegan",
        "minutes": 30,
        "protein_g": 27,
        "tags": {"soy", "legumes", "coconut"},
        "ingredients": [
            ("chickpeas", 1, "15-oz can", "Canned goods"),
            ("shelled frozen edamame", 12, "oz", "Frozen"),
            ("light coconut milk", 1, "14-oz can", "Canned goods"),
            ("diced tomatoes", 1, "15-oz can", "Canned goods"),
            ("baby spinach", 5, "oz", "Produce"),
            ("brown rice, dry", 0.75, "cup", "Grains & bakery"),
            ("yellow onion", 1, "each", "Produce"),
            ("curry powder", 1.5, "tbsp", "Spices"),
            ("neutral cooking oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Start the rice.",
            "Sauté chopped onion with curry powder.",
            "Simmer chickpeas, edamame, tomatoes, and coconut milk for 10 minutes; wilt in spinach and serve over rice.",
        ],
    },
    {
        "name": "Black bean quinoa taco bowls",
        "diet": "vegan",
        "minutes": 25,
        "protein_g": 26,
        "tags": {"legumes"},
        "ingredients": [
            ("black beans", 1.5, "15-oz can", "Canned goods"),
            ("quinoa, dry", 0.75, "cup", "Grains & bakery"),
            ("frozen corn", 1, "cup", "Frozen"),
            ("romaine lettuce", 1, "head", "Produce"),
            ("salsa", 0.75, "cup", "Condiments"),
            ("avocado", 1, "each", "Produce"),
            ("lime", 1, "each", "Produce"),
            ("pumpkin seeds", 0.25, "cup", "Pantry"),
            ("chili powder", 2, "tsp", "Spices"),
            ("ground cumin", 1, "tsp", "Spices"),
        ],
        "steps": [
            "Cook quinoa.",
            "Warm beans and corn with chili powder and cumin.",
            "Build bowls with lettuce, quinoa, bean mixture, salsa, avocado, pumpkin seeds, and lime.",
        ],
    },
    {
        "name": "Sesame edamame soba bowls",
        "diet": "vegan",
        "minutes": 20,
        "protein_g": 30,
        "tags": {"soy", "sesame", "gluten"},
        "ingredients": [
            ("soba noodles", 8, "oz", "Grains & bakery"),
            ("shelled frozen edamame", 12, "oz", "Frozen"),
            ("shredded cabbage", 8, "oz", "Produce"),
            ("carrots", 2, "each", "Produce"),
            ("low-sodium soy sauce", 2, "tbsp", "Pantry"),
            ("tahini", 2, "tbsp", "Pantry"),
            ("rice vinegar", 2, "tbsp", "Pantry"),
            ("sesame oil", 2, "tsp", "Pantry"),
            ("lime", 1, "each", "Produce"),
        ],
        "steps": [
            "Boil soba, adding edamame for the final 3 minutes; drain.",
            "Whisk soy sauce, tahini, vinegar, sesame oil, lime, and a little water.",
            "Toss noodles and edamame with cabbage, grated carrots, and dressing.",
        ],
    },
    {
        "name": "Red lentil dal with peas and whole-grain flatbread",
        "diet": "vegan",
        "minutes": 30,
        "protein_g": 25,
        "tags": {"legumes", "gluten"},
        "ingredients": [
            ("red lentils, dry", 1, "cup", "Pantry"),
            ("frozen green peas", 1.5, "cup", "Frozen"),
            ("diced tomatoes", 1, "15-oz can", "Canned goods"),
            ("light coconut milk", 0.5, "14-oz can", "Canned goods"),
            ("whole-grain flatbread", 2, "each", "Grains & bakery"),
            ("yellow onion", 1, "each", "Produce"),
            ("garlic", 2, "clove", "Produce"),
            ("curry powder", 1.5, "tbsp", "Spices"),
            ("neutral cooking oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Sauté onion and garlic with curry powder.",
            "Add lentils, tomatoes, coconut milk, and 2 cups water; simmer until tender.",
            "Stir in peas and serve with warmed flatbread.",
        ],
    },
    {
        "name": "Chickpea quinoa spinach skillet",
        "diet": "vegan",
        "minutes": 25,
        "protein_g": 24,
        "tags": {"legumes"},
        "ingredients": [
            ("chickpeas", 1.5, "15-oz can", "Canned goods"),
            ("quinoa, dry", 0.75, "cup", "Grains & bakery"),
            ("baby spinach", 5, "oz", "Produce"),
            ("cherry tomatoes", 1, "pint", "Produce"),
            ("vegetable broth", 1.5, "cup", "Canned goods"),
            ("pumpkin seeds", 0.25, "cup", "Pantry"),
            ("lemon", 1, "each", "Produce"),
            ("garlic", 2, "clove", "Produce"),
            ("olive oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Sauté garlic and halved tomatoes in olive oil.",
            "Add quinoa, broth, and drained chickpeas; cover and simmer until quinoa is tender.",
            "Wilt in spinach and finish with lemon and pumpkin seeds.",
        ],
    },
    {
        "name": "Cottage cheese pesto pasta with peas",
        "diet": "lacto_ovo",
        "minutes": 20,
        "protein_g": 35,
        "tags": {"dairy", "gluten"},
        "ingredients": [
            ("whole-wheat pasta", 8, "oz", "Grains & bakery"),
            ("cottage cheese", 1.5, "cup", "Refrigerated"),
            ("frozen green peas", 1.5, "cup", "Frozen"),
            ("basil pesto", 0.25, "cup", "Condiments"),
            ("baby spinach", 5, "oz", "Produce"),
            ("lemon", 1, "each", "Produce"),
        ],
        "steps": [
            "Boil pasta, adding peas for the final 3 minutes.",
            "Blend or stir cottage cheese with pesto, lemon, and a splash of pasta water.",
            "Toss off heat with drained pasta and spinach.",
        ],
    },
    {
        "name": "Egg and black bean quesadillas",
        "diet": "lacto_ovo",
        "minutes": 20,
        "protein_g": 30,
        "tags": {"dairy", "egg", "gluten", "legumes"},
        "ingredients": [
            ("large eggs", 6, "each", "Refrigerated"),
            ("black beans", 1, "15-oz can", "Canned goods"),
            ("whole-wheat tortillas", 4, "each", "Grains & bakery"),
            ("shredded cheddar cheese", 4, "oz", "Refrigerated"),
            ("baby spinach", 3, "oz", "Produce"),
            ("salsa", 0.75, "cup", "Condiments"),
            ("avocado", 1, "each", "Produce"),
            ("neutral cooking oil", 2, "tsp", "Pantry"),
        ],
        "steps": [
            "Soft-scramble the eggs with spinach.",
            "Fill tortillas with eggs, drained beans, and cheese.",
            "Toast in a skillet and serve with salsa and avocado.",
        ],
    },
    {
        "name": "Lentil shakshuka with eggs and feta",
        "diet": "lacto_ovo",
        "minutes": 30,
        "protein_g": 28,
        "tags": {"dairy", "egg", "legumes", "gluten"},
        "ingredients": [
            ("large eggs", 4, "each", "Refrigerated"),
            ("cooked lentils", 1.5, "cup", "Canned goods"),
            ("crushed tomatoes", 1, "28-oz can", "Canned goods"),
            ("feta cheese", 3, "oz", "Refrigerated"),
            ("whole-grain pita", 2, "each", "Grains & bakery"),
            ("red bell pepper", 1, "each", "Produce"),
            ("yellow onion", 1, "each", "Produce"),
            ("garlic", 2, "clove", "Produce"),
            ("smoked paprika", 1, "tsp", "Spices"),
            ("ground cumin", 1, "tsp", "Spices"),
            ("olive oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Sauté pepper, onion, garlic, paprika, and cumin.",
            "Add tomatoes and lentils; simmer briefly, then make wells and crack in eggs.",
            "Cover until eggs set; top with feta and serve with pita.",
        ],
    },
    {
        "name": "Greek yogurt chickpea salad wraps",
        "diet": "lacto_ovo",
        "minutes": 15,
        "protein_g": 25,
        "tags": {"dairy", "gluten", "legumes"},
        "ingredients": [
            ("chickpeas", 1.5, "15-oz can", "Canned goods"),
            ("plain Greek yogurt", 1, "cup", "Refrigerated"),
            ("whole-wheat tortillas", 4, "each", "Grains & bakery"),
            ("celery", 3, "stalk", "Produce"),
            ("grapes", 1, "cup", "Produce"),
            ("baby spinach", 3, "oz", "Produce"),
            ("pumpkin seeds", 0.25, "cup", "Pantry"),
            ("lemon", 1, "each", "Produce"),
            ("Dijon mustard", 1, "tbsp", "Condiments"),
        ],
        "steps": [
            "Mash chickpeas roughly.",
            "Mix with yogurt, chopped celery and grapes, pumpkin seeds, lemon, and mustard.",
            "Wrap with spinach in tortillas.",
        ],
    },
    {
        "name": "Paneer and green pea tomato skillet",
        "diet": "lacto_ovo",
        "minutes": 30,
        "protein_g": 31,
        "tags": {"dairy", "gluten"},
        "ingredients": [
            ("paneer", 12, "oz", "Refrigerated"),
            ("frozen green peas", 2, "cup", "Frozen"),
            ("crushed tomatoes", 1, "28-oz can", "Canned goods"),
            ("whole-grain flatbread", 2, "each", "Grains & bakery"),
            ("yellow onion", 1, "each", "Produce"),
            ("garlic", 2, "clove", "Produce"),
            ("plain Greek yogurt", 0.5, "cup", "Refrigerated"),
            ("curry powder", 1.5, "tbsp", "Spices"),
            ("neutral cooking oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Brown paneer cubes and set aside.",
            "Sauté onion, garlic, and curry powder; add tomatoes and peas and simmer.",
            "Return paneer to the pan; serve with yogurt and flatbread.",
        ],
    },
    {
        "name": "White bean, kale, and ricotta toast skillet",
        "diet": "lacto_ovo",
        "minutes": 20,
        "protein_g": 27,
        "tags": {"dairy", "gluten", "legumes"},
        "ingredients": [
            ("cannellini beans", 2, "15-oz can", "Canned goods"),
            ("ricotta cheese", 1, "cup", "Refrigerated"),
            ("whole-grain bread", 4, "slice", "Grains & bakery"),
            ("chopped kale", 6, "oz", "Produce"),
            ("cherry tomatoes", 1, "pint", "Produce"),
            ("garlic", 2, "clove", "Produce"),
            ("lemon", 1, "each", "Produce"),
            ("olive oil", 1, "tbsp", "Pantry"),
        ],
        "steps": [
            "Toast the bread.",
            "Sauté garlic and tomatoes, then add drained beans and kale until hot and wilted.",
            "Spread toast with ricotta, top with the bean skillet, and finish with lemon.",
        ],
    },
]


_ALIASES = {
    "eggs": "egg",
    "peanuts": "peanut",
    "soybeans": "soy",
    "sesame seeds": "sesame",
    "milk": "dairy",
    "cheese": "dairy",
    "yogurt": "dairy",
    "wheat": "gluten",
}


def _normalized_terms(values: list[str] | None) -> set[str]:
    terms: set[str] = set()
    for value in values or []:
        cleaned = " ".join(value.lower().replace("-", " ").split())
        terms.add(_ALIASES.get(cleaned, cleaned))
    return terms


def _matches_exclusion(recipe: dict[str, Any], excluded: set[str]) -> bool:
    tags = {str(tag).lower() for tag in recipe["tags"]}
    ingredient_names = [str(item[0]).lower().replace("-", " ") for item in recipe["ingredients"]]
    for term in excluded:
        if term in tags:
            return True
        if any(term in name or name in term for name in ingredient_names):
            return True
    return False


def _is_in_pantry(ingredient_name: str, pantry: set[str]) -> bool:
    name = ingredient_name.lower().replace("-", " ")
    return any(term in name or name in term for term in pantry)


def _rounded(value: float) -> int | float:
    rounded = round(value, 2)
    return int(rounded) if rounded.is_integer() else rounded


def make_vegetarian_weeknight_grocery_list(
    nights: int = 5,
    servings_per_meal: int = 2,
    diet: Literal["lacto_ovo", "vegan"] = "lacto_ovo",
    max_cook_minutes: int = 30,
    min_protein_g_per_serving: int = 25,
    excluded_ingredients: list[str] | None = None,
    pantry_items: list[str] | None = None,
) -> dict[str, Any]:
    """Create an easy high-protein vegetarian weeknight dinner plan and aggregated grocery list.

    Choose 1-7 nights and 1-8 servings per dinner. ``diet`` may be ``lacto_ovo``
    (which can include dairy, eggs, and vegan meals) or ``vegan``. Recipes are
    constrained by ``max_cook_minutes`` (15-45) and ranked around the requested
    ``min_protein_g_per_serving`` (15-40). Put allergies, dislikes, or broad
    exclusions such as ``soy``, ``peanut``, ``sesame``, ``gluten``, ``dairy``,
    ``egg``, or an ingredient name in ``excluded_ingredients``. Put ingredients
    already on hand in ``pantry_items`` to omit matching items from the shopping
    list.

    Returns the selected dinners with scaled ingredients, concise cooking steps,
    estimated protein per serving, and a category-grouped consolidated shopping
    list. Quantities and protein are planning estimates rather than package-size
    or medical nutrition calculations; labels vary, and substring matching means
    callers should review the result for severe allergies. The function has no
    side effects and does not order groceries.
    """
    if not 1 <= nights <= 7:
        raise ValueError("nights must be between 1 and 7")
    if not 1 <= servings_per_meal <= 8:
        raise ValueError("servings_per_meal must be between 1 and 8")
    if not 15 <= max_cook_minutes <= 45:
        raise ValueError("max_cook_minutes must be between 15 and 45")
    if not 15 <= min_protein_g_per_serving <= 40:
        raise ValueError("min_protein_g_per_serving must be between 15 and 40")

    excluded = _normalized_terms(excluded_ingredients)
    pantry = _normalized_terms(pantry_items)
    allowed_diets = {"vegan"} if diet == "vegan" else {"vegan", "lacto_ovo"}

    eligible = [
        recipe
        for recipe in _RECIPES
        if recipe["diet"] in allowed_diets
        and recipe["minutes"] <= max_cook_minutes
        and not _matches_exclusion(recipe, excluded)
    ]
    eligible.sort(
        key=lambda recipe: (
            recipe["protein_g"] < min_protein_g_per_serving,
            abs(recipe["protein_g"] - min_protein_g_per_serving),
            recipe["minutes"],
            recipe["name"],
        )
    )

    if not eligible:
        return {
            "status": "no_matching_meals",
            "message": "No recipes match all constraints. Increase max_cook_minutes or relax exclusions.",
            "constraints": {
                "diet": diet,
                "max_cook_minutes": max_cook_minutes,
                "excluded_ingredients": sorted(excluded),
            },
            "meal_plan": [],
            "shopping_list": {},
        }

    selected = eligible[:nights]
    warnings: list[str] = []
    if len(selected) < nights:
        warnings.append(
            f"Only {len(selected)} unique recipes matched; the plan contains fewer than {nights} nights."
        )
    below_target = [recipe["name"] for recipe in selected if recipe["protein_g"] < min_protein_g_per_serving]
    if below_target:
        warnings.append(
            "Some meals fall below the requested protein target: " + ", ".join(below_target) + "."
        )

    scale = servings_per_meal / 2
    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    meals: list[dict[str, Any]] = []
    omitted: list[str] = []

    for night, recipe in enumerate(selected, start=1):
        scaled_ingredients: list[dict[str, Any]] = []
        for name, quantity, unit, category in recipe["ingredients"]:
            scaled_quantity = float(quantity) * scale
            scaled_ingredients.append(
                {"item": name, "quantity": _rounded(scaled_quantity), "unit": unit}
            )
            if _is_in_pantry(name, pantry):
                omitted.append(name)
            else:
                totals[(category, name, unit)] += scaled_quantity
        meals.append(
            {
                "night": night,
                "meal": recipe["name"],
                "diet": recipe["diet"],
                "cook_minutes": recipe["minutes"],
                "estimated_protein_g_per_serving": recipe["protein_g"],
                "servings": servings_per_meal,
                "ingredients": scaled_ingredients,
                "steps": recipe["steps"],
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (category, name, unit), quantity in sorted(
        totals.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        grouped[category].append(
            {"item": name, "quantity": _rounded(quantity), "unit": unit}
        )

    return {
        "status": "ok",
        "summary": {
            "planned_nights": len(meals),
            "servings_per_meal": servings_per_meal,
            "diet": diet,
            "protein_target_g_per_serving": min_protein_g_per_serving,
            "protein_range_in_plan_g": [
                min(meal["estimated_protein_g_per_serving"] for meal in meals),
                max(meal["estimated_protein_g_per_serving"] for meal in meals),
            ],
            "maximum_cook_time_in_plan_minutes": max(meal["cook_minutes"] for meal in meals),
        },
        "meal_plan": meals,
        "shopping_list": dict(grouped),
        "pantry_items_omitted": sorted(set(omitted)),
        "warnings": warnings,
        "nutrition_note": (
            "Protein values are approximate per-serving planning estimates based on typical "
            "ingredient data; verify product labels and consult a qualified clinician for "
            "individual medical nutrition needs."
        ),
        "research_basis": [
            {
                "source": "USDA FoodData Central",
                "use": "Reference source for typical food nutrient composition.",
                "url": "https://fdc.nal.usda.gov/",
            },
            {
                "source": "Dietary Guidelines for Americans, 2025-2030",
                "use": "Supports variety among plant protein foods including beans, peas, lentils, nuts, seeds, and soy.",
                "url": "https://www.dietaryguidelines.gov/",
            },
            {
                "source": "USDA National Agricultural Library Vegetarian Nutrition",
                "use": "Background guidance for vegetarian and vegan dietary patterns.",
                "url": "https://www.nal.usda.gov/human-nutrition-and-food-safety/vegetarian-nutrition",
            },
        ],
    }
