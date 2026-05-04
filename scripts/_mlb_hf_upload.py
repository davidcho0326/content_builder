"""PUT 18 MLB ref jpegs to HF presigned URLs."""
import sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.stdout.reconfigure(encoding="utf-8")

MAPPING = [
    ("S01_cheer_line_R01_ref.jpg", "289ed616-9920-4425-9580-95dbb771aa35", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/289ed616-9920-4425-9580-95dbb771aa35.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=22aee4b448fd214c1d9bee87aa73a7116998e84682f28cf15e7869bf7c173a5f"),
    ("S01_cheer_line_R02_ref.jpg", "6a69140a-af25-422a-89cd-5ffcf8f2f322", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/6a69140a-af25-422a-89cd-5ffcf8f2f322.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=f805f59c3b7890e86735cffc09fabf4a98cddb7f54fd2619b768f60bc78c3d5b"),
    ("S01_cheer_line_R03_ref.jpg", "07d69113-cfce-4415-8683-bfbc9a707f51", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/07d69113-cfce-4415-8683-bfbc9a707f51.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=feedb619a3657d70c6055309e99c594f65fa11b8baff942bea7f62022d7a29b1"),
    ("S01_cheer_line_R04_ref.jpg", "8c9b9739-4103-4909-9def-9a38d0209b32", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/8c9b9739-4103-4909-9def-9a38d0209b32.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=06bd598cd7e1b8f178bb5e29ba32af06e6353bba56bf2f878e9c9e3d5e12fd42"),
    ("S01_cheer_line_R05_ref.jpg", "22b99807-3df4-4345-be60-f8f69bf4b5a9", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/22b99807-3df4-4345-be60-f8f69bf4b5a9.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=6ff6ff4903cd6f88e90e14160b1655ee438718d42afc53d1dfde8afecc55ccbc"),
    ("S01_cheer_line_R06_ref.jpg", "cf176fa0-e764-4ec4-9ad5-6c8f4b226c68", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/cf176fa0-e764-4ec4-9ad5-6c8f4b226c68.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=8b1ef85a3afbbbf709404758bc8c4f29a7928b3bd20049ab28512efd3c29fe47"),
    ("S02_daylight_wave_R01_ref.jpg", "06f32ae0-8e47-4fb8-8db0-dca7a861c18f", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/06f32ae0-8e47-4fb8-8db0-dca7a861c18f.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=d1e1ade390970cf3a073efabda03416461e8b020cb3b7cab6ef22de4f7eea701"),
    ("S02_daylight_wave_R02_ref.jpg", "0d0fcfe5-bc4b-4e36-a591-60c05a69c25e", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/0d0fcfe5-bc4b-4e36-a591-60c05a69c25e.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=c9b161481f995a20c982b9f380baed20db73bb6e2ad4fdc11ca56131826dfa73"),
    ("S02_daylight_wave_R03_ref.jpg", "6bd4af25-1141-4b57-97e9-25b11143936a", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/6bd4af25-1141-4b57-97e9-25b11143936a.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=bdddb657532292e5870911e39c96657d5e4cb80e153ed084e079ad51b60674a1"),
    ("S02_daylight_wave_R04_ref.jpg", "9775d286-3ace-4a43-802e-e327391715c4", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/9775d286-3ace-4a43-802e-e327391715c4.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=9e773e8399ace3e6bef145398e7a6efbbdd13823cd0a62544d2d259eff9a4972"),
    ("S02_daylight_wave_R05_ref.jpg", "fd69b0e5-08c3-4399-b298-bb17906808a3", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/fd69b0e5-08c3-4399-b298-bb17906808a3.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=7c38bf96dc26f1b5b0b028755b1c5157cd1c159beff52f746de428ae0c4f9957"),
    ("S02_daylight_wave_R06_ref.jpg", "6c1192a6-3493-4918-b357-a54117436fc0", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/6c1192a6-3493-4918-b357-a54117436fc0.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=28d7139494ee4abfdf00a65a9274e72fd5142f632c0dc8bb1287100096c2be9d"),
    ("S03_dugout_backstage_R01_ref.jpg", "660f5fcb-4878-4e69-b3c8-8ded0abc2408", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/660f5fcb-4878-4e69-b3c8-8ded0abc2408.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=41e13cc6f9ca15e351adb7ee71cdc2e79fb6e3f017d34b38dc454bc8de8b1027"),
    ("S03_dugout_backstage_R02_ref.jpg", "aee54b9c-a92c-4202-b738-4cc68b126172", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/aee54b9c-a92c-4202-b738-4cc68b126172.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=31bcb6c77d22552d9152d20d995023d8076025aaf748358d3cbcf7e0686065b2"),
    ("S03_dugout_backstage_R03_ref.jpg", "fe9597dd-18fb-4124-9a25-0058b40c6f36", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/fe9597dd-18fb-4124-9a25-0058b40c6f36.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=27b319e210765f75b997126f1fe62c602d52ffa917a2a3ed15a2228289b4ba9d"),
    ("S03_dugout_backstage_R04_ref.jpg", "2a48926f-31d1-4256-a694-289bafdaa6ed", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/2a48926f-31d1-4256-a694-289bafdaa6ed.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=e844485b832a9597c8377805b2250d523e5de8086ef67e6f6987885bb8d7afdf"),
    ("S03_dugout_backstage_R05_ref.jpg", "12f6daf4-e96c-4b13-a0c1-259deb412335", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/12f6daf4-e96c-4b13-a0c1-259deb412335.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=224369b91a7b57b572b384437ff34825f1ff6516b9612fa14eaefb1ba990fc11"),
    ("S03_dugout_backstage_R06_ref.jpg", "85741967-0724-4a31-82f5-3b0a909c37e2", "https://d276s3zg8h21b2.cloudfront.net/user_3456Ryv8DqFsfImeWSxwf5W66pv/85741967-0724-4a31-82f5-3b0a909c37e2.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAYPNTVMCGYPZMTKFK%2F20260503%2Feu-north-1%2Fs3%2Faws4_request&X-Amz-Date=20260503T155642Z&X-Amz-Expires=86400&X-Amz-SignedHeaders=content-type%3Bhost&X-Amz-Signature=6b7e73a3c44a24d21c8f20a37d6b0a8288c75ebe9a447c0a2414d97f168a5652"),
]
IMGS_DIR = Path("st_cut-dev/results/mlb/imc_driven/20260503_MLB_27SS_20260504_005525/03_images")


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
ok = sum(1 for _,_,s in results if s in (200,204))
print(f"uploaded: {ok}/{len(results)}")
mp = {fn: mid for fn, mid, _ in MAPPING}
(IMGS_DIR / "_hf_media_map.json").write_text(json.dumps(mp, indent=2), encoding="utf-8")
