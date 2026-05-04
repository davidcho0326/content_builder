"""One-off: PUT 18 ref jpegs to HF presigned URLs and save media map."""
import sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.stdout.reconfigure(encoding="utf-8")

MAPPING = [
    ("S01_the_morning_veranda_in_como_R01_ref.jpg", "52d2eadd-f4c2-416c-ae99-7e011624608d", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/52d2eadd-f4c2-416c-ae99-7e011624608d.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141821Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=d1c34e05feb9b9003496b18f411465ace94274f278c2fb44ca074c6f6a4d650c"),
    ("S01_the_morning_veranda_in_como_R02_ref.jpg", "6711d362-ae5a-4248-b67b-02d468e8c7b8", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/6711d362-ae5a-4248-b67b-02d468e8c7b8.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141821Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=4feb647b1927751cd68f80ae387688f8e38d977238ad0576769414a70cbe6d75"),
    ("S01_the_morning_veranda_in_como_R03_ref.jpg", "1765f831-475b-434d-9c21-312dfe3b8871", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/1765f831-475b-434d-9c21-312dfe3b8871.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=1b7c35e4911c970901b953da090a17e85d84aa41e3d09b8070b3bcea22471a77"),
    ("S01_the_morning_veranda_in_como_R04_ref.jpg", "b08026b1-c4df-4ecb-a77d-b34fb11a545d", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/b08026b1-c4df-4ecb-a77d-b34fb11a545d.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=9a4db6e679627939008de16e98b1b0f878c2083f042b1304f66604fb57b34727"),
    ("S01_the_morning_veranda_in_como_R05_ref.jpg", "e5ae0e87-9612-4bb2-8670-5d483233d411", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/e5ae0e87-9612-4bb2-8670-5d483233d411.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=8040398cfcb5dcdf18c1bcb77d258240abd5938ab11fb0e79fb67ddcb9573e09"),
    ("S01_the_morning_veranda_in_como_R06_ref.jpg", "ce5545d3-fea9-4d7c-baf6-cd2fb745fcdd", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/ce5545d3-fea9-4d7c-baf6-cd2fb745fcdd.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=a3904cb9438b950ab15dbf27c64f25fb165feed17a48a17cee943a43b1854e7f"),
    ("S02_private_deck_the_yachting_navy_R01_ref.jpg", "f1715633-0634-402a-adf4-ec8e3df660e4", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/f1715633-0634-402a-adf4-ec8e3df660e4.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=cef64d998f630c6cca0748fed908ebff437a1ad3da84ab097c3da78d4278f3af"),
    ("S02_private_deck_the_yachting_navy_R02_ref.jpg", "73ecfbef-aadd-4681-8b88-b84cff2bebca", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/73ecfbef-aadd-4681-8b88-b84cff2bebca.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=f7210570d8c522fcf8e1095f48bfbcbb1ee60c44c4fb083da01c57dee16f6860"),
    ("S02_private_deck_the_yachting_navy_R03_ref.jpg", "831cd232-23a2-4ae8-8a5a-b5f8266d7aad", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/831cd232-23a2-4ae8-8a5a-b5f8266d7aad.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=02cd297b9a04254548f01cdf5a63a181a6d0702d98e6ac4c7f25c164814a8bf4"),
    ("S02_private_deck_the_yachting_navy_R04_ref.jpg", "1c8a59d2-d860-47b9-83fe-9b22e4ddf188", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/1c8a59d2-d860-47b9-83fe-9b22e4ddf188.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=323d20556485981a1c18a66b6ce1b6df1abf9e525dee480aacb03cf6ea4d0115"),
    ("S02_private_deck_the_yachting_navy_R05_ref.jpg", "986116a4-a3e3-4cf2-8e5b-e7ff8d87b41d", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/986116a4-a3e3-4cf2-8e5b-e7ff8d87b41d.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=d17eeaeee0f553bc0d6c36989b5c894fec79041933e7b51f43f4ac11e627fff9"),
    ("S02_private_deck_the_yachting_navy_R06_ref.jpg", "af4c4d2c-0756-4228-8fc7-49ffbd19d0df", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/af4c4d2c-0756-4228-8fc7-49ffbd19d0df.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=46519a084331e4a26fc9de84b12b993b3236eb7070a5d18a9aa4ad7331e58ab0"),
    ("S03_the_italian_garden_soir_e_R01_ref.jpg", "cab734c9-7e86-471e-a83b-eb1fc37f5278", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/cab734c9-7e86-471e-a83b-eb1fc37f5278.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=552c32006e02e0eb67ab7cd135a2164a1dd5ce3f1100d3066bd72108768d97cb"),
    ("S03_the_italian_garden_soir_e_R02_ref.jpg", "e34665ac-a3bf-4a8b-8703-26b076b593ca", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/e34665ac-a3bf-4a8b-8703-26b076b593ca.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=49b29caedb6d301589e113a63ae98c4ab567d7762c6f57f4fae84631ee823e58"),
    ("S03_the_italian_garden_soir_e_R03_ref.jpg", "f7d5753b-0976-4779-a157-8f07cf5ec0cc", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/f7d5753b-0976-4779-a157-8f07cf5ec0cc.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=672a1882ca63bf69dbc3f182620aa30a30e74f1d9aa2ac58294eaaabdaaf15e7"),
    ("S03_the_italian_garden_soir_e_R04_ref.jpg", "155ba48a-1277-49ec-8402-c8d07d6b6e67", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/155ba48a-1277-49ec-8402-c8d07d6b6e67.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=f5cd7c1dfb07f22c61f2134471a922e8724c31d2fcfd64522885e935fd98dacf"),
    ("S03_the_italian_garden_soir_e_R05_ref.jpg", "c906cd0d-469b-4be5-bdea-baf7588628a6", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/c906cd0d-469b-4be5-bdea-baf7588628a6.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=94dd1f45446c1552ef335c3fa2c2184df8564043c20f92f308c167aa3111c606"),
    ("S03_the_italian_garden_soir_e_R06_ref.jpg", "dc00bfbb-89fc-4d41-b18d-58da0529b83d", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/dc00bfbb-89fc-4d41-b18d-58da0529b83d.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T141822Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=d5125a37ad838e624feee6ee321be8b3428f221996ef91a6a53fb221b85da7cd"),
]

IMGS_DIR = Path("st_cut-dev/results/dv/imc_driven/20260503_DV_27SS_20260503_231654/03_images")


def upload_one(item):
    fn, mid, url = item
    body = (IMGS_DIR / fn).read_bytes()
    r = requests.put(url, data=body,
                      headers={"Content-Type": "image/jpeg"}, timeout=120)
    return (fn, mid, r.status_code)


results = []
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = [ex.submit(upload_one, x) for x in MAPPING]
    for fu in as_completed(futs):
        results.append(fu.result())

ok = sum(1 for _, _, s in results if s in (200, 204))
print(f"uploaded: {ok}/{len(results)}")
for fn, mid, s in results:
    if s not in (200, 204):
        print(f"  FAIL {fn}: {s}")

mapping_dict = {fn: mid for fn, mid, _ in MAPPING}
(IMGS_DIR / "_hf_media_map.json").write_text(
    json.dumps(mapping_dict, indent=2), encoding="utf-8"
)
print("media map saved")
