#!/usr/bin/env python3
"""
Comprehensive translation fixer - handle all untranslated English text.
"""

import json
import re
from pathlib import Path

def fix_all_translations():
    config_path = Path(__file__).parent.parent / 'config' / 'homer_exercises.json'

    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Map English terms to native language translations
    terms = {
        'small': {'punjabi': 'ਛੋਟਾ', 'tamil': 'சிறிய', 'telugu': 'చిన్న', 'hindi': 'छोटा', 'kannada': 'ಸಣ್ಣ'},
        'lightweight': {'punjabi': 'ਹਲਕਾ', 'tamil': 'ஹல்கிய', 'telugu': 'తేలికైన', 'hindi': 'हल्का', 'kannada': 'ತೇಲಿಕ'},
        'shallow': {'punjabi': 'ਖਾਲੀ', 'tamil': 'ఆழమற్ற', 'telugu': 'నిస్సారమైన', 'hindi': 'उथला', 'kannada': 'ಕಡಿಮೆ'},
        'nonstick': {'punjabi': 'ਨੋਨਸਟಿಕ', 'tamil': 'ஐ்எக్స்', 'telugu': 'నాన్-కట్', 'hindi': 'नॉन-स्टिक', 'kannada': 'ನಾನ್-ಸ್ಟಿಕ್'},
        'non-toxic': {'punjabi': 'ਗੈਰ-ਜ਼ਹਿਰੀਲਾ', 'tamil': 'நச்சு இல்லாத', 'telugu': 'నాన్-టాక్సిక్', 'hindi': 'गैर-जहरीला', 'kannada': 'ವಿಷಕಾರಿಯಲ್ಲದ'},
        'soft': {'punjabi': 'ਨਰਮ', 'tamil': 'மென்', 'telugu': 'మృదువైన', 'hindi': 'नरम', 'kannada': 'ಮೃದುವಾದ'},
        'rolled': {'punjabi': 'ਰੋਲ', 'tamil': 'உருட்டப्பட्ட', 'telugu': 'రోలिড్', 'hindi': 'रोल्ड', 'kannada': 'ರೋಲ್ಡ್'},
        'chair': {'punjabi': 'ਕੁਰਸੀ', 'tamil': 'நாற்काலி', 'telugu': 'కుర్చీ', 'hindi': 'कुर्सी', 'kannada': 'ಕುರ್ಚಿ'},
        'table': {'punjabi': 'ਮੇਜ਼', 'tamil': 'மेज', 'telugu': 'టేబుల్', 'hindi': 'मेज़', 'kannada': 'ಮೇಜು'},
        'pages': {'punjabi': 'ਪੰਨੇ', 'tamil': 'பக्கங்கள்', 'telugu': 'పేజీలు', 'hindi': 'पृष्ठ', 'kannada': 'ಪುಟಗಳು'},
    }

    fixed_count = 0

    # Process all exercises
    for group in data['vcg'].values():
        for exercise in group.get('exercises', []):
            for lang in ['punjabi', 'tamil', 'telugu', 'hindi', 'kannada']:
                if lang not in exercise:
                    continue

                lang_block = exercise[lang]

                # Fix items field
                if 'items' in lang_block:
                    original = lang_block['items']
                    fixed = original
                    for eng_term, trans_dict in terms.items():
                        if lang in trans_dict:
                            pattern = r'\b' + re.escape(eng_term) + r'\b'
                            fixed = re.sub(pattern, trans_dict[lang], fixed, flags=re.IGNORECASE)
                    if fixed != original:
                        lang_block['items'] = fixed
                        fixed_count += 1

    # Save updated file
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Fixed {fixed_count} fields")

if __name__ == '__main__':
    fix_all_translations()
