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
import subprocess
import json
import re
import ffmpeg
from services.file_management import download_file
from services.ffmpeg_toolkit import get_file_info
from config import LOCAL_STORAGE_PATH

def create_dummy_file(output_path, duration=5):
    """Create a dummy file with black video and silent audio."""
    try:
        (
            ffmpeg
            .input('color=c=black:s=1280x720:r=30', format='lavfi', t=duration)
            .output(
                ffmpeg.input('anullsrc=channel_layout=stereo:sample_rate=44100', format='lavfi', t=duration),
                output_path,
                vcodec='libx264',
                acodec='aac',
                shortest=None
            )
            .run(overwrite_output=True, capture_stderr=True)
        )
        return output_path
    except Exception as e:
        print(f"Error creating dummy file: {str(e)}")
        raise

def ensure_audio_stream(input_path, job_id, index):
    """Ensure the input file has an audio stream. If not, add silence."""
    try:
        has_video, has_audio, duration = get_file_info(input_path)
        
        if has_audio:
            return input_path
            
        print(f"File {input_path} missing audio. Adding silence.")
        output_path = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_fixed_{index}.mp4")
        
        input_stream = ffmpeg.input(input_path)
        audio_stream = ffmpeg.input('anullsrc=channel_layout=stereo:sample_rate=44100', format='lavfi').audio.filter('atrim', duration=duration)
        
        # If video exists, copy it. If not (audio only file?), generate black video?
        # Assuming if no audio, it might be video-only.
        if has_video:
            (
                ffmpeg
                .output(input_stream.video, audio_stream, output_path, c='copy', acodec='aac', shortest=None)
                .run(overwrite_output=True, capture_stderr=True)
            )
        else:
            # Neither video nor audio? Should have been caught by get_file_info or download check.
            # Create generic dummy if completely empty
             return create_dummy_file(output_path, duration=duration if duration > 0 else 5)
             
        return output_path
    except Exception as e:
        print(f"Error adding silence to {input_path}: {str(e)}")
        # Fallback: return original and hope for best (or raise?)
        return input_path

def get_extension_from_format(format_name):
    # Mapping of common format names to file extensions
    format_to_extension = {
        'mp4': 'mp4',
        'mov': 'mov',
        'avi': 'avi',
        'mkv': 'mkv',
        'webm': 'webm',
        'gif': 'gif',
        'apng': 'apng',
        'jpg': 'jpg',
        'jpeg': 'jpg',
        'png': 'png',
        'image2': 'png',  # Assume png for image2 format
        'rawvideo': 'raw',
        'mp3': 'mp3',
        'wav': 'wav',
        'aac': 'aac',
        'flac': 'flac',
        'ogg': 'ogg'
    }
    return format_to_extension.get(format_name.lower(), 'mp4')  # Default to mp4 if unknown

def get_metadata(filename, metadata_requests, job_id):
    metadata = {}
    if metadata_requests.get('thumbnail'):
        thumbnail_filename = f"{os.path.splitext(filename)[0]}_thumbnail.jpg"
        thumbnail_command = [
            'ffmpeg',
            '-i', filename,
            '-vf', 'select=eq(n\,0)',
            '-vframes', '1',
            thumbnail_filename
        ]
        try:
            subprocess.run(thumbnail_command, check=True, capture_output=True, text=True)
            if os.path.exists(thumbnail_filename):
                metadata['thumbnail'] = thumbnail_filename  # Return local path instead of URL
        except subprocess.CalledProcessError as e:
            print(f"Thumbnail generation failed: {e.stderr}")

    if metadata_requests.get('filesize'):
        metadata['filesize'] = os.path.getsize(filename)

    if metadata_requests.get('encoder') or metadata_requests.get('duration') or metadata_requests.get('bitrate'):
        ffprobe_command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            filename
        ]
        result = subprocess.run(ffprobe_command, capture_output=True, text=True)
        probe_data = json.loads(result.stdout)
        
        if metadata_requests.get('duration'):
            metadata['duration'] = float(probe_data['format']['duration'])
        if metadata_requests.get('bitrate'):
            metadata['bitrate'] = int(probe_data['format']['bit_rate'])
        
        if metadata_requests.get('encoder'):
            metadata['encoder'] = {}
            for stream in probe_data['streams']:
                if stream['codec_type'] == 'video':
                    metadata['encoder']['video'] = stream.get('codec_name', 'unknown')
                elif stream['codec_type'] == 'audio':
                    metadata['encoder']['audio'] = stream.get('codec_name', 'unknown')

    return metadata

def process_ffmpeg_compose(data, job_id):
    output_filenames = []
    
    # Build FFmpeg command
    command = ["ffmpeg"]
    
    # Add global options
    for option in data.get("global_options", []):
        command.append(option["option"])
        if "argument" in option and option["argument"] is not None:
            command.append(str(option["argument"]))
    
    # Add inputs
    input_paths = []
    download_cache = {}  # cache of url -> local_path
    for i, input_data in enumerate(data["inputs"]):
        if "options" in input_data:
            for option in input_data["options"]:
                command.append(option["option"])
                if "argument" in option and option["argument"] is not None:
                    command.append(str(option["argument"]))
        file_url = input_data.get("file_url")
        
        # Handle empty URL or "None" string
        if not file_url or str(file_url).strip() == "" or str(file_url).strip().lower() == "none":
             print(f"Input {i} has empty URL. Creating dummy file.")
             input_path = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_dummy_{i}.mp4")
             create_dummy_file(input_path)
        elif file_url in download_cache:
            input_path = download_cache[file_url]
        else:
            try:
                input_path = download_file(file_url, LOCAL_STORAGE_PATH)
                download_cache[file_url] = input_path
            except Exception as e:
                print(f"Failed to download {file_url}: {e}. Creating dummy file.")
                input_path = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_dummy_{i}.mp4")
                create_dummy_file(input_path)
        
        # Ensure audio stream exists
        input_path = ensure_audio_stream(input_path, job_id, i)
        
        input_paths.append(input_path)
        command.extend(["-i", input_path])
    
    # Add filters
    subtitles_paths = []  # Track downloaded subtitles/filter files
    if data.get("filters"):
        new_filters = []
        for filter_obj in data["filters"]:
            filter_str = filter_obj["filter"]
            def replace_url(match):
                prefix = match.group(1)
                filter_type = match.group(2)
                quote = match.group(3)
                url = match.group(4)
                closing_quote = match.group(5)
                trailing = match.group(6) or ''
                if not url or url.strip() == '':
                    print(f"[DEBUG] Skipping empty URL for filter: {match.group(0)}")
                    return match.group(0)
                print(f"[DEBUG] Parsed URL for filter: {url}")
                try:
                    local_path = download_file(url, LOCAL_STORAGE_PATH)
                    subtitles_paths.append(local_path)
                    fixed_path = local_path.replace('\\', '/')
                    return f"{prefix}{filter_type}={quote}{fixed_path}{closing_quote}{trailing}"
                except Exception as e:
                    print(f"Failed to download filter asset {url}: {e}")
                    return match.group(0)

            # Regex: (.*?)(subtitles|ass)=(['"])(https?://[^'\"]+)(['"])(.*)
            pattern = r"(.*?)(subtitles|ass)=([\'\"])(https?://[^'\"]+)([\'\"])(.*)"
            filter_str = re.sub(pattern, replace_url, filter_str)
            new_filters.append(filter_str)
        filter_complex = ";".join(new_filters)
        command.extend(["-filter_complex", filter_complex])
    
    # Add outputs
    for i, output in enumerate(data["outputs"]):
        format_name = None
        for option in output["options"]:
            if option["option"] == "-f":
                format_name = option.get("argument")
                break
        
        extension = get_extension_from_format(format_name) if format_name else 'mp4'
        output_filename = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_output_{i}.{extension}")
        output_filenames.append(output_filename)
        
        for option in output["options"]:
            command.append(option["option"])
            if "argument" in option and option["argument"] is not None:
                command.append(str(option["argument"]))
        command.append(output_filename)
    
    # Execute FFmpeg command
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg command failed: {e.stderr}")
        raise Exception(f"FFmpeg command failed: {e.stderr}")
    
    # Clean up input files
    for input_path in input_paths:
        if os.path.exists(input_path):
            os.remove(input_path)
    # Clean up subtitles/filter files
    for subtitles_path in subtitles_paths:
        if os.path.exists(subtitles_path):
            os.remove(subtitles_path)
    # Get metadata if requested
    metadata = []
    if data.get("metadata"):
        for output_filename in output_filenames:
            metadata.append(get_metadata(output_filename, data["metadata"], job_id))
    
    return output_filenames, metadata