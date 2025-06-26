from flask import Flask, render_template, request, send_file, after_this_request, make_response
import yt_dlp
import os
import tempfile
import uuid
import re

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    video_info = None
    formats = []
    error = None

    if request.method == 'POST':
        url = request.form.get('url', '').strip()

        ydl_opts = {'quiet': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
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

    is_audio = format_id == 'audio-mp3'

    temp_dir = tempfile.mkdtemp()
    ext = 'mp3' if is_audio else 'mp4'
    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")

    ydl_opts = {
        'outtmpl': file_path,
        'quiet': False,
        'noplaylist': True,
        'merge_output_format': ext,
    }

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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get("title", "video")
            video_title = re.sub(r'[\\/*?:"<>|]', "_", video_title)
    except Exception as e:
        return f"<h3>Error: {str(e)}</h3><p><a href='/'>Go Back</a></p>"

    @after_this_request
    def cleanup(response):
        try:
            os.remove(file_path)
            os.rmdir(temp_dir)
        except Exception as e:
            print(f"[Cleanup Error] {e}")
        return response

    return make_response(send_file(
        file_path,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=f"{video_title}.{ext}"
    ))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
