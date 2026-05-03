# WORKFLOW_BYPASS_OK: strategy-cut-builder lifestyle scenarios (2026-04-30)
"""라이프스타일 시나리오 정의 — 마케팅 전략 문서 기반

Discovery 26FW: 4 content pillars
MLB 26SS: HIP FEMININE SPORTIVE 3 phases
"""

DISCOVERY_SCENARIOS = [
    {
        "id": "DX_RUN_01",
        "pillar": "running_life",
        "title": "출근 전 한강 러닝 후 카페",
        "hashtags": ["#러닝룩", "#러닝중간남동커피"],
        "prompt": """A young Korean woman in her mid-20s just finished a morning run along the Han River.
She's now standing outside a trendy cafe, catching her breath with a warm smile of accomplishment.

OUTFIT: Black and white colorblock half-zip hooded windbreaker (cropped, ending above waist),
black high-rise bike shorts showing toned legs, chunky trail running shoes, Discovery cap.
Small crossbody bag. Subtle D logo on chest.

SETTING: Early morning golden hour at a riverside cafe terrace. Modern cafe exterior with glass windows.
Han River path visible in background. Warm autumn light. Slight morning mist.

MOOD: Active yet stylish — the moment between workout and daily life. Healthy glow, natural dewy skin.
Expression: Serene confidence, natural post-workout radiance. Not posing — caught in a candid moment.

PHOTOGRAPHY: Shot on iPhone 16 Pro. Natural morning light. Slightly warm but not golden cast.
Full body shot. Candid street snap aesthetic. Real influencer feel.
Korean text visible on cafe signage is OK for authenticity.""",
    },
    {
        "id": "DX_RUN_02",
        "pillar": "running_life",
        "title": "러닝 크루와 함께 달리는 순간",
        "hashtags": ["#러닝룩", "#러닝크루"],
        "prompt": """A young Korean woman running on an urban trail path, mid-stride with athletic form.

OUTFIT: Olive green half-zip windbreaker (cropped), black compression leggings, white trail running shoes.
Hair in high ponytail, sweatband. Discovery logo visible on jacket chest.

SETTING: Autumn morning on a tree-lined running path in Seoul. Golden and red autumn leaves.
Urban park setting (like Seoul Forest or Olympic Park). Cool crisp air visible in breath.

MOOD: Dynamic active energy — in the zone, focused, athletic. Sporty chic in motion.
Expression: Focused and determined, natural athletic confidence.

PHOTOGRAPHY: Action shot, slight motion blur on legs. Full body, eye level.
Magazine editorial quality but authentic feel. Morning golden backlight.""",
    },
    {
        "id": "DX_RESORT_01",
        "pillar": "premium_resort",
        "title": "겨울 리조트 체크인",
        "hashtags": ["#프리미엄여행", "#프리미엄리조트"],
        "prompt": """A young Korean woman arriving at a premium winter resort, standing at the lobby entrance.

OUTFIT: Beige sand cropped short down jacket (semi-fitted, feminine silhouette, stand collar, full zip),
dark navy high-rise wide-leg pants, cream leather sneakers, minimal tote bag.
Hair in loose low ponytail. No hood — clean neckline.

SETTING: Upscale resort hotel lobby entrance. Glass doors, warm interior light spilling out.
Snow-covered landscape visible through windows. Pine trees. Premium mountain resort atmosphere.

MOOD: Premium leisure — elegant arrival moment. Warm and sophisticated, effortlessly chic.
Expression: Serene, quietly confident, relaxed travel mood.

PHOTOGRAPHY: Full body shot, eye level. Warm indoor/outdoor lighting transition.
Fashion editorial quality. Sharp focus. Natural skin texture.""",
    },
    {
        "id": "DX_RESORT_02",
        "pillar": "premium_resort",
        "title": "리조트 카페에서 커피 한잔",
        "hashtags": ["#프리미엄리조트", "#리조트커피"],
        "prompt": """A young Korean woman sitting at a resort cafe terrace, holding a warm latte.

OUTFIT: Cream cropped down jacket open over an ivory cashmere sweater, dark pants, ankle boots.
Minimal gold jewelry. Premium relaxed layering.

SETTING: Mountain resort outdoor cafe terrace. Wooden furniture, warm blankets on chairs.
Snowy mountains visible in background. Late afternoon winter light.

MOOD: Cozy premium leisure — the essence of a warm winter getaway. Quiet luxury moment.
Expression: Serene, content, gazing at the mountain view.

PHOTOGRAPHY: Medium shot, slightly candid angle. Warm natural light.
Lifestyle editorial. Coffee steam visible. Authentic but curated.""",
    },
    {
        "id": "DX_WELLNESS_01",
        "pillar": "active_wellness",
        "title": "필라테스 후 스트릿",
        "hashtags": ["#운동가는길OOTD", "#건강하고스포티한나"],
        "prompt": """A young Korean woman walking on a Seoul street after a pilates class, yoga mat bag on shoulder.

OUTFIT: Lavender crop top with Discovery logo, black high-rise bike shorts,
white oversized windbreaker tied around waist, white platform sneakers.
Hair in messy bun. Sunglasses pushed up on head.

SETTING: Trendy Seoul neighborhood (Seongsu/Hannam feel). Modern buildings, coffee shops.
Afternoon light. Urban but green — street trees visible.

MOOD: Active wellness lifestyle — the bridge between workout and social life.
Healthy, confident, owning the street in athleisure.
Expression: Cool confidence, walking with purpose, phone in hand.

PHOTOGRAPHY: Full body street snap, eye level. Natural afternoon light.
iPhone candid aesthetic. Urban lifestyle.""",
    },
    {
        "id": "DX_COMMUTE_01",
        "pillar": "commute_life",
        "title": "출근길 데일리룩",
        "hashtags": ["#데일리리틀", "#출근룩", "#겨울코디"],
        "prompt": """A young Korean woman walking to the office on a crisp winter morning in Gangnam.

OUTFIT: Beige sand cropped short down jacket (zipped to chin), dark grey pencil skirt (knee length),
black tights, Discovery padding boots (soft volume, round toe), structured tote bag.
Earphones in, phone in hand.

SETTING: Seoul Gangnam office district morning. Modern glass buildings, wide sidewalk.
Other commuters blurred in background. Crisp winter morning light, slightly cold atmosphere.

MOOD: Commute chic — warm, functional, but premium looking. Standing out from the crowd naturally.
Expression: Neutral focus, morning determination, quietly stylish.

PHOTOGRAPHY: Full body, slightly low angle emphasizing the silhouette. Morning sidelight.
Street photography style. Sharp focus on subject, bokeh background.""",
    },
]

MLB_SCENARIOS = [
    {
        "id": "MLB_SHOES_01",
        "phase": "shoes_bag",
        "title": "클라비 슈즈 포커스 — 성수 카페",
        "mood": "trendy_chic",
        "prompt": """A young Korean woman sitting on a cafe bench in Seongsu, Seoul, legs crossed to show off her shoes.

OUTFIT: Oversized cream blazer over white crop tee, grey wide-leg pants rolled up at ankle,
MLB Clavi sneakers in pink/mauve colorway (LOW PROFILE, chunky sole).
Small MLB monogram tote bag next to her. NY cap in beige.

SETTING: Trendy Seongsu cafe with industrial interior — exposed brick, concrete floors.
Natural light from large windows. Iced coffee on table.

MOOD: Trendy chic accessory focus — shoes and bag are the stars. Effortless cool girl.
Expression: Cool indifferent, looking at phone, one hand touching cap.

PHOTOGRAPHY: Medium shot, slightly low angle emphasizing shoes. Natural indoor light.
Sharp focus on shoes and bag, soft bokeh on face. Instagram-ready.
MLB logo clearly visible on shoes, bag, and cap.""",
    },
    {
        "id": "MLB_BALLET_01",
        "phase": "balletcore",
        "title": "발레코어 — 파리풍 거리",
        "mood": "feminine_elegant",
        "prompt": """A young Korean woman on a European-style street in Seoul, embodying balletcore femininity.

OUTFIT: White ribbon-detail crop top, pleated cream mini skirt (A-line, above knee),
MLB Mary Jane shoes in cream/beige, small structured crossbody bag.
NY cap in cream with subtle logo. Hair in low bun with ribbon.

SETTING: Parisian-vibe street in Seoul (like Garosu-gil or Bukchon).
Stone buildings, cafe awnings, flower shop. Soft afternoon light.

MOOD: HIP FEMININE — ballet-inspired elegance with MLB sporty edge.
Delicate but confident. The cap adds street credibility to the feminine look.
Expression: Serene, slightly playful, looking over shoulder.

PHOTOGRAPHY: Full body, eye level. Warm afternoon golden light.
Fashion editorial with candid touch. Soft color palette.
MLB branding visible but integrated into feminine aesthetic.""",
    },
    {
        "id": "MLB_BALLET_02",
        "phase": "balletcore",
        "title": "발레코어 — 스튜디오 감성",
        "mood": "feminine_elegant",
        "prompt": """A young Korean woman in a bright dance studio-like space, combining ballet grace with street attitude.

OUTFIT: Fitted cream knit crop top, white tennis mini skirt,
MLB ballet flat shoes in dusty pink with NY logo, cream nylon portfolio bag.
MLB cap in white, worn slightly tilted. Minimal gold earrings.

SETTING: Bright minimal studio space with large mirrors, wooden floors, ballet barre visible.
Clean white walls, natural daylight flooding in. Simple, elegant.

MOOD: FEMININE balletcore — graceful but with cool MLB attitude underneath.
Expression: Cool serene, chin slightly raised, confident gaze in mirror reflection.

PHOTOGRAPHY: Full body with mirror reflection visible. Natural studio daylight.
Clean composition. Soft tones — cream, white, dusty pink palette.
MLB logo subtle but visible on shoes, cap, and bag.""",
    },
    {
        "id": "MLB_SPORT_01",
        "phase": "sportive",
        "title": "HIP SPORTIVE — NYC 스트릿",
        "mood": "hip_sporty",
        "prompt": """A young Korean woman walking confidently on a NYC-inspired Seoul street, full hip sportive energy.

OUTFIT: White crop ringer tee with brown contrasting bands and NY logo on chest,
denim mini skirt with raw hem, brown MLB baseball cap worn low over eyes,
white chunky platform sneakers, small MLB crossbody bag in brown.

SETTING: Urban street with NYC vibes — concrete buildings, wide sidewalk,
parked cars, street signage. Late afternoon warm light casting long shadows.

MOOD: HIP FEMININE SPORTIVE at its peak — sporty, confident, owning the street.
This is THE KARINA energy — cool, indifferent, effortlessly trendy.
Expression: COOL stare, not smiling, slightly raised chin, cap shadow over eyes.

PHOTOGRAPHY: Full body, eye level, 3/4 angle. Strong afternoon sidelight.
High-fashion street style. Sharp focus. Cool color temperature.
NY logo PROMINENT on cap and tee — brand identity MUST dominate.
NO golden cast. Instagram editorial quality.""",
    },
    {
        "id": "MLB_SPORT_02",
        "phase": "sportive",
        "title": "HIP SPORTIVE — 루프탑 써머",
        "mood": "hip_sporty",
        "prompt": """A young Korean woman on a city rooftop, summer golden hour, radiating sporty confidence.

OUTFIT: Blue crop halter top with white MLB piping, matching blue bike shorts,
brown varsity jacket draped over shoulders (not worn), MLB cap in navy with white NY logo,
white runner sneakers, small MLB tote in the hand.

SETTING: Seoul rooftop with city skyline visible. Sunset golden hour.
Concrete rooftop floor, metal railing, distant buildings catching warm light.

MOOD: Sportive summer energy — athletic feminine cool. Workout-to-drinks transition.
The golden hour makes everything look premium.
Expression: Cool confidence, looking at city view, wind in hair.

PHOTOGRAPHY: Full body, slightly low angle emphasizing long legs against skyline.
Golden hour backlight creating rim light on hair and shoulders.
Cinematic quality. Warm but not oversaturated.
MLB branding visible — cap, top piping, bag.""",
    },
    {
        "id": "MLB_SPORT_03",
        "phase": "sportive",
        "title": "HIP SPORTIVE — 카리나 바이브 스트릿",
        "mood": "hip_sporty",
        "prompt": """A young Korean woman leaning against a concrete wall in an urban alley, pure KARINA attitude.

OUTFIT: Black varsity jacket (wool body, brown nylon sleeves) worn open over white crop tee,
grey cargo mini skirt with side pockets, platform sneakers in cream,
brown MLB cap pulled low, small structured bag.

SETTING: Urban back alley with concrete walls, metal fire escape stairs visible,
dim ambient lighting with one warm streetlight creating dramatic shadows.

MOOD: The definition of URBAN COOL — tough, hip, zero-effort attitude.
This is nighttime city energy, post-game swagger.
Expression: COOL INDIFFERENT — not smiling, direct stare, chin up, one hand in jacket pocket.

PHOTOGRAPHY: Full body, eye level. Dramatic urban lighting — warm streetlight + cool ambient.
High contrast. Fashion editorial quality with street grit.
NY logo and team number patch clearly visible on jacket.
Cap shadow adding mystery to the face.""",
    },
]
