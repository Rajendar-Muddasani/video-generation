"""
stories/clever_crow.py
The Clever Crow — classic Aesop fable
Moral: patient thinking beats brute force

To generate the English video:
    python generate_story.py stories/clever_crow.py

To regenerate everything (new images, new TTS):
    python generate_story.py stories/clever_crow.py --force
"""

STORY_ID    = "clever-crow"
STORY_TITLE = "The Clever Crow"
CHANNEL_NAME = "Mitra AI Stories"

# Prepended to EVERY DALL-E 3 prompt — controls the art style for the whole story.
# Change this to completely change the visual feel of the story.
ART_STYLE = (
    "Soft watercolor children's book illustration, warm pastel colours, "
    "gentle brushstrokes, cozy magical forest setting, "
    "golden and moonlit lighting, dreamlike and safe for children, "
    "no text or letters in the image. "
)

# Voice config for English narration
VOICE_EN = {
    "language_code": "en-US",
    "name": "en-US-Chirp3-HD-Aoede",   # warm feminine — best for bedtime
    "fallback": "en-US-Neural2-F",
    "speaking_rate": 0.85,              # slow and soothing
    "pitch": -2.0,                      # slightly lower = more calming
}

# Voice config for Telugu narration (optional — use --lang te)
VOICE_TE = {
    "language_code": "te-IN",
    "name": "te-IN-Chirp3-HD-Kore",
    "fallback": "te-IN-Standard-B",
    "speaking_rate": 0.88,
    "pitch": -1.0,
}

# ── Slides ────────────────────────────────────────────────────────────────────
# Each slide: (eyebrow_text, title_overlay, dall_e_scene_prompt, narration_text)
#
# eyebrow  — small coloured label above the title (e.g. "Part 1"), or "" for none
# title    — large white text shown at bottom of image
# dall_e   — scene description WITHOUT art style (art style is prepended automatically)
# narration— spoken text for this slide (aim for 110-140 words for 50-65 second slides)

SLIDES = [
    (
        "",                        # eyebrow
        "The Clever Crow",         # title overlay
        # DALL-E scene
        "A majestic black crow perched on a moonlit banyan branch, glowing "
        "full moon behind, silver stars, warm golden light, title card feel",
        # narration
        "Once upon a time, in a beautiful green forest, there lived "
        "a very clever crow. He was known for his bright eyes and quick mind. "
        "Tonight, we follow the crow on a very special day...",
    ),
    (
        "Part 1",
        "A Hot Summer Day",
        "A lush green forest under a blazing summer sun, dust on the path, "
        "wilting flowers, a small dry riverbed, warm amber and yellow tones",
        "It was the hottest day of summer. The sun blazed down on the forest "
        "like a great fire in the sky. The leaves drooped. The river had dried up. "
        "Every creature was searching for water. The crow was very, very thirsty.",
    ),
    (
        "Part 2",
        "The Thirsty Crow",
        "A tired crow with drooping wings flying over a dry dusty village, "
        "searching, looking down with worried bright eyes, golden sky",
        "The crow flew here and there, searching everywhere. He checked the "
        "riverbed — dry. He checked the old pond — empty. His wings grew heavy "
        "and his throat burned. But the clever crow did not give up.",
    ),
    (
        "Part 3",
        "Water! But So Far Down",
        "A crow peering into a tall clay pot sitting on dry ground, "
        "beak reaching in but too short to touch the water far below, "
        "late afternoon light, a few clouds",
        "At last! Near an old cottage, the crow spotted a tall clay pot. "
        "He flew down and looked inside. There was water — cool, beautiful water! "
        "But it was deep, deep at the bottom. No matter how far the crow stretched, "
        "he could not reach it. What would he do?",
    ),
    (
        "Part 4",
        "Think, Crow, Think",
        "A crow sitting quietly beside a clay pot, eyes closed in thought, "
        "a contemplative expression, soft evening light, pebbles nearby on the ground",
        "The crow sat very still. He did not panic. He thought carefully. "
        "He looked at the pot. He looked at his wings. He looked around him. "
        "And then — he looked down at the ground. Pebbles! Small round pebbles "
        "were scattered all around. An idea began to shine in his clever mind.",
    ),
    (
        "Part 5",
        "One Pebble at a Time",
        "A crow carefully picking up a small pebble with its beak, "
        "a clay pot nearby, water level very low inside, "
        "gentle determination in the crow's eyes, warm evening light",
        "The crow picked up one pebble with his beak. He walked to the pot "
        "and dropped it in. Plop. The water barely moved. He picked up another. "
        "Plop. And another. Plop plop plop. It was slow work. But the crow "
        "kept going, one pebble at a time, never stopping.",
    ),
    (
        "Part 6",
        "The Water is Rising!",
        "A crow excitedly dropping pebbles into a clay pot, "
        "the water level noticeably higher now, joy and hope on the crow's face, "
        "golden hour light, beautiful lush forest background",
        "After many, many pebbles, something wonderful happened. The water began "
        "to rise! Slowly, slowly, it crept up toward the top. The crow worked "
        "faster now, his heart beating with excitement. Higher and higher the "
        "cool water climbed. The crow's clever plan was working.",
    ),
    (
        "Part 7",
        "One Last Pebble",
        "A crow holding the final pebble, looking at a nearly full clay pot, "
        "water very close to the top, a magical glowing light around the pot, "
        "triumphant but tender expression",
        "The crow picked up one last pebble. He held it for a moment, looking "
        "at the pot. The water was almost — almost — at the top. He took a deep "
        "breath. He dropped the pebble in. Plop. And the cool, clear water "
        "rose right up to the very brim.",
    ),
    (
        "Part 8",
        "Sweet Water, Sweet Victory",
        "A happy crow drinking water from a full clay pot, "
        "eyes closed with joy, evening sunlight, forest glowing warmly, "
        "relief and happiness, fireflies appearing in background",
        "The crow dipped his beak into the cool water and drank. Oh, how sweet "
        "it was! He drank and drank until his thirst was completely gone. "
        "He looked up at the golden sky, and felt very proud — not because he "
        "was strong, but because he had been patient and clever.",
    ),
    (
        "",
        "Goodnight, Little One",
        "A crow sleeping peacefully on a moonlit branch, "
        "bright stars, a soft glowing moon, fireflies, "
        "a cozy peaceful forest at night, gentle and dreamy",
        "And so, dear child, the clever crow taught us something important. "
        "When a problem feels too hard, sit quietly and think. Look around you. "
        "The answer is often right there, waiting. Now close your eyes, "
        "dream of cool water and kind forests. Goodnight.",
    ),
]

# ── Telugu Slides ──────────────────────────────────────────────────────────────
# Same images and overlays as SLIDES; only the narration_text changes.
# Each tuple: (eyebrow, title_overlay, dall_e_scene_prompt, telugu_narration)
SLIDES_TE = [
    (
        "",
        "The Clever Crow",
        "A majestic black crow perched on a moonlit banyan branch, glowing "
        "full moon behind, silver stars, warm golden light, title card feel",
        "ఒకప్పుడు ఒక పచ్చని అడవిలో ఒక చాలా తెలివైన కాకి నివసించేది. "
        "అతను తన మెరిసే కళ్ళు మరియు చురుకైన బుద్ధికి ప్రసిద్ధుడు. "
        "ఈ రాత్రి, మనం ఆ కాకితో పాటు చాలా ప్రత్యేకమైన రోజు గురించి తెలుసుకుందాం.",
    ),
    (
        "భాగం 1",
        "A Hot Summer Day",
        "A lush green forest under a blazing summer sun, dust on the path, "
        "wilting flowers, a small dry riverbed, warm amber and yellow tones",
        "అది వేసవి కాలంలో అత్యంత వేడిగా ఉన్న రోజు. సూర్యుడు అడవిపై "
        "ఒక పెద్ద అగ్నిలా మండిపోతున్నాడు. ఆకులు వాలిపోయాయి. నది ఎండిపోయింది. "
        "ప్రతి జీవి నీళ్ళ కోసం వెతుకుతోంది. కాకికి చాలా దాహంగా ఉంది.",
    ),
    (
        "భాగం 2",
        "The Thirsty Crow",
        "A tired crow with drooping wings flying over a dry dusty village, "
        "searching, looking down with worried bright eyes, golden sky",
        "కాకి ఇక్కడా అక్కడా ఎగురుతూ అన్నిచోట్లా వెతికింది. "
        "నదిలో చూసింది — ఎండిపోయింది. పాత చెరువు దగ్గర చూసింది — ఖాళీగా ఉంది. "
        "రెక్కలు భారంగా అయ్యాయి, గొంతు మండిపోతోంది. "
        "కానీ తెలివైన కాకి వదులుకోలేదు.",
    ),
    (
        "భాగం 3",
        "Water! But So Far Down",
        "A crow peering into a tall clay pot sitting on dry ground, "
        "beak reaching in but too short to touch the water far below, "
        "late afternoon light, a few clouds",
        "చివరకు! ఒక పాత ఇంటి దగ్గర, కాకి ఒక పెద్ద మట్టి కుండను చూసింది. "
        "అది కిందికి దిగి లోపల చూసింది. నీళ్ళు ఉన్నాయి — చల్లటి, అందమైన నీళ్ళు! "
        "కానీ అవి చాలా లోతుగా దిగువన ఉన్నాయి. కాకి ఎంత సాచినా "
        "నీళ్ళను అందుకోలేకపోయింది. ఇప్పుడు ఏం చేయాలి?",
    ),
    (
        "భాగం 4",
        "Think, Crow, Think",
        "A crow sitting quietly beside a clay pot, eyes closed in thought, "
        "a contemplative expression, soft evening light, pebbles nearby on the ground",
        "కాకి చాలా నిశ్శబ్దంగా కూర్చుంది. అది కంగారుపడలేదు. జాగ్రత్తగా ఆలోచించింది. "
        "కుండను చూసింది. తన రెక్కలను చూసింది. చుట్టూ చూసింది. "
        "తర్వాత — నేలవైపు చూసింది. రాళ్ళు! చిన్న చిన్న గుండ్రటి రాళ్ళు "
        "అన్నిచోట్లా చెల్లాచెదురుగా ఉన్నాయి. తెలివైన మనసులో ఒక ఆలోచన మెరిసింది.",
    ),
    (
        "భాగం 5",
        "One Pebble at a Time",
        "A crow carefully picking up a small pebble with its beak, "
        "a clay pot nearby, water level very low inside, "
        "gentle determination in the crow's eyes, warm evening light",
        "కాకి తన ముక్కుతో ఒక రాయిని అందుకుంది. కుండ దగ్గరికి వెళ్ళి దాన్ని వేసింది. "
        "ఖళ్ళు. నీళ్ళు పెద్దగా కదలలేదు. మరో రాయి వేసింది. ఖళ్ళు. "
        "ఇంకొకటి. ఖళ్ళు ఖళ్ళు ఖళ్ళు. ఇది నెమ్మదైన పని. "
        "కానీ కాకి ఒక్కో రాయిగా, ఆగకుండా కొనసాగింది.",
    ),
    (
        "భాగం 6",
        "The Water is Rising!",
        "A crow excitedly dropping pebbles into a clay pot, "
        "the water level noticeably higher now, joy and hope on the crow's face, "
        "golden hour light, beautiful lush forest background",
        "చాలా చాలా రాళ్ళు వేసిన తర్వాత, అద్భుతమైన విషయం జరిగింది. "
        "నీళ్ళు పైకి రావడం మొదలయ్యాయి! నెమ్మదిగా, నెమ్మదిగా పైకి వస్తున్నాయి. "
        "కాకి ఇప్పుడు వేగంగా పని చేసింది, గుండె ఉత్సాహంతో కొట్టుకుంటోంది. "
        "చల్లటి నీళ్ళు మరింత పైకి వస్తున్నాయి. కాకి తెలివైన పథకం పని చేస్తోంది.",
    ),
    (
        "భాగం 7",
        "One Last Pebble",
        "A crow holding the final pebble, looking at a nearly full clay pot, "
        "water very close to the top, a magical glowing light around the pot, "
        "triumphant but tender expression",
        "కాకి చివరి రాయిని తీసుకుంది. ఒక్క క్షణం పట్టుకుని కుండను చూసింది. "
        "నీళ్ళు దాదాపు — దాదాపు — అంచు వరకు వచ్చాయి. "
        "లోతుగా శ్వాస తీసుకుంది. రాయిని వేసింది. ఖళ్ళు. "
        "చల్లటి, తెలిసిన నీళ్ళు అంచు వరకు వచ్చాయి.",
    ),
    (
        "భాగం 8",
        "Sweet Water, Sweet Victory",
        "A happy crow drinking water from a full clay pot, "
        "eyes closed with joy, evening sunlight, forest glowing warmly, "
        "relief and happiness, fireflies appearing in background",
        "కాకి తన ముక్కును చల్లటి నీళ్ళలో ముంచి తాగింది. ఎంత తీయగా ఉందో! "
        "దాహం పూర్తిగా తీరే వరకు తాగింది. బంగారు ఆకాశం వైపు చూసి, "
        "చాలా గర్వంగా అనిపించింది — తాను బలవంతుడు కాబట్టి కాదు, "
        "తాను ఓపికగా మరియు తెలివిగా ఉన్నాడు కాబట్టి.",
    ),
    (
        "",
        "Goodnight, Little One",
        "A crow sleeping peacefully on a moonlit branch, "
        "bright stars, a soft glowing moon, fireflies, "
        "a cozy peaceful forest at night, gentle and dreamy",
        "కాబట్టి, ప్రియమైన బిడ్డా, తెలివైన కాకి మనకు ఒక ముఖ్యమైన విషయం నేర్పింది. "
        "ఒక సమస్య చాలా కష్టంగా అనిపించినప్పుడు, నిశ్శబ్దంగా కూర్చుని ఆలోచించు. "
        "చుట్టూ చూడు. సమాధానం చాలా దగ్గరలోనే ఉంటుంది. "
        "ఇప్పుడు కళ్ళు మూసుకో, చల్లటి నీళ్ళు మరియు మంచి అడవుల గురించి కలలు కను. శుభ రాత్రి.",
    ),
]

# ── YouTube metadata ──────────────────────────────────────────────────────────
YOUTUBE_METADATA = """\
TITLE:
The Clever Crow | Bedtime Story for Kids | Mitra AI Stories

DESCRIPTION:
A thirsty crow finds a pot of water — but the water is too deep to reach.
Watch how clever thinking and patience save the day in this beautiful classic fable.

This gentle bedtime story teaches children that calm thinking and persistence
always find a way — even when a problem seems impossible.

🌙 New story every day. Subscribe to Mitra AI Stories.

TAGS:
bedtime story, clever crow story, crow and pitcher, moral story for kids,
animated story, story in English, Mitra AI Stories, fable for children,
Aesop fable, bedtime stories for toddlers, short story with moral

CATEGORY: Education
THUMBNAIL: use output/clever-crow/slide01_overlay.jpg or slide09_overlay.jpg
"""
