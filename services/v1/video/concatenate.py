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
import concurrent.futures
from services.file_management import download_file
from config import LOCAL_STORAGE_PATH

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
    
    video_stream = next((s for s in data.get('streams', []) if s['codec_type'] == 'video'), None)
    
    has_video = video_stream is not None
    has_audio = any(s['codec_type'] == 'audio' for s in data.get('streams', []))
    duration = float(data['format']['duration'])
    
    # Extrai a largura e altura originais do vídeo
    width = int(video_stream['width']) if video_stream else 0
    height = int(video_stream['height']) if video_stream else 0
    
    return has_video, has_audio, duration, width, height

def process_video_concatenate(media_urls, job_id, webhook_url=None):
    """Combine multiple videos into one."""
    input_files = []
    output_filename = f"{job_id}.mp4"
    output_path = os.path.join(LOCAL_STORAGE_PATH, output_filename)

    try:
        # Download all media files
        for i, media_item in enumerate(media_urls):
            url = media_item['video_url']
            input_filename = download_file(url, os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_input_{i}"))
            input_files.append(input_filename)

        # Detecção automática de resolução baseada no primeiro vídeo
        target_w, target_h = 1080, 1920 # Valor padrão (vertical) por segurança
        if input_files:
            _, _, _, first_w, first_h = get_file_info(input_files[0])
            if first_w > 0 and first_h > 0:
                target_w, target_h = first_w, first_h

        # Optimization: Normalize videos in parallel then concat stream-copy
        # This avoids the O(N) complexity of filter graphs and speeds up processing significantly
        normalized_files = [None] * len(input_files)
        
        def normalize_task(index, input_file):
            output_file = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_norm_{index}.ts")
            try:
                has_video, has_audio, duration, _, _ = get_file_info(input_file)
                if not has_video:
                    print(f"Warning: File {input_file} has no video stream. Skipping.")
                    return None
                
                inp = ffmpeg.input(input_file)
                
                # Escala automática que mantém proporção e adiciona bordas se o formato for diferente
                v = (
                    inp.video
                    .filter('scale', target_w, target_h, force_original_aspect_ratio='decrease')
                    .filter('pad', target_w, target_h, '(ow-iw)/2', '(oh-ih)/2')
                    .filter('setsar', 1)
                    .filter('fps', fps=30)
                )
                
                if has_audio:
                    a = inp.audio
                else:
                    a = ffmpeg.input('anullsrc=channel_layout=stereo:sample_rate=44100', format='lavfi').audio.filter('atrim', duration=duration)
                
                # Encode to MPEG-TS with ultrafast preset for speed and concat compatibility
                (
                    ffmpeg
                    .output(v, a, output_file, vcodec='libx264', preset='ultrafast', acodec='aac', ar=44100, f='mpegts')
                    .run(overwrite_output=True, capture_stderr=True)
                )
                return output_file
            except ffmpeg.Error as e:
                print(f"FFmpeg error normalizing {input_file}: {e.stderr.decode('utf8')}")
                return None
            except Exception as e:
                print(f"Error normalizing {input_file}: {str(e)}")
                return None

        # Use 4 workers to normalize videos in parallel
        print(f"Starting parallel normalization of {len(input_files)} videos...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(normalize_task, i, f): i for i, f in enumerate(input_files)}
            for future in concurrent.futures.as_completed(futures):
                i = futures[future]
                normalized_files[i] = future.result()
        
        # Filter out failed normalizations
        valid_files = [f for f in normalized_files if f is not None]
        
        if not valid_files:
             raise Exception("No valid video files to concatenate.")

        # Create concat list file
        list_file = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_list.txt")
        with open(list_file, 'w') as f:
            for vf in valid_files:
                f.write(f"file '{vf}'\n")
        
        # Fast concat using stream copy
        print("Concatenating normalized videos...")
        try:
            (
                ffmpeg
                .input(list_file, format='concat', safe=0)
                .output(output_path, c='copy', movflags='+faststart')
                .run(overwrite_output=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
             print(f"FFmpeg concat error: {e.stderr.decode('utf8')}")
             raise e

        # Clean up input files and intermediate files
        for f in input_files:
            if os.path.exists(f): os.remove(f)
        for f in valid_files:
             if os.path.exists(f): os.remove(f)
        if os.path.exists(list_file): os.remove(list_file)

        print(f"Video combination successful: {output_path}")

        # Check if the output file exists locally before upload
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Output file {output_path} does not exist after combination.")

        return output_path
    except Exception as e:
        print(f"Video combination failed: {str(e)}")
        raise 
