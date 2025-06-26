from flask import Flask, render_template, request, send_file, after_this_request, make_response
import yt_dlp
import os
import tempfile
import uuid
import re
import time
import requests

app = Flask(__name__)

# ----------------------------------------
# Common yt-dlp options (with sleep)
# ----------------------------------------
COMMON_YDL_OPTS = {
    'quiet': True,
    'nocheckcertificate': True,
    'geo_bypass': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    },
    'sleep_interval_requests': 0.5,
    'sleep_interval': 0.5,
}

def get_invidious_instances():
    """Fetch the current list of active Invidious instances, fallback to hard-coded."""
    try:
        resp = requests.get("https://api.invidious.io/instances.json?sort=users", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [inst["instanceApi"] for inst in data if inst.get("instanceApi")]
    except Exception:
        return [
            "https://yewtu.be",
            "https://yewtu.cafe",
            "https://yewtu.xyz"
        ]

def fetch_info_invidious_dynamic(url, max_attempts=3):
    """Try multiple Invidious front-ends until one returns metadata."""
    instances = get_invidious_instances()
    for base in instances:
        opts = COMMON_YDL_OPTS.copy()
        opts["extractor_args"] = {"youtube": {"base_address": base}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False), base
        except Exception:
            time.sleep(1)
            continue
    raise RuntimeError("All Invidious instances failed.")

@app.route('/', methods=['GET', 'POST'])
def index():
    video_info = None
    formats = []
    error = None

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            info_dict, instance = fetch_info_invidious_dynamic(url)
            formats = [
                f for f in info_dict.get('formats', [])
                if f.get('vcodec') != 'none'
                and f.get('ext') == 'mp4'
                and f.get('height') is not None
                and (f.get('filesize') or f.get('filesize_approx'))
            ]
            formats = sorted(formats, key=lambda x: x.get('height', 0), reverse=True)
            video_info = {
                'title': info_dict.get('title'),
                'id': info_dict.get('id'),
                'url': url,
                'instance': instance
            }
        except Exception as e:
            error = f"❌ Failed to fetch video info: {e}"

    return render_template('index.html', video_info=video_info, formats=formats, error=error)

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url', '').strip()
    format_id = request.form.get('format_id', '')
    is_audio = (format_id == 'audio-mp3')

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Fetch metadata once to get title
    try:
        info_dict, instance = fetch_info_invidious_dynamic(url)
        video_title = info_dict.get("title", "video")
        video_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
    except Exception as e:
        return f"<h3>Error fetching metadata: {e}</h3><p><a href='/'>Go Back</a></p>"

    temp_dir = tempfile.mkdtemp()
    ext = 'mp3' if is_audio else 'mp4'
    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")

    # Try downloading via each Invidious instance until one succeeds
    instances = get_invidious_instances()
    download_success = False
    last_error = None

    for base in instances:
        opts = COMMON_YDL_OPTS.copy()
        opts.update({
            'outtmpl': file_path,
            'noplaylist': True,
            'merge_output_format': ext,
            'extractor_args': {'youtube': {'base_address': base}}
        })
        if is_audio:
            opts.update({
                'format': 'bestaudio',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            })
        else:
            opts['format'] = f"{format_id}+bestaudio/best"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            download_success = True
            break
        except Exception as e:
            last_error = e
            time.sleep(1)

    if not download_success:
        return f"<h3>Error downloading: {last_error}</h3><p><a href='/'>Go Back</a></p>"

    @after_this_request
    def cleanup(response):
        try:
            os.remove(file_path)
            os.rmdir(temp_dir)
        except Exception:
            pass
        return response

    return make_response(send_file(
        file_path,
        mimetype='audio/mpeg' if is_audio else 'video/mp4',
        as_attachment=True,
        download_name=f"{video_title}.{ext}"
    ))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)








