"""
Vocabulary used by the SYNTHETIC label generator.

Everything here is invented for training / testing purposes:
  * brand names are built from generic adjective + noun pairs and screened against a
    block-list of well-known Indian brands so that no generated label imitates a real product;
  * company names, street addresses, telephone numbers, e-mail domains (*.example.in),
    FSSAI numbers and batch codes are random and do not identify real businesses;
  * city / state / PIN-prefix combinations are real geography so that addresses *look*
    realistic to the OCR and extraction models.

Nothing generated from this file may be presented as a real product or as evidence that a
real product complies with the Legal Metrology rules.
"""
from __future__ import annotations

BRAND_ADJ = [
    "Sun", "Golden", "Royal", "Green", "Pure", "Silver", "Blue", "Crystal", "Fresh", "Grand",
    "Happy", "Little", "Noble", "Prime", "Red", "Rich", "Rural", "Sapphire", "Shining", "Smart",
    "Sweet", "True", "Urban", "Vital", "White", "Wild", "Bright", "Classic", "Coastal", "Daily",
    "Emerald", "First", "Harvest", "Hill", "Lotus", "Magic", "Meadow", "Morning", "Nature", "Ocean",
    "Pearl", "Rain", "River", "Saffron", "Spring", "Star", "Summit", "Valley", "Velvet", "Zesty",
    "Kaveri", "Nila", "Ganga", "Vindhya", "Malabar", "Deccan", "Konkan", "Doaba", "Sahyadri", "Narmada",
]
BRAND_NOUN = [
    "Leaf", "Crown", "Field", "Harvest", "Grove", "Farm", "Mill", "Bloom", "Nest", "Spoon",
    "Basket", "Bowl", "Crest", "Dew", "Drop", "Grain", "Hearth", "Kitchen", "Kraft", "Land",
    "Light", "Orchard", "Path", "Peak", "Petal", "Pod", "Root", "Seed", "Sprout", "Stone",
    "Tree", "Vale", "Wave", "Wheel", "Wing", "Aura", "Bay", "Care", "Charm", "Glow",
    "Heritage", "Joy", "Mark", "Mint", "Oasis", "Origin", "Pride", "Rise", "Shore", "Trail",
    "Gold", "Valley", "Rasoi", "Bazaar", "Dhara", "Kalash", "Tara", "Vana", "Sutra", "Mitra",
]
# Screen: do not produce anything that equals or contains a well-known brand token.
BRAND_BLOCKLIST = {
    "tata", "amul", "fortune", "saffola", "britannia", "parle", "haldiram", "mdh", "everest", "nestle",
    "dabur", "patanjali", "himalaya", "colgate", "dove", "surf", "vim", "harpic", "lizol", "classmate",
    "nataraj", "apsara", "aashirvaad", "daawat", "kohinoor", "maggi", "bisleri", "frooti", "pringles",
    "nutella", "fevicol", "goldwinner", "sundrop", "dhara", "gemini", "ariel", "tide", "nirma", "ghadi",
    "lux", "lifebuoy", "pears", "santoor", "godrej", "wipro", "catch", "badshah", "aachi", "sakthi",
    "goldleaf", "sunrise", "sunfeast", "kissan", "bournvita", "horlicks", "boost", "complan", "real",
    "tropicana", "paperboat", "rasna", "tang", "mother", "nandini", "aavin", "milma", "heritage", "goldenharvest",
}
BRAND_BLOCK_PAIRS = {("Golden", "Harvest"), ("Heritage", "Dairy"), ("Real", "Juice"), ("Sun", "Rise"),
                     ("Nature", "Fresh"), ("Golden", "Crown"), ("Royal", "Crown"), ("Blue", "Star"),
                     ("Emerald", "Isle"), ("Nila", "Valley")}

COMPANY_WORDS = {
    "food": ["Agro Foods", "Food Products", "Foods", "Agro Industries", "Consumer Foods", "Agro Processors"],
    "rice": ["Rice Mills", "Agro Mills", "Grain Processors", "Agro Foods"],
    "snacks": ["Snacks", "Bakers", "Confectionery", "Food Products"],
    "beverage": ["Beverages", "Drinks", "Bottlers", "Agro Beverages"],
    "oil": ["Oil Mills", "Edible Oils", "Agro Oils", "Oils & Fats"],
    "household": ["Home Care", "Chemicals", "Consumer Products", "Hygiene Products"],
    "cosmetic": ["Cosmetics", "Personal Care", "Herbals", "Laboratories"],
    "spice": ["Spices", "Masala Udyog", "Spice Mills", "Condiments"],
    "dairy": ["Dairy", "Milk Products", "Dairy Foods", "Milk Producers Co-operative"],
    "stationery": ["Stationery", "Paper Products", "Writing Instruments", "Educational Products"],
    "other": ["Industries", "Enterprises", "Consumer Goods", "Manufacturing Co."],
}
COMPANY_SUFFIX = ["Pvt. Ltd.", "Private Limited", "Pvt Ltd", "Ltd.", "Limited", "LLP", "& Co.", "Industries Pvt. Ltd."]

# (city, state, PIN prefix [3 digits], industrial locality options)
CITIES = [
    ("Nagpur", "Maharashtra", "440", ["MIDC Industrial Area, Butibori", "Hingna MIDC", "Kalmeshwar Road"]),
    ("Pune", "Maharashtra", "411", ["Chakan MIDC", "Bhosari Industrial Area", "Hadapsar Industrial Estate"]),
    ("Mumbai", "Maharashtra", "400", ["Andheri (East)", "Vikhroli (West)", "Turbhe MIDC"]),
    ("Bengaluru", "Karnataka", "560", ["Peenya Industrial Estate", "Bommasandra Industrial Area", "Whitefield"]),
    ("Mysuru", "Karnataka", "570", ["Hebbal Industrial Area", "Metagalli"]),
    ("Chennai", "Tamil Nadu", "600", ["Ambattur Industrial Estate", "Guindy", "Sriperumbudur"]),
    ("Coimbatore", "Tamil Nadu", "641", ["SIDCO Industrial Estate", "Kurichi", "Peelamedu"]),
    ("Madurai", "Tamil Nadu", "625", ["Kappalur Industrial Estate", "K. Pudur"]),
    ("Hyderabad", "Telangana", "500", ["Cherlapally IDA", "Jeedimetla", "Uppal Industrial Area"]),
    ("Vijayawada", "Andhra Pradesh", "520", ["Autonagar", "Kondapalli IDA"]),
    ("Ahmedabad", "Gujarat", "380", ["Naroda GIDC", "Vatva GIDC", "Changodar"]),
    ("Surat", "Gujarat", "395", ["Sachin GIDC", "Pandesara GIDC"]),
    ("Vapi", "Gujarat", "396", ["GIDC Phase II", "GIDC Phase I"]),
    ("Indore", "Madhya Pradesh", "452", ["Sanwer Road Industrial Area", "Pithampur Sector 3"]),
    ("Jaipur", "Rajasthan", "302", ["Sitapura Industrial Area", "VKI Area"]),
    ("Ludhiana", "Punjab", "141", ["Focal Point Phase V", "Industrial Area A"]),
    ("Karnal", "Haryana", "132", ["Sector 3, HSIIDC", "G.T. Road"]),
    ("Sonipat", "Haryana", "131", ["HSIIDC Kundli", "Industrial Area Rai"]),
    ("Gurugram", "Haryana", "122", ["Udyog Vihar Phase IV", "Sector 37"]),
    ("Noida", "Uttar Pradesh", "201", ["Sector 63", "Phase II, Hosiery Complex"]),
    ("Lucknow", "Uttar Pradesh", "226", ["Talkatora Industrial Estate", "Chinhat"]),
    ("Kolkata", "West Bengal", "700", ["Taratala Industrial Estate", "Kasba Industrial Estate"]),
    ("Kochi", "Kerala", "682", ["Kakkanad", "Edayar Industrial Area"]),
    ("Guwahati", "Assam", "781", ["Amingaon", "Bamunimaidan"]),
    ("Bhubaneswar", "Odisha", "751", ["Mancheswar Industrial Estate", "Rasulgarh"]),
    ("Haridwar", "Uttarakhand", "249", ["SIDCUL Sector 6", "Bahadrabad"]),
    ("Solan", "Himachal Pradesh", "173", ["Baddi Industrial Area", "Barotiwala"]),
    ("Patna", "Bihar", "800", ["Patliputra Industrial Area", "Fatuha"]),
    ("Raipur", "Chhattisgarh", "492", ["Urla Industrial Area", "Siltara Phase II"]),
    ("Dehradun", "Uttarakhand", "248", ["Selaqui Industrial Area", "Patel Nagar"]),
]
STREET_FORMS = [
    "Plot No. {n}", "Plot {n}", "Survey No. {n}/{m}", "#{n}, {o} Cross", "B-{n}", "Shed No. {n}", "Khasra No. {n}",
    "Unit {n}", "Door No. {n}-{m}", "Gat No. {n}", "Building {m}, Unit {n}", "C-{n}/{m}",
]
ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th"]

FOREIGN = [
    ("Italy", ["Olive", "Pasta"]), ("Spain", ["Olive"]), ("Thailand", ["Coconut Water"]), ("Malaysia", ["Wafer"]),
    ("France", ["Lotion", "Serum"]), ("South Korea", ["Serum", "Face Wash"]), ("China", ["Markers", "Batteries", "Stapler"]),
    ("Germany", ["Pencils", "Glass Cleaner"]), ("Australia", ["Oats", "Honey"]), ("Vietnam", ["Coffee", "Cashew"]),
    ("Belgium", ["Cookies", "Chocolate"]), ("United Arab Emirates", ["Dates"]), ("Sri Lanka", ["Tea"]),
    ("Turkey", ["Hazelnut"]), ("USA", ["Almond", "Peanut Butter"]),
]

# ------------------------------------------------------------------------------ product catalogue
# key -> dict(app_category, company_kind, products=[(name, unit_kind, sizes, price_per_base_range, shelf_months, fssai, extras)])
#   unit_kind: "g" (mass, sizes in g), "ml" (volume, sizes in ml), "N" (count, sizes = count), "sheets", "pairs", "m"
#   price range = INR per base unit (per kg / per L / per piece)
CATEGORIES = {
    "packaged_food": dict(app="food", company="food", products=[
        ("Instant Noodles Masala", "g", [70, 140, 280, 560], (180, 260), 9),
        ("Tomato Ketchup", "g", [200, 500, 950], (120, 190), 12),
        ("Mango Pickle", "g", [200, 400, 1000], (220, 380), 12),
        ("Whole Wheat Atta", "g", [1000, 5000, 10000], (42, 68), 4),
        ("Roasted Vermicelli", "g", [180, 400, 900], (90, 150), 9),
        ("Rolled Oats", "g", [500, 1000], (160, 260), 12),
        ("Corn Flakes", "g", [250, 475, 875], (300, 420), 9),
        ("Peanut Butter Crunchy", "g", [340, 510, 1000], (380, 560), 12),
        ("Mixed Fruit Jam", "g", [200, 500], (240, 340), 18),
        ("Natural Honey", "g", [250, 500, 1000], (480, 760), 24),
        ("Tomato Soup Mix", "g", [50, 100], (900, 1400), 12),
        ("Thick Poha", "g", [500, 1000], (70, 110), 6),
        ("Ready to Eat Dal Makhani", "g", [300], (430, 560), 12),
        ("Chocolate Spread", "g", [200, 350], (700, 950), 12),
    ]),
    "rice_grains": dict(app="food", company="rice", products=[
        ("Basmati Rice", "g", [1000, 5000, 10000], (95, 210), 18),
        ("Sona Masoori Rice", "g", [1000, 5000, 10000, 25000], (55, 80), 12),
        ("Toor Dal", "g", [500, 1000, 2000], (140, 190), 9),
        ("Moong Dal", "g", [500, 1000], (120, 170), 9),
        ("Chana Dal", "g", [500, 1000], (80, 120), 9),
        ("Kabuli Chana", "g", [500, 1000], (120, 180), 12),
        ("Red Rajma", "g", [500, 1000], (130, 190), 12),
        ("Idli Rice", "g", [1000, 5000], (45, 70), 12),
        ("Ragi Flour", "g", [500, 1000], (70, 110), 6),
        ("Bombay Rava (Sooji)", "g", [500, 1000], (50, 80), 6),
        ("Besan", "g", [500, 1000], (90, 130), 6),
        ("Brown Rice", "g", [1000], (130, 200), 12),
    ]),
    "biscuits_snacks": dict(app="food", company="snacks", products=[
        ("Cream Sandwich Biscuits", "g", [75, 150, 300], (180, 280), 9),
        ("Glucose Biscuits", "g", [55, 250, 800], (100, 140), 9),
        ("Digestive Biscuits", "g", [100, 250, 1000], (200, 300), 9),
        ("Salted Crackers", "g", [100, 200], (160, 240), 9),
        ("Classic Salted Potato Chips", "g", [26, 52, 90], (380, 520), 4),
        ("Aloo Bhujia", "g", [150, 400, 1000], (220, 300), 6),
        ("Khatta Meetha Namkeen", "g", [200, 400], (200, 280), 6),
        ("Roasted Peanuts", "g", [140, 200], (250, 350), 6),
        ("Choco Chip Cookies", "g", [75, 150, 250], (320, 480), 9),
        ("Milk Rusk", "g", [200, 300], (180, 250), 6),
        ("Kerala Banana Chips", "g", [150, 400], (320, 420), 4),
        ("Methi Khakhra", "g", [200], (300, 400), 4),
    ]),
    "beverages": dict(app="beverage", company="beverage", products=[
        ("Mango Fruit Drink", "ml", [125, 200, 600, 1200], (70, 110), 9),
        ("Packaged Drinking Water", "ml", [500, 1000, 2000, 5000], (15, 25), 6),
        ("Orange Juice", "ml", [200, 1000], (110, 160), 9),
        ("Carbonated Lemon Drink", "ml", [250, 750, 2250], (40, 60), 6),
        ("Premium Assam Tea", "g", [100, 250, 500, 1000], (440, 700), 18),
        ("Instant Coffee Powder", "g", [50, 100, 200], (1700, 2600), 18),
        ("Tender Coconut Water", "ml", [200, 1000], (130, 190), 6),
        ("Energy Drink", "ml", [250, 350], (380, 520), 12),
        ("Jaljeera Drink", "ml", [200, 600], (70, 100), 6),
    ]),
    "edible_oils": dict(app="food", company="oil", products=[
        ("Refined Sunflower Oil", "ml", [500, 1000, 5000], (140, 190), 9),
        ("Cold Pressed Groundnut Oil", "ml", [500, 1000, 5000], (190, 280), 6),
        ("Kachi Ghani Mustard Oil", "ml", [500, 1000, 5000], (150, 210), 9),
        ("Rice Bran Oil", "ml", [1000, 5000], (150, 200), 9),
        ("Extra Virgin Olive Oil", "ml", [250, 500, 1000], (900, 1600), 24),
        ("Virgin Coconut Oil", "ml", [250, 500, 1000], (400, 700), 12),
        ("Refined Soyabean Oil", "ml", [1000, 5000], (120, 170), 9),
        ("Gingelly (Sesame) Oil", "ml", [500, 1000], (320, 460), 9),
    ]),
    "household_cleaning": dict(app="household", company="household", products=[
        ("Detergent Powder", "g", [500, 1000, 4000], (90, 180), 36),
        ("Dishwash Liquid Lemon", "ml", [250, 500, 750, 2000], (180, 280), 24),
        ("Disinfectant Floor Cleaner", "ml", [500, 975, 2000], (180, 260), 24),
        ("Toilet Cleaner", "ml", [200, 500, 1000], (180, 240), 24),
        ("Glass Cleaner Spray", "ml", [250, 500], (220, 300), 24),
        ("Dishwash Bar", "g", [130, 300, 500], (90, 140), 24),
        ("Liquid Detergent Front Load", "ml", [500, 1000, 2000], (220, 320), 24),
        ("Mosquito Repellent Coils", "N", [10, 20], (4, 7), 36),
        ("Garbage Bags Medium", "N", [15, 30], (4, 8), 60),
        ("Room Freshener Spray", "ml", [220, 300], (700, 900), 36),
    ]),
    "cosmetics_personal_care": dict(app="cosmetic", company="cosmetic", products=[
        ("Herbal Shampoo", "ml", [80, 180, 340, 650], (600, 900), 24),
        ("Neem Face Wash", "ml", [50, 100, 150], (1300, 1900), 24),
        ("Moisturising Body Lotion", "ml", [100, 200, 400], (800, 1200), 30),
        ("Fluoride Toothpaste", "g", [50, 100, 150, 200], (500, 750), 24),
        ("Sandal Bathing Soap", "g", [75, 100, 125], (400, 600), 36),
        ("Coconut Hair Oil", "ml", [100, 200, 500], (500, 800), 24),
        ("Talcum Powder", "g", [100, 300], (500, 750), 36),
        ("Sunscreen Lotion SPF 50", "g", [50, 100], (5000, 7000), 24),
        ("Lip Balm", "g", [4, 5], (18000, 30000), 30),
        ("Hand Wash Refill", "ml", [185, 750], (300, 450), 24),
        ("Shaving Cream", "g", [30, 70], (1000, 1500), 36),
    ]),
    "spices": dict(app="food", company="spice", products=[
        ("Turmeric Powder", "g", [100, 200, 500], (260, 400), 12),
        ("Kashmiri Red Chilli Powder", "g", [100, 200, 500], (450, 700), 12),
        ("Coriander Powder", "g", [100, 200, 500], (220, 320), 12),
        ("Garam Masala", "g", [50, 100], (900, 1300), 12),
        ("Chicken Masala", "g", [50, 100], (800, 1100), 12),
        ("Sambar Powder", "g", [100, 200], (500, 700), 9),
        ("Cumin Seeds (Jeera)", "g", [100, 200], (500, 750), 12),
        ("Black Pepper Whole", "g", [50, 100], (900, 1400), 18),
        ("Chaat Masala", "g", [50, 100], (700, 1000), 12),
        ("Compounded Asafoetida (Hing)", "g", [25, 50], (3000, 5000), 24),
        ("Kasuri Methi", "g", [25, 50], (1200, 1800), 12),
    ]),
    "dairy": dict(app="food", company="dairy", products=[
        ("Toned Milk", "ml", [500, 1000], (54, 60), 0),
        ("Fresh Paneer", "g", [200, 500, 1000], (380, 460), 0),
        ("Pasteurised Table Butter", "g", [100, 500], (500, 580), 6),
        ("Pure Cow Ghee", "ml", [200, 500, 1000], (580, 760), 9),
        ("Set Curd", "g", [200, 400, 1000], (70, 100), 0),
        ("Processed Cheese Slices", "g", [200, 750], (560, 700), 9),
        ("Skimmed Milk Powder", "g", [200, 500, 1000], (440, 560), 12),
        ("Badam Flavoured Milk", "ml", [180, 200], (160, 220), 6),
        ("Spiced Buttermilk", "ml", [200, 500], (40, 60), 0),
    ]),
    "stationery": dict(app="stationery", company="stationery", products=[
        ("Ball Point Pens Blue", "N", [5, 10, 20], (5, 10), 0),
        ("HB Pencils", "N", [10], (5, 8), 0),
        ("Dust Free Erasers", "N", [5, 10, 20], (3, 5), 0),
        ("Glue Stick", "g", [8, 15, 25], (2500, 4000), 24),
        ("Sketch Pens", "N", [12, 24], (5, 9), 0),
        ("A4 Copier Paper 75 GSM", "sheets", [500], (0.5, 0.7), 0),
        ("Wax Crayons", "N", [12, 24], (4, 7), 0),
        ("Long Notebook Single Line", "N", [1, 6], (55, 85), 0),
        ("Correction Pen", "ml", [7, 12], (5000, 7000), 24),
        ("Permanent Markers", "N", [4, 10], (18, 30), 0),
    ]),
    "other_consumer_goods": dict(app="other", company="other", products=[
        ("Cotton Ankle Socks", "pairs", [3, 5], (60, 100), 0),
        ("LED Bulb 9W", "N", [1, 2], (90, 140), 0),
        ("Alkaline AA Batteries", "N", [2, 4, 10], (22, 35), 60),
        ("Aluminium Foil Roll", "m", [9, 25, 72], (8, 14), 0),
        ("Paper Napkins", "N", [50, 100], (0.8, 1.4), 0),
        ("Scented Candles", "N", [4, 6], (40, 70), 0),
        ("Cotton Buds", "N", [100, 200], (0.5, 0.9), 0),
        ("Kitchen Towel Rolls", "N", [2, 4], (60, 90), 0),
    ]),
}

# App category overrides for individual products (the rule engine has finer categories).
APP_CATEGORY_OVERRIDE = {
    "Fluoride Toothpaste": "personal_care", "Sandal Bathing Soap": "personal_care", "Hand Wash Refill": "personal_care",
    "Shaving Cream": "personal_care", "Talcum Powder": "personal_care", "Coconut Hair Oil": "personal_care",
    "Cotton Ankle Socks": "textile", "LED Bulb 9W": "electrical", "Alkaline AA Batteries": "electronics",
}

FOOD_CATEGORIES = {"packaged_food", "rice_grains", "biscuits_snacks", "beverages", "edible_oils", "spices", "dairy"}

TAGLINES = [
    "100% Natural", "No Added Preservatives", "Rich in Fibre", "Premium Quality", "Farm Fresh", "Since 1987",
    "Double Filtered", "Aged 12 Months", "Extra Long Grain", "Stone Ground", "Hand Picked", "New Improved Formula",
    "Family Pack", "Value Pack", "Economy Pack", "Now Bigger", "Pure & Hygienic", "Trusted Quality",
    "Made with Real Fruit", "Tough on Stains", "Kills 99.9% Germs*", "Dermatologically Tested", "Paraben Free",
    "Smooth Writing", "Non-Toxic", "Long Lasting", "Energy Saving",
]

STORAGE = [
    "Store in a cool and dry place.", "Store in a cool, dry and hygienic place.", "Keep away from direct sunlight.",
    "Refrigerate after opening.", "Store below 25°C.", "Keep refrigerated at 4°C.", "Best consumed chilled.",
    "Keep out of reach of children.", "For external use only.", "Avoid contact with eyes.", "Shake well before use.",
    "Close the lid tightly after use.", "Protect from moisture.",
]
LEGAL_MISC = [
    "Not for medicinal use.", "Recyclable pack. Please dispose responsibly.", "Packed in a hygienic environment.",
    "Contains permitted class II preservative (INS 211).", "Contains added flavours (natural and nature identical).",
    "Allergen information: Contains wheat and milk.", "Allergen advice: May contain traces of nuts.",
    "This pack is sold by weight, not by volume.", "Some settling of contents may occur.",
    "Weight of contents when packed.", "Colour may vary from batch to batch.",
]
INGREDIENT_POOL = [
    "wheat flour", "sugar", "edible vegetable oil (palm)", "invert syrup", "milk solids", "iodised salt",
    "leavening agents (500(ii), 503(ii))", "emulsifier (322)", "cocoa solids", "spices and condiments",
    "rice bran oil", "tomato paste", "vinegar", "citric acid", "acidity regulator (330)", "natural flavours",
    "maltodextrin", "dehydrated vegetables", "turmeric", "chilli", "coriander", "mango pulp", "water",
]

# Hindi (Devanagari) declaration labels used for bilingual variations.
HINDI = {
    "mrp": "अधिकतम खुदरा मूल्य",
    "net_quantity": "शुद्ध मात्रा",
    "packed_on": "पैक करने की तिथि",
    "mfg_date": "निर्माण तिथि",
    "customer_care": "उपभोक्ता सेवा",
    "inclusive": "सभी करों सहित",
    "best_before": "इससे पहले उपयोग करें",
    "batch_number": "बैच संख्या",
}


# ------------------------------------------------------------------------------ category-aware extras
_GROUP_OF = {"packaged_food": "food", "rice_grains": "food", "biscuits_snacks": "food", "spices": "food",
             "dairy": "dairy", "edible_oils": "oil", "beverages": "bev", "household_cleaning": "household",
             "cosmetics_personal_care": "cosmetic", "stationery": "stationery", "other_consumer_goods": "other"}
_TAGS = {
    "food": ["100% Natural", "No Added Preservatives", "Rich in Fibre", "Premium Quality", "Farm Fresh", "Stone Ground",
             "Hand Picked", "Family Pack", "Value Pack", "Extra Long Grain", "Aged 12 Months", "Pure & Hygienic", "Since 1987"],
    "dairy": ["Farm Fresh", "Pasteurised", "Rich & Creamy", "Pure & Hygienic", "Trusted Quality"],
    "oil": ["Double Filtered", "Cold Pressed", "Rich in Vitamin E", "Heart Friendly*", "Pure & Natural", "Economy Pack"],
    "bev": ["Made with Real Fruit", "No Added Sugar", "Refreshing Taste", "Family Pack", "Value Pack", "Chilled is Best"],
    "household": ["Tough on Stains", "Kills 99.9% Germs*", "Fresh Lemon Fragrance", "New Improved Formula", "Economy Pack"],
    "cosmetic": ["Dermatologically Tested", "Paraben Free", "Enriched with Aloe Vera", "For All Skin Types", "Herbal Formula"],
    "stationery": ["Smooth Writing", "Non-Toxic", "Long Lasting", "Student's Choice", "Value Pack"],
    "other": ["Long Lasting", "Energy Saving", "Premium Quality", "Value Pack", "Soft & Comfortable"],
}
_STORE = {
    "food": ["Store in a cool and dry place.", "Store in a cool, dry and hygienic place.", "Keep away from direct sunlight.",
             "Transfer contents to an airtight container after opening.", "Close the pack tightly after use."],
    "dairy": ["Keep refrigerated at 4°C.", "Store below 5°C.", "Refrigerate after opening.", "Do not freeze."],
    "oil": ["Store in a cool and dry place.", "Keep away from direct sunlight.", "Close the lid tightly after use."],
    "bev": ["Best consumed chilled.", "Refrigerate after opening and consume within 2 days.", "Shake well before use.",
            "Store in a cool and dry place."],
    "household": ["Keep out of reach of children.", "Avoid contact with eyes.", "Store in a cool and dry place.",
                  "Do not mix with other cleaning products."],
    "cosmetic": ["For external use only.", "Avoid contact with eyes.", "Store below 30°C.", "Keep out of reach of children."],
    "stationery": ["Keep away from heat.", "Not suitable for children under 3 years.", "Replace the cap after use."],
    "other": ["Keep away from moisture.", "Keep out of reach of children.", "Dispose of responsibly."],
}
_MISC = {
    "food": ["Allergen information: Contains wheat and milk.", "Allergen advice: May contain traces of nuts.",
             "Contains permitted class II preservative (INS 211).", "Contains added flavours (natural and nature identical).",
             "Packed in a hygienic environment.", "Recyclable pack. Please dispose responsibly."],
    "dairy": ["Packed in a hygienic environment.", "Contains milk.", "Recyclable pack. Please dispose responsibly."],
    "oil": ["Not for medicinal use.", "Weight of contents when packed.", "Recyclable pack. Please dispose responsibly."],
    "bev": ["Contains added flavours (natural and nature identical).", "Not recommended for children.",
            "Recyclable pack. Please dispose responsibly."],
    "household": ["Not for medicinal use.", "Recyclable pack. Please dispose responsibly.", "Colour may vary from batch to batch."],
    "cosmetic": ["Colour may vary from batch to batch.", "Patch test recommended before use.", "Not tested on animals."],
    "stationery": ["Colour may vary from batch to batch.", "Conforms to IS 3705."],
    "other": ["Colour may vary from batch to batch.", "Some settling of contents may occur."],
}


def taglines_for(cat_key: str) -> list[str]:
    return _TAGS[_GROUP_OF.get(cat_key, "other")]


def storage_for(cat_key: str) -> list[str]:
    return _STORE[_GROUP_OF.get(cat_key, "other")]


def misc_for(cat_key: str) -> list[str]:
    return _MISC[_GROUP_OF.get(cat_key, "other")]
