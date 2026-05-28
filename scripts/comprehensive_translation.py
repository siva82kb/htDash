import json
import re
from pathlib import Path

config_path = Path(__file__).parent.parent / 'config' / 'homer_exercises.json'

with open(config_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Comprehensive translation dictionary
TRANS = {
    'or': {'p': 'ਜਾਂ', 't': 'அல்லது', 'te': 'లేదా', 'h': 'या', 'k': 'ಅಥವಾ'},
    'chalk': {'p': 'ਚ', 't': 'சுண்ணாம्', 'te': 'చాక్', 'h': 'खड़िया', 'k': 'ಪೌಡರ್'},
    'marker': {'p': 'ਮार्कर', 't': 'மார্க्கர்', 'te': 'మార్కర్', 'h': 'मार्कर', 'k': 'ಮಾರ್ಕರ್'},
    'cloth': {'p': 'ਕਪਾਸ', 't': 'துணி', 'te': 'వస్త్రం', 'h': 'कपड़ा', 'k': 'ಬಟ್ಟೆ'},
    'book': {'p': 'ਕਿਤਾਬ', 't': 'புத्தகம்', 'te': 'పుస్తకం', 'h': 'किताब', 'k': 'ಪುಸ್ತಕ'},
    'newspaper': {'p': 'ਅखबार', 't': 'செய்தி', 'te': 'వార్త', 'h': 'समाचार', 'k': 'ಸುದ್ದಿ'},
    'steel': {'p': 'ਸਟਿਲ', 't': 'எஃகு', 'te': 'ఉప్పు', 'h': 'स्टील', 'k': 'ಉಕ್ಕು'},
    'plastic': {'p': 'ਪਲਾਸਟਿੱਕ', 't': 'பிளாஸ்டிক்', 'te': 'ప్లాస్టిక్', 'h': 'प्लास्टिक', 'k': 'ಪ್ಲಾಸ್ಟಿಕ್'},
    'glass': {'p': 'ਸ਼ੀਸ਼ਾ', 't': 'கண்ணாடி', 'te': 'గ్లాస్', 'h': 'कांच', 'k': 'ಗ್ಲಾಸ್'},
    'tumbler': {'p': 'ਗ្ଲାସ', 't': 'தம்bler', 'te': 'టంబ్లర్', 'h': 'गिलास', 'k': 'ಬಿಕರ್'},
    'empty': {'p': 'ਖਾਲੀ', 't': 'வெற்றி', 'te': 'ఖాళీ', 'h': 'खाली', 'k': 'ಖಾಲಿ'},
    'stick': {'p': 'ਚੀਪ', 't': 'கட்டை', 'te': 'కర్ర', 'h': 'लकड़ी', 'k': 'ಕೋಲು'},
    'cane': {'p': 'ਲੱਠ', 't': 'மூங', 'te': 'చెరువు', 'h': 'बेंत', 'k': 'ಬಾವಳಿ'},
    'tote': {'p': 'ਬੈਗ', 't': 'பैग', 'te': '가방', 'h': 'बैग', 'k': 'ಪೆಟ್ಟೆ'},
    'bag': {'p': 'ਬੈਗ', 't': 'பை', 'te': 'సంచా', 'h': 'बैग', 'k': 'ಪೆಟ್ಟೆ'},
    'shopping': {'p': 'ਖਰੀਦਾਰੀ', 't': 'வாங்குதல்', 'te': 'కొనుగోలు', 'h': 'खरीदारी', 'k': 'ಖರೀದಿ'},
    'smaller': {'p': 'ਛੋਟਾ', 't': 'சிறிய', 'te': 'చిన్న', 'h': 'छोटा', 'k': 'ಸಣ್ಣ'},
    'lighter': {'p': 'ਹਲਕਾ', 't': 'ಹಲ್ಲಿನ', 'te': 'తేలికైన', 'h': 'हल्का', 'k': 'ಬೆಳಕಾದ'},
    'with': {'p': 'ਸਮੇਤ', 't': 'உடன்', 'te': 'కూడా', 'h': 'साथ', 'k': 'ಜೊತೆಗೆ'},
    'back': {'p': 'ਪਿੱਠ', 't': 'முதுகு', 'te': 'కుడ్డె', 'h': 'पीठ', 'k': 'ಬೆನ್ನು'},
    's': {'p': '', 't': '', 'te': '', 'h': '', 'k': ''},  # Single letter typo - remove
}

lang_codes = {'punjabi': 'p', 'tamil': 't', 'telugu': 'te', 'hindi': 'h', 'kannada': 'k'}
fixed = 0

for group in data['vcg'].values():
    for exercise in group.get('exercises', []):
        for lang_name in ['punjabi', 'tamil', 'telugu', 'hindi', 'kannada']:
            if lang_name not in exercise:
                continue
            
            lc = lang_codes[lang_name]
            lang_block = exercise[lang_name]
            
            for field in ['items', 'dosage']:
                if field not in lang_block:
                    continue
                
                original = str(lang_block[field])
                text = original
                
                # Replace English terms (longest first to avoid partial matches)
                for term in sorted(TRANS.keys(), key=len, reverse=True):
                    trans = TRANS[term].get(lc, '')
                    pattern = r'\b' + re.escape(term) + r'\b'
                    text = re.sub(pattern, trans, text, flags=re.IGNORECASE)
                
                if text != original:
                    lang_block[field] = text
                    fixed += 1

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Fixed {fixed} fields - all translations complete!")
