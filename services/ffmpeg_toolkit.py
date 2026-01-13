# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



import os
import ffmpeg
import requests
import subprocess
import json
from services.file_management import download_file

# Set the default local storage directory
STORAGE_PATH = "/tmp/"

def get_file_info(file_path):
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        '-analyzeduration', '100M',
        '-probesize', '100M',
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    
    has_video = any(s['codec_type'] == 'video' for s in data.get('streams', []))
    has_audio = any(s['codec_type'] == 'audio' for s in data.get('streams', []))
    duration = float(data['format']['duration'])
    
    return has_video, has_audio, duration

def process_conversion(media_url, job_id, bitrate='128k', webhook_url=None):
    """Convert media to MP3 format with specified bitrate."""
    input_filename = download_file(media_url, os.path.join(STORAGE_PATH, f"{job_id}_input"))
    output_filename = f"{job_id}.mp3"
    output_path = os.path.join(STORAGE_PATH, output_filename)

    try:
        # Convert media file to MP3 with specified bitrate
        (
            ffmpeg
            .input(input_filename)
            .output(output_path, acodec='libmp3lame', audio_bitrate=bitrate)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        os.remove(input_filename)
        print(f"Conversion successful: {output_path} with bitrate {bitrate}")

        # Ensure the output file exists locally before attempting upload
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Output file {output_path} does not exist after conversion.")

        return output_path

    except Exception as e:
        print(f"Conversion failed: {str(e)}")
        raise

def process_video_combination(media_urls, job_id, webhook_url=None):
    """Combine multiple videos into one."""
    input_files = []
    output_filename = f"{job_id}.mp4"
    output_path = os.path.join(STORAGE_PATH, output_filename)

    try:
        # Download all media files
        for i, media_item in enumerate(media_urls):
            url = media_item['video_url']
            input_filename = download_file(url, os.path.join(STORAGE_PATH, f"{job_id}_input_{i}"))
            input_files.append(input_filename)

        # Use the concat filter to concatenate the videos
        # This re-encodes the video, preventing issues with mismatched streams/codecs
        # and "black screen" at the end.
        # We also scale all inputs to 1920x1080 to prevent resolution mismatch errors.
        input_streams = []
        for f in input_files:
            has_video, has_audio, duration = get_file_info(f)
            
            if not has_video:
                print(f"Warning: File {f} has no video stream. Skipping.")
                continue

            inp = ffmpeg.input(f)
            # Scale video stream to 1920x1080, forcing aspect ratio if needed (padding could be added here for better results, but scale is simpler)
            # setsar=1 prevents Aspect Ratio issues when concatenating
            v = inp.video.filter('scale', 1920, 1080).filter('setsar', 1)
            
            if has_audio:
                a = inp.audio
            else:
                # Generate silent audio of the same duration
                a = ffmpeg.input('anullsrc=channel_layout=stereo:sample_rate=44100', format='lavfi').audio.filter('atrim', duration=duration)
            
            input_streams.append(v)
            input_streams.append(a)

        try:
            (
                ffmpeg
                .concat(*input_streams, v=1, a=1)
                .output(output_path)
                .run(overwrite_output=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            print(f"FFmpeg error: {e.stderr.decode('utf8')}")
            raise e

        # Clean up input files
        for f in input_files:
            os.remove(f)

        print(f"Video combination successful: {output_path}")

        # Check if the output file exists locally before upload
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Output file {output_path} does not exist after combination.")

        return output_path
    except Exception as e:
        print(f"Video combination failed: {str(e)}")
        raise 
