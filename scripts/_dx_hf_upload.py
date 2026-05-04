"""PUT 18 DX ref jpegs to HF presigned URLs."""
import sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.stdout.reconfigure(encoding="utf-8")

MAPPING = [
    ("S01_first_light_R01_ref.jpg", "b1ffba10-52ab-4272-915a-078aae516394", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/b1ffba10-52ab-4272-915a-078aae516394.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=840552f1ab7758ec6a07387de9c3824670339d1217e79de72ca276f08d3bd62f"),
    ("S01_first_light_R02_ref.jpg", "57c80ccb-96d2-4d6b-a0b6-5cc41bd2149c", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/57c80ccb-96d2-4d6b-a0b6-5cc41bd2149c.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=5ee4f6ee10934cebf6aa7ec2f159dd3de35a08412455dd4f8ba328bd4e8abfc2"),
    ("S01_first_light_R03_ref.jpg", "142ce5e5-733e-4694-a083-1a6b9aaf966b", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/142ce5e5-733e-4694-a083-1a6b9aaf966b.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=cb9856354c9b7e3dc6ea76a5219d1c3d532bf0b10ea7f622c154729ecdbb52c5"),
    ("S01_first_light_R04_ref.jpg", "bbd89418-4eb2-42d6-aa1e-d2b6c3d143ac", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/bbd89418-4eb2-42d6-aa1e-d2b6c3d143ac.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=dccb43de8588fe992c4e3553404e30c81d381e06ca08cee6cfcc1fb30ba11d3b"),
    ("S01_first_light_R05_ref.jpg", "57019fe5-568f-4e76-b299-1b23bdafacd6", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/57019fe5-568f-4e76-b299-1b23bdafacd6.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=ce4e6a5a8c0d25dfd439af53b79d549da42c606f96091bb07c7f72539923105f"),
    ("S01_first_light_R06_ref.jpg", "2447843d-5540-4c60-870e-fa54f7cbcc48", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/2447843d-5540-4c60-870e-fa54f7cbcc48.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=6aa5a39f5939a04ba540689ec6d67ffd85b4ca3feac311dfc94c5e1cfee278b1"),
    ("S02_caf_transit_R01_ref.jpg", "bc961778-aa59-4616-bcba-bf4773d014b2", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/bc961778-aa59-4616-bcba-bf4773d014b2.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=93946444e25796e14d3ef8ba4414557fbd4b64f97f85353817aad4ecdc836fb6"),
    ("S02_caf_transit_R02_ref.jpg", "6f91fc81-5edb-47bd-97ad-6e22482d8f13", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/6f91fc81-5edb-47bd-97ad-6e22482d8f13.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=b419f76cfbfa2d9f034a486a46825b84778fe69805fdfd35ddd9f3465308664e"),
    ("S02_caf_transit_R03_ref.jpg", "e2baf22e-9239-457f-913f-ea4620b3585a", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/e2baf22e-9239-457f-913f-ea4620b3585a.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=c333b1694972222faa40b46f537ef94508b872586d5b6ea4be03ff89e48f6ecd"),
    ("S02_caf_transit_R04_ref.jpg", "af918a9b-5eb4-4c09-9f1d-356e4327b2aa", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/af918a9b-5eb4-4c09-9f1d-356e4327b2aa.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=831891ea25a9a59773b2f42f5bba40de584b6e3c79384410226c681f4c2ce534"),
    ("S02_caf_transit_R05_ref.jpg", "16e89f7f-3def-4719-b2f8-02ffaa6ce0bc", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/16e89f7f-3def-4719-b2f8-02ffaa6ce0bc.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=aa5232f61c4b416b8ee876c4c0e0790695e16f00e781fbdabf31df7dd38a5854"),
    ("S02_caf_transit_R06_ref.jpg", "288113af-bc5f-4aec-8528-4e4b0976a933", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/288113af-bc5f-4aec-8528-4e4b0976a933.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=685bfb08949087c3c5d01c4dc30f2abe93ba64c8770e4b0d4caede78861f1744"),
    ("S03_office_glow_R01_ref.jpg", "3af507c0-a1da-42ce-9546-3314a193b2d8", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/3af507c0-a1da-42ce-9546-3314a193b2d8.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=0f8bc9e5652ec810cbf922f757bbfc46f5a0e4c81dc191663beb5395c72f379d"),
    ("S03_office_glow_R02_ref.jpg", "0612554d-3806-4e50-83cf-d073ce40d047", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/0612554d-3806-4e50-83cf-d073ce40d047.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=7071b47b859fa1aaa598eaddc7075e922fba024fb45b5637b45c0853a090eff4"),
    ("S03_office_glow_R03_ref.jpg", "865109f1-b93e-4176-838e-c46ab448527e", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/865109f1-b93e-4176-838e-c46ab448527e.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=35d5e23e7aa3bf1150e17061a3a3e3deac54978854d0b6e88a48aee82f5e31f9"),
    ("S03_office_glow_R04_ref.jpg", "a102c766-c28f-4f12-8efc-6667baca8dbd", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/a102c766-c28f-4f12-8efc-6667baca8dbd.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=d6b806a32196ae335b302b688ce30fcc0da2d1ee36434b7dac8bf2663567d565"),
    ("S03_office_glow_R05_ref.jpg", "6636a76a-40b8-44cf-87e0-acf7c9e7cd07", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/6636a76a-40b8-44cf-87e0-acf7c9e7cd07.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=7e0731063a1a2658aeba3b494088820ae43e87d3981fb017ca7df90ef991e223"),
    ("S03_office_glow_R06_ref.jpg", "587b3fd2-6edc-49c1-ba36-c8e880eca5ca", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/587b3fd2-6edc-49c1-ba36-c8e880eca5ca.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T154012Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=adfac75227baf29b8db6d2537c9da6b8d65fcdd53d0c11203a6cc37faa77ff99"),
]
IMGS_DIR = Path("st_cut-dev/results/dx/imc_driven/20260503_DX_26FW_20260504_003900/03_images")


def upload_one(item):
    fn, mid, url = item
    body = (IMGS_DIR / fn).read_bytes()
    r = requests.put(url, data=body, headers={"Content-Type": "image/jpeg"}, timeout=120)
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

mp = {fn: mid for fn, mid, _ in MAPPING}
(IMGS_DIR / "_hf_media_map.json").write_text(json.dumps(mp, indent=2), encoding="utf-8")
print("media map saved")
