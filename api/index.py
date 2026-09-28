from flask import Flask, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import json
import io

app = Flask(__name__)


def fetch_snapchat_profile(username):
    username = username.lower().replace("@", "").strip()

    result = try_web_api(username)
    if result:
        return result

    result = try_next_data(username)
    if result:
        return result

    result = try_html_meta(username)
    if result:
        return result

    return None


def try_web_api(username):
    url = f"https://www.snapchat.com/web-api/v1/public-profile/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": f"https://www.snapchat.com/add/{username}",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            profile = data.get("data", {}).get("me", {}) or data.get("data", {})
            if profile.get("username"):
                return normalize(profile, username)
    except Exception as e:
        print(f"⚠️ Web API failed: {e}")
    return None


def try_next_data(username):
    url = f"https://www.snapchat.com/add/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script:
            return None
        data = json.loads(script.string)
        profile = extract_profile_from_next(data, username)
        if profile:
            return normalize(profile, username)
    except Exception as e:
        print(f"⚠️ Next data failed: {e}")
    return None


def extract_profile_from_next(data, username):
    def find_profile(obj, depth=0):
        if depth > 10:
            return None
        if isinstance(obj, dict):
            if obj.get("username", "").lower() == username:
                return obj
            for v in obj.values():
                r = find_profile(v, depth + 1)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = find_profile(item, depth + 1)
                if r:
                    return r
        return None
    return find_profile(data)


def try_html_meta(username):
    url = f"https://www.snapchat.com/add/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        profile = {"username": username}

        og_title = soup.find("meta", {"property": "og:title"})
        if og_title:
            profile["display_name"] = og_title.get("content", "").replace(" | Snapchat", "")

        og_desc = soup.find("meta", {"property": "og:description"})
        if og_desc:
            profile["bio"] = og_desc.get("content", "")

        og_img = soup.find("meta", {"property": "og:image"})
        if og_img:
            profile["profile_picture"] = og_img.get("content", "")

        if profile.get("display_name") or profile.get("bio"):
            return normalize(profile, username)
    except Exception as e:
        print(f"⚠️ HTML meta failed: {e}")
    return None


def normalize(profile, username):
    pic = (
        profile.get("profile_picture")
        or profile.get("profilePictureUrl")
        or profile.get("bitmoji_avatar")
        or profile.get("bitmoji")
        or ""
    )

    return {
        "username": profile.get("username") or username,
        "display_name": (
            profile.get("display_name")
            or profile.get("displayName")
            or profile.get("title")
            or profile.get("name")
            or "N/A"
        ),
        "verified": "Yes" if (
            profile.get("verified")
            or profile.get("isVerified")
            or profile.get("is_verified")
        ) else "No",
        "subscribers": str(
            profile.get("subscriber_count")
            or profile.get("subscriberCount")
            or profile.get("subscribers")
            or 0
        ),
        "bio": (
            profile.get("bio")
            or profile.get("description")
            or profile.get("bioText")
            or "Not search my profile"
        ),
        "profile_link": f"https://www.snapchat.com/add/{username}",
        "profile_picture": pic,
        "snapcode": profile.get("snapcode") or f"https://app.snapchat.com/web/deeplink/snapcode?username={username}&type=SVG&bitmoji=enable",
        "category": profile.get("category") or "",
        "website": profile.get("website") or profile.get("websiteUrl") or "",
    }


# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    return jsonify({"status": "ok", "service": "Snapchat Lookup API"})


@app.route('/api/snap/<username>')
@app.route('/snap/<username>')
def snap_lookup(username):
    try:
        data = fetch_snapchat_profile(username)
        if not data:
            return jsonify({
                "success": False,
                "error": "User not found or Snapchat blocked the request"
            }), 404

        return jsonify({"success": True, "data": data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/snap/<username>/photo')
@app.route('/snap/<username>/photo')
def snap_photo(username):
    try:
        data = fetch_snapchat_profile(username)
        if not data or not data.get("profile_picture"):
            return jsonify({"error": "No photo"}), 404

        img_url = data["profile_picture"]
        r = requests.get(img_url, timeout=10)
        if r.status_code == 200:
            return send_file(
                io.BytesIO(r.content),
                mimetype=r.headers.get("Content-Type", "image/jpeg")
            )
        return jsonify({"error": "Failed to fetch image"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
