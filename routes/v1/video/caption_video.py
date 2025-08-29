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

from flask import Blueprint, jsonify
from app_utils import validate_payload, queue_task_wrapper
import logging
from services.authentication import authenticate
from services.cloud_storage import upload_file
import os
import requests
import urllib.request

v1_video_caption_bp = Blueprint('v1_video/caption', __name__)
logger = logging.getLogger(__name__)

@v1_video_caption_bp.route('/v1/video/caption', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "captions": {"type": "string", "format": "uri"},  # ASS file URL
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url", "captions"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def caption_video_v1(job_id, data):
    video_url = data['video_url']
    ass_file_url = data['captions']  # ASS file URL
    webhook_url = data.get('webhook_url')
    id = data.get('id')
    
    logger.info(f"Job {job_id}: Processing video {video_url} with provided ASS file {ass_file_url}")
    
    try:
        from services.file_management import download_file
        from config import LOCAL_STORAGE_PATH
        
        # Download the video file
        try:
            video_path = download_file(video_url, LOCAL_STORAGE_PATH)
            logger.info(f"Job {job_id}: Video downloaded to {video_path}")
        except Exception as e:
            logger.error(f"Job {job_id}: Video download error: {str(e)}")
            return {"error": f"Video download failed: {str(e)}"}, "/v1/video/caption", 500
        
        # Download the ASS file
        try:
            ass_filename = f"{job_id}_captions.ass"
            ass_path = os.path.join(LOCAL_STORAGE_PATH, ass_filename)
            urllib.request.urlretrieve(ass_file_url, ass_path)
            
            # Verify ASS file exists and has content
            if not os.path.exists(ass_path) or os.path.getsize(ass_path) == 0:
                raise Exception("Downloaded ASS file is empty or invalid")
                
            logger.info(f"Job {job_id}: ASS file downloaded to {ass_path}")
            
        except Exception as e:
            logger.error(f"Job {job_id}: ASS file download error: {str(e)}")
            return {"error": f"ASS file download failed: {str(e)}"}, "/v1/video/caption", 500
        
        # Prepare output path for the rendered video
        output_filename = f"{id or job_id}_captioned.mp4"
        output_path = os.path.join(LOCAL_STORAGE_PATH, output_filename)
        
        # Render video with subtitles using FFmpeg
        try:
            import ffmpeg
            
            # Escape special characters in paths for FFmpeg
            ass_path_clean = ass_path.replace("'", "\\'").replace(":", "\\:")
            
            (
                ffmpeg
                .input(video_path)
                .output(
                    output_path,
                    vf=f"subtitles='{ass_path_clean}'",
                    acodec='copy',
                    vcodec='libx264',
                    **{'movflags': '+faststart'}  # Optimize for web streaming
                )
                .run(overwrite_output=True, quiet=True)
            )
            
            # Verify output file was created
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception("FFmpeg failed to create output video")
                
            logger.info(f"Job {job_id}: Video processed successfully. Output: {output_path}")
            
        except Exception as e:
            logger.error(f"Job {job_id}: FFmpeg processing error: {str(e)}")
            return {"error": f"Video processing failed: {str(e)}"}, "/v1/video/caption", 500
        
        # Upload the captioned video to cloud storage
        try:
            cloud_url = upload_file(output_path)
            logger.info(f"Job {job_id}: Captioned video uploaded: {cloud_url}")
        except Exception as e:
            logger.error(f"Job {job_id}: Cloud upload error: {str(e)}")
            return {"error": f"Upload failed: {str(e)}"}, "/v1/video/caption", 500
        
        # Send webhook notification if provided
        if webhook_url:
            try:
                webhook_payload = {
                    "job_id": job_id,
                    "status": "completed",
                    "video_url": cloud_url,
                    "original_video": video_url,
                    "captions_file": ass_file_url,
                    "local_output_path": output_path  # Include local path for direct access
                }
                
                response = requests.post(webhook_url, json=webhook_payload, timeout=10)
                logger.info(f"Job {job_id}: Webhook sent successfully (status: {response.status_code})")
                
            except Exception as webhook_error:
                logger.warning(f"Job {job_id}: Webhook notification failed - {str(webhook_error)}")
        
        # FILES KEPT - NO CLEANUP PERFORMED
        # The following files remain accessible:
        # - video_path: Original downloaded video
        # - ass_path: Downloaded ASS subtitle file  
        # - output_path: Final processed video with subtitles
        
        logger.info(f"Job {job_id}: Job completed successfully. Files retained at:")
        logger.info(f"  - Original video: {video_path}")
        logger.info(f"  - ASS file: {ass_path}")
        logger.info(f"  - Processed video: {output_path}")
        
        # Return success response with file paths
        response_data = {
            "success": True,
            "video_url": cloud_url,
            "job_id": job_id,
            "message": "Video successfully processed and all files retained",
            "original_video": video_url,
            "subtitles_used": ass_file_url,
            "local_files": {
                "original_video_path": video_path,
                "ass_file_path": ass_path,
                "processed_video_path": output_path
            }
        }
        
        return response_data, "/v1/video/caption", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Unexpected error during processing - {str(e)}", exc_info=True)
        return {"error": f"Processing failed: {str(e)}"}, "/v1/video/caption", 500
