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
    
    has_video = any(s['codec_type'] == 'video' for s in data.get('streams', []))
    has_audio = any(s['codec_type'] == 'audio' for s in data.get('streams', []))
    duration = float(data['format']['duration'])
    
    return has_video, has_audio, duration

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

        # The filter graph can become too large/complex for ffmpeg if we have many inputs (e.g., > 50).
        # To avoid this, we process the videos in batches of 20.
        BATCH_SIZE = 20
        
        # Helper function to concatenate a batch of files
        def concatenate_batch(files, output_file):
            input_streams = []
            for f in files:
                has_video, has_audio, duration = get_file_info(f)
                
                if not has_video:
                    print(f"Warning: File {f} has no video stream. Skipping.")
                    continue

                inp = ffmpeg.input(f)
                v = inp.video.filter('scale', 1920, 1080).filter('setsar', 1)
                
                if has_audio:
                    a = inp.audio
                else:
                    a = ffmpeg.input('anullsrc=channel_layout=stereo:sample_rate=44100', format='lavfi').audio.filter('atrim', duration=duration)
                
                input_streams.append(v)
                input_streams.append(a)

            try:
                (
                    ffmpeg
                    .concat(*input_streams, v=1, a=1)
                    .output(output_file)
                    .run(overwrite_output=True, capture_stderr=True)
                )
            except ffmpeg.Error as e:
                print(f"FFmpeg error: {e.stderr.decode('utf8')}")
                raise e

        # If we have more inputs than BATCH_SIZE, we process in chunks
        current_inputs = input_files
        iteration = 0
        
        while len(current_inputs) > BATCH_SIZE:
            next_stage_inputs = []
            num_batches = (len(current_inputs) + BATCH_SIZE - 1) // BATCH_SIZE
            
            for i in range(num_batches):
                batch = current_inputs[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
                if len(batch) == 1:
                    next_stage_inputs.append(batch[0])
                    continue
                    
                batch_output = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_batch_{iteration}_{i}.mp4")
                concatenate_batch(batch, batch_output)
                next_stage_inputs.append(batch_output)
            
            current_inputs = next_stage_inputs
            iteration += 1
            
        # Final concatenation of the remaining files (<= BATCH_SIZE)
        concatenate_batch(current_inputs, output_path)

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
