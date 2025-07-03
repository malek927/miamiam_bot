import json
import random
import re
from gpt4all import GPT4All

class MiamiamBot:
    def __init__(self, menu_path="classified_menu.json", model_path="mistral-7b-instruct-v0.1.Q4_0.gguf"):
        with open(menu_path, 'r', encoding='utf-8') as f:
            self.menu_data = json.load(f)
        self.gpt_model = GPT4All(model_path)
        self.last_suggestion = None
        self.last_preferences = None
        self.session_context = {}

        self.ingredient_aliases = {
            "chiken": "chicken", "ciken": "chicken", "chikn": "chicken", "chikin": "chicken",
            "beaf": "beef", "boef": "beef", "meat": "meat", "meet": "meat", "daging": "meat",
            "egg": "egg", "telur": "egg", "telor": "egg", "telorr": "egg",
            "ikan": "fish", "ikan goreng": "fish",
            "nasi": "rice", "nasilemak": "rice",
            "mie": "noodle", "maggi": "noodle", "nudel": "noodle", "noodl": "noodle",
            "cheez": "cheese", "cheese": "cheese", "cheeze": "cheese", "keju": "cheese",
            "aym": "chicken"
        }

        self.exclusive_tags = [
            {"spicy", "sweet"},
            {"hot", "cold"},
            {"sweet", "salty"},
            {"only drink", "not drink"}
        ]

    def normalize_message(self, message):
        synonyms = {
            "rm": "myr", "ringgit": "myr", "ringitt": "myr", "riggit": "myr", "rigit": "myr",
            "spagetti": "spaghetti", "mie": "noodle", "maggie": "noodle", "mee": "noodle",
            "sambal": "spicy", "rendang": "beef", "telur": "egg"

        }
        for key, val in synonyms.items():
            message = re.sub(rf"\\b{key}\\b", val, message, flags=re.IGNORECASE)
        return message

    def normalize_ingredient(self, word):
        return self.ingredient_aliases.get(word.lower(), word.lower())

    def update_session_context(self, new_preferences):
        for key, value in new_preferences.items():
            if key in ["min_price", "max_price"]:
                self.session_context[key] = value
            elif key.startswith("not ") or key in ["halal", "healthy"]:
                self.session_context[key] = value
            elif key in ["spicy", "sweet", "hot", "cold", "salty"]:
                for group in self.exclusive_tags:
                    if key in group:
                        for t in group:
                            if t != key:
                                self.session_context.pop(t, None)
                        break
                self.session_context[key] = True
            elif key == "ingredients":
                if any(t in self.session_context for t in ["sweet", "dessert"]):
                    self.session_context.pop("ingredients", None)
                else:
                    self.session_context[key] = value

    def is_reset_request(self, message):
        message = message.lower()
        return any(phrase in message for phrase in [
            "reset", "start over", "forget", "clear", "new search", "restart", "begin again"
        ])

    def is_plan_request(self, message):
        message = self.normalize_message(message)

        # Match number of days (e.g., "3 days", "5 meals", etc.)
        match = re.search(r'(?P<days>\d+)\s*(?:days?|day|meals?|meal)\b', message)
        if match:
            return int(match.group('days'))

        # Keywords like "week" or "weekly" imply 7-day plan
        if any(kw in message for kw in ["week", "weekly", "7 day", "seven days"]):
            return 7

        return None

    def generate_meal_plan(self, days, preferences):
        plan_data = []
        total_cost = 0

        matches = self.filter_menu(self.session_context)

        if not matches:
            for day in range(1, days + 1):
                plan_data.append((f"Day {day}", None, None, 0))
            return plan_data, 0

        random.shuffle(matches)

        used_keys = set()
        for day in range(1, days + 1):
            # Pick from unused meals if available
            available = [
                (restaurant, item)
                for restaurant, item in matches
                if (restaurant, item["name"]) not in used_keys
            ]

            if available:
                restaurant, item = random.choice(available)
                used_keys.add((restaurant, item["name"]))
            else:
                restaurant, item = random.choice(matches)

            price = item.get("price", 0)
            if isinstance(price, str):
                try:
                    price = float(price.split("/")[0].strip())
                except:
                    price = 0

            plan_data.append((f"Day {day}", restaurant, item, price))
            total_cost += price

        return plan_data, total_cost

    def format_plan_response(self, plan_data, total_cost, days):
        response = f"📅 {days}-Day Meal Plan\n\n"
        for day, restaurant, item, price in plan_data:
            if restaurant:
                response += f"• {day}: {item['name']} from {restaurant} — RM{price:.2f}\n"
                if item.get('ingredients'):
                    response += f"  Ingredients: {', '.join(item['ingredients'])}\n"
                if item.get('tags'):
                    response += f"  Tags: {', '.join(item['tags'])}\n"
            else:
                response += f"• {day}: No matching meal found\n"
        response += f"\n💰 Total estimated cost: RM{total_cost:.2f}"
        return response

    def parse_user_preferences(self, message):
        message = self.normalize_message(message.lower())
        preferences = {}
        supported_tags = ["halal", "spicy", "sweet", "healthy", "cold", "hot", "after_gym"]
        meal_plan_match = re.search(
            r'\b(?:plan|suggest|recommend|give me|i want|i need|can you (?:plan|suggest|recommend))\s*(?:me|us|meals?|dishes?)?\s*(?:a\s*)?(meal\s*plan\s*(?:of)?\s*)?(?P<count>\d+)\s*(?P<tags>[\w\s]*)',
            message
        )

        if meal_plan_match:
            preferences["meal_plan_count"] = int(meal_plan_match.group("count"))

            # Also try to extract tag-like words after the number: e.g., "3 halal meals"
            tag_part = meal_plan_match.group("tags")
            if tag_part:
                for tag in tag_part.lower().split():
                    tag = tag.strip()
                    if tag in supported_tags:  # self.valid_tags contains 'halal', 'spicy', etc.
                        preferences.setdefault("tags", []).append(tag)

        if "eat" in message:
            preferences["not drink"] = True
        elif "drink" in message:
            preferences["only drink"] = True

        for tag in supported_tags:
            if f"not {tag}" in message:
                preferences[f"not {tag}"] = True
            elif tag in message:
                preferences[tag] = True
        if "vegetarian" in message:
            preferences.update({"not meat": True, "not fish": True})

        if "after gym" in message or "post workout" in message:
            preferences["after_gym"] = True

        if "cheapest" in message or "lowest price" in message or "least expensive" in message:
            preferences["cheapest"] = True

        range_match = re.search(
            r"(?:between|from)\s*(\d+(?:\.\d+)?)\s*(?:rm|myr)?\s*(?:to|and|-)\s*(\d+(?:\.\d+)?)\s*(?:rm|myr)?", message)
        if range_match:
            preferences["min_price"] = float(range_match.group(1))
            preferences["max_price"] = float(range_match.group(2))
        else:
            single_price_match = re.search(
                r"(?:under|less than|maximum|max|have|budget)\s*(?:is\s*)?(\d+(?:\.\d+)?)\s*(?:rm|myr)?", message)
            if single_price_match:
                preferences["max_price"] = float(single_price_match.group(1))
            else:
                fallback_price = re.search(r"(\d+(?:\.\d+)?)\s*(?:rm|myr)", message)
                if fallback_price:
                    preferences["max_price"] = float(fallback_price.group(1))

        ingredient_phrases = re.findall(r"(?:with|including|containing|has|have|want|eat|like|get|need)\\s+(?:some\\s+)?(\\w+)", message)
        ingredients = [self.normalize_ingredient(w) for w in ingredient_phrases if not w.isdigit()]
        if ingredients:
            preferences["ingredients"] = list(set(ingredients))

        return preferences

    def is_food_request(self, message):
        message = message.lower()
        keywords = [
            'halal', 'spicy', 'sweet', 'healthy', 'cold', 'hot',
            'recommend', 'food', 'eat', 'meal', 'dish', 'menu',
            'something to eat', 'want to eat', 'with', 'including',
            'have', 'containing', 'drink','cheapest'
        ]
        ingredient_words = ['meat', 'chicken', 'beef', 'cheese', 'egg', 'rice', 'noodle', 'burger', 'fish']

        # ✅ Correct: only one backslash in raw string
        price_pattern = r"(under|less than|max(?:imum)?|have|budget|from|between)?\s*\d+(?:\.\d+)?\s*(rm|myr|ringgit)?"

        return (
                any(word in message for word in keywords + ingredient_words) or
                bool(re.search(price_pattern, message))
        )

    def is_another_recommendation(self, message):
        return any(word in message.lower() for word in ["something else", "another", "anything else", "more"])

    def filter_menu(self, preferences):
        INGREDIENT_SYNONYMS = {
            "meat": {"beef", "chicken", "lamb", "duck", "turkey"},
            "noodle": {"maggie", "ramen", "instant noodles", "mee"},
            "rice": {"nasi", "fried rice", "steamed rice"},
            "chili": {"sambal", "spicy"},
            "egg": {"telur"},
            "cheese": {"cheddar", "mozzarella"},
        }

        scored_items = []
        positive_tags = set()
        negative_tags = set()

        ingredients_required = set(ing.lower() for ing in preferences.get("ingredients", []))
        expanded_ingredients = set()
        for ing in ingredients_required:
            expanded_ingredients.update(INGREDIENT_SYNONYMS.get(ing, {ing}))

        for key in preferences:
            if key.startswith("not "):
                negative_tags.add(key.replace("not ", ""))
            elif key not in ["max_price", "min_price", "ingredients", "cheapest"]:
                positive_tags.add(key)
        if preferences.get("only drink"):
            positive_tags.add("drink")
        if preferences.get("not drink"):
            negative_tags.add("drink")

        min_price = preferences.get("min_price", 0)
        max_price = preferences.get("max_price", float("inf"))

        for restaurant, meals in self.menu_data.items():
            for item in meals:
                tags = set(tag.lower() for tag in item.get("tags", []))
                item_ingredients = set(i.lower() for i in item.get("ingredients", []))
                item_price = item.get("price") or item.get("Price (MYR)", 999)

                if isinstance(item_price, str):
                    try:
                        item_price = float(item_price.split("/")[0].strip())
                    except:
                        item_price = 999

                if not (min_price <= item_price <= max_price):
                    continue

                if positive_tags and not all(tag in tags for tag in positive_tags):
                    continue

                if ingredients_required and not expanded_ingredients.intersection(item_ingredients):
                    continue

                if positive_tags and not all(tag in tags for tag in positive_tags):
                    continue

                score = sum(1 for tag in positive_tags if tag in tags)
                scored_items.append((score, item_price, restaurant, item))

        if preferences.get("cheapest"):
            scored_items.sort(key=lambda x: (x[1], -x[0]))
        else:
            scored_items.sort(key=lambda x: (-x[0], x[1]))

        return [(r, i) for _, __, r, i in scored_items]

    def generate_response(self, message):
        # 🔄 Reset session if needed
        if self.is_reset_request(message):
            self.session_context = {}
            self.last_suggestion = None
            return "🔄 Preferences reset! Let’s start fresh. What would you like to eat or drink?"

        # ✅ Parse preferences
        preferences = self.parse_user_preferences(message)

        # 📆 Daily plan request (e.g., “plan for 5 days”)
        plan_days = self.is_plan_request(message)
        if plan_days is not None:
            # Exclude drinks and sweet things in meal plans
            preferences["not drink"] = True
            preferences["not sweet"] = True

            self.update_session_context(preferences)
            plan_data, total = self.generate_meal_plan(plan_days, self.session_context)
            return self.format_plan_response(plan_data, total, plan_days)

        # 🍱 Meal count plan (e.g., “plan 3 meals”)
        if "meal_plan_count" in preferences:
            # Exclude drinks and sweet things in meal plans
            preferences["not drink"] = True
            preferences["not sweet"] = True

            self.update_session_context(preferences)
            matches = self.filter_menu(self.session_context)
            meal_plan_count = preferences["meal_plan_count"]
            meals = random.sample(matches, min(meal_plan_count, len(matches)))
            response = "🍽 Here's your meal plan:\n"
            for i, (restaurant, meal) in enumerate(meals, 1):
                response += f"\n🍱 Meal {i}: {meal['name']} from {restaurant} - RM{meal['price']:.2f}"
            return response

        # 🍽️ Handle normal food request
        if self.is_food_request(message):
            self.update_session_context(preferences)
            self.last_preferences = self.session_context.copy()
            matches = self.filter_menu(self.last_preferences)

            if not matches:
                return "😓 Sorry, I couldn’t find anything that matches all your preferences."

            if self.last_preferences.get("cheapest"):
                def parse_price(p):
                    val = p.get("price") or p.get("Price (MYR)", 999)
                    if isinstance(val, str):
                        val = val.split("/")[0].strip()
                    try:
                        return float(val)
                    except:
                        return 999

                matches = sorted(matches, key=lambda x: parse_price(x[1]))
                restaurant, item = matches[0]
            else:
                restaurant, item = random.choice(matches)

            self.last_suggestion = (restaurant, item)
            return f"🍽 How about {item['name']} from {restaurant}?\n💸 RM{item.get('price', '?')}\n🏷 Tags: {', '.join(item.get('tags', []))}"

        # 🔁 Follow-up recommendation
        if self.is_another_recommendation(message):
            if not self.last_suggestion:
                return "🤔 I haven't recommended anything yet! Try asking for food first."
            matches = [m for m in self.filter_menu(self.last_preferences) if m != self.last_suggestion]
            if not matches:
                return "🙈 No more options for now. You’ve seen it all!"
            restaurant, item = random.choice(matches)
            self.last_suggestion = (restaurant, item)
            return f"🍽 Here's another idea: {item['name']} from {restaurant}!\n💸 RM{item.get('price', '?')}\n🏷 {', '.join(item.get('tags', []))}"

        # 💬 Fallback casual chat
        prompt = f"You are Miammiam, a funny foodie bot who chats with users. They said: \"{message}\". Respond like a helpful, humorous food-lover assistant."
        with self.gpt_model.chat_session():
            response = self.gpt_model.generate(prompt, max_tokens=100)
        return response
