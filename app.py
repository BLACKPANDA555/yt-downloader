from flask import Flask, render_template, request, send_file, after_this_request, make_response
import yt_dlp
import os
import tempfile
import uuid
import re
import time

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
    # 1) pause between web requests and after downloads
    'sleep_interval_requests': 0.5,
    'sleep_interval': 0.5,
}

def fetch_info_with_retries(url, ydl_opts, max_attempts=3):
    """Try extract_info up to max_attempts times, backing off on 429 errors."""
    for attempt in range(1, max_attempts + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            msg = str(e)
            # only retry on Too Many Requests
            if '429' in msg or 'Too Many Requests' in msg:
                wait = 1 * attempt  # 1s, 2s, 3s
                time.sleep(wait)
                continue
            # other errors should surface immediately
            raise
    # if all retries failed
    raise yt_dlp.utils.DownloadError("429 Too Many Requests after retries")

@app.route('/', methods=['GET', 'POST'])
def index():
    video_info = None
    formats = []
    error = None

    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # build options and fetch metadata with retries
        ydl_opts = COMMON_YDL_OPTS.copy()

        try:
            info_dict = fetch_info_with_retries(url, ydl_opts)
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
                'url': url
            }

        except Exception as e:
            error = f"❌ Failed to fetch video info: {str(e)}"

    return render_template('index.html', video_info=video_info, formats=formats, error=error)

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url', '').strip()
    format_id = request.form.get('format_id', '')
    is_audio = (format_id == 'audio-mp3')

    # ensure https
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # prepare temp file
    temp_dir = tempfile.mkdtemp()
    ext = 'mp3' if is_audio else 'mp4'
    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")

    # build download options
    ydl_opts = COMMON_YDL_OPTS.copy()
    ydl_opts.update({
        'outtmpl': file_path,
        'noplaylist': True,
        'merge_output_format': ext,
    })

    if is_audio:
        ydl_opts.update({
            'format': 'bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        })
    else:
        ydl_opts['format'] = f"{format_id}+bestaudio/best"

    try:
        # download with retries for metadata first (optional)
        info = fetch_info_with_retries(url, ydl_opts)
        # now perform actual download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        video_title = info.get("title", "video")
        video_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
    except Exception as e:
        return f"<h3>Error: {str(e)}</h3><p><a href='/'>Go Back</a></p>"

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









