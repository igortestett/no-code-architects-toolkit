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

from flask import Blueprint, request
from app_utils import validate_payload, queue_task_wrapper
import logging
import shutil
from services.ass_toolkit import generate_ass_captions_v1
from services.authentication import authenticate
import os

v1_video_caption_bp = Blueprint('v1_video/caption', __name__)
logger = logging.getLogger(__name__)
@@ -87,8 +74,8 @@
           "items": {
               "type": "object",
               "properties": {
                    "start": { "type": "string" },
                    "end": { "type": "string" }
               },
               "required": ["start", "end"],
               "additionalProperties": False
@@ -108,89 +95,116 @@ def caption_video_v1(job_id, data):
settings = data.get('settings', {})
replace = data.get('replace', [])
exclude_time_ranges = data.get('exclude_time_ranges', [])
    webhook_url = data.get('webhook_url')
    id = data.get('id')
language = data.get('language', 'auto')

    logger.info(f"Job {job_id}: Received v1 captioning request for {video_url}")
    logger.info(f"Job {job_id}: Settings received: {settings}")
    logger.info(f"Job {job_id}: Replace rules received: {replace}")
    logger.info(f"Job {job_id}: Exclude time ranges received: {exclude_time_ranges}")

try:
        # Process video with the enhanced v1 service
        output = generate_ass_captions_v1(video_url, captions, settings, replace, exclude_time_ranges, job_id, language)

        if isinstance(output, dict) and 'error' in output:
            if 'available_fonts' in output:
                return ({"error": output['error'], "available_fonts": output['available_fonts']}, "/v1/video/caption", 400)
else:
                return ({"error": output['error']}, "/v1/video/caption", 400)

        # If processing was successful, output is the ASS file path
        ass_path = output
logger.info(f"Job {job_id}: ASS file generated at {ass_path}")

        # Download the video
        try:
            from services.file_management import download_file
            from config import LOCAL_STORAGE_PATH
            video_path = download_file(video_url, LOCAL_STORAGE_PATH)
            logger.info(f"Job {job_id}: Video downloaded to {video_path}")
        except Exception as e:
            logger.error(f"Job {job_id}: Video download error: {str(e)}")
            return ({"error": str(e)}, "/v1/video/caption", 500)
        
        # Prepare final output path in /tmp
final_filename = f"{job_id}_captioned.mp4"
final_output_path = f"/tmp/{final_filename}"
        
        # Ensure /tmp exists
os.makedirs("/tmp", exist_ok=True)

        # Render video with subtitles using FFmpeg
try:
            import ffmpeg
            ffmpeg.input(video_path).output(
                final_output_path,
                vf=f"subtitles='{ass_path}:fontsdir=./fonts'",
                acodec='copy'
            ).overwrite_output().run()
            logger.info(f"Job {job_id}: FFmpeg processing completed. Output saved to {final_output_path}")
        except Exception as e:
            logger.error(f"Job {job_id}: FFmpeg error: {str(e)}")
            return ({"error": f"FFmpeg error: {str(e)}"}, "/v1/video/caption", 500)
        
        # Clean up the ASS file after use
        if os.path.exists(ass_path):
            os.remove(ass_path)
            logger.info(f"Job {job_id}: Cleaned up ASS file: {ass_path}")

        # Clean up video file
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Job {job_id}: Cleaned up video file: {video_path}")

        # Verify final output exists and is not empty
if not os.path.exists(final_output_path):
            logger.error(f"Job {job_id}: Final output file not created: {final_output_path}")
return ({"error": "Output file not created"}, "/v1/video/caption", 500)

file_size = os.path.getsize(final_output_path)
if file_size == 0:
logger.error(f"Job {job_id}: Final output file is empty")
return ({"error": "Generated file is empty"}, "/v1/video/caption", 500)

        logger.info(f"Job {job_id}: Final output ready: {final_output_path} ({file_size} bytes)")

        # Generate download URL
base_url = request.url_root.rstrip('/')
download_url = f"{base_url}/download/{final_filename}"

        logger.info(f"Job {job_id}: Generated download URL: {download_url}")
        
        return (download_url, "/v1/video/caption", 200)

except Exception as e:
        logger.error(f"Job {job_id}: Error during captioning process - {str(e)}", exc_info=True)
return ({"error": str(e)}, "/v1/video/caption", 500)
