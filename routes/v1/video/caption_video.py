# Copyright (c) 2025 Stephen G. Pope
from flask import Blueprint, request
from app_utils import validate_payload, queue_task_wrapper
import logging
import os
import ffmpeg
from services.ass_toolkit import generate_ass_captions_v1
from services.file_management import download_file
from services.authentication import authenticate
from config import LOCAL_STORAGE_PATH

v1_video_caption_bp = Blueprint('v1_video/caption', __name__)
logger = logging.getLogger(__name__)

@v1_video_caption_bp.route('/v1/video/caption', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "captions": {"type": "string"},
        "settings": {
            "type": "object",
            "properties": {
                "line_color": {"type": "string"},
                "word_color": {"type": "string"},
                "outline_color": {"type": "string"},
                "all_caps": {"type": "boolean"},
                "max_words_per_line": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "position": {
                    "type": "string",
                    "enum": [
                        "bottom_left", "bottom_center", "bottom_right",
                        "middle_left", "middle_center", "middle_right",
                        "top_left", "top_center", "top_right"
                    ]
                },
                "alignment": {
                    "type": "string",
                    "enum": ["left", "center", "right"]
                },
                "font_family": {"type": "string"},
                "font_size": {"type": "integer"},
                "bold": {"type": "boolean"},
                "italic": {"type": "boolean"},
                "underline": {"type": "boolean"},
                "strikeout": {"type": "boolean"},
                "style": {
                    "type": "string",
                    "enum": ["classic", "karaoke", "highlight", "underline", "word_by_word"]
                },
                "outline_width": {"type": "integer"},
                "spacing": {"type": "integer"},
                "angle": {"type": "integer"},
                "shadow_offset": {"type": "integer"}
            },
            "additionalProperties": False
        },
        "replace": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "find": {"type": "string"},
                    "replace": {"type": "string"}
                },
                "required": ["find", "replace"]
            }
        },
        "exclude_time_ranges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"}
                },
                "required": ["start", "end"],
                "additionalProperties": False
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "language": {"type": "string"}
    },
    "required": ["video_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def caption_video_v1(job_id, data):
    video_url = data['video_url']
    captions = data.get('captions')
    settings = data.get('settings', {})
    replace = data.get('replace', [])
    exclude_time_ranges = data.get('exclude_time_ranges', [])
    language = data.get('language', 'auto')
    
    logger.info(f"Job {job_id}: Starting optimized video captioning for {video_url}")
    
    try:
        # 1. Download video first (parallel with ASS generation if needed)
        logger.info(f"Job {job_id}: Downloading video...")
        video_path = download_file(video_url, LOCAL_STORAGE_PATH)
        logger.info(f"Job {job_id}: Video downloaded to {video_path}")
        
        # 2. Generate ASS file using optimized ass_toolkit
        logger.info(f"Job {job_id}: Generating ASS subtitles...")
        ass_output = generate_ass_captions_v1(
            video_url=video_url,
            captions=captions,
            settings=settings,
            replace=replace,
            exclude_time_ranges=exclude_time_ranges,
            job_id=job_id,
            language=language
        )
        
        # Handle ASS generation errors
        if isinstance(ass_output, dict) and 'error' in ass_output:
            # Cleanup video file
            if os.path.exists(video_path):
                os.remove(video_path)
            
            if 'available_fonts' in ass_output:
                return ({"error": ass_output['error'], "available_fonts": ass_output['available_fonts']}, "/v1/video/caption", 400)
            else:
                return ({"error": ass_output['error']}, "/v1/video/caption", 400)
        
        ass_path = ass_output
        logger.info(f"Job {job_id}: ASS file generated at {ass_path}")
        
        # 3. Prepare final output
        final_filename = f"{job_id}_captioned.mp4"
        final_output_path = f"/tmp/{final_filename}"
        os.makedirs("/tmp", exist_ok=True)
        
        # 4. Render video with subtitles using optimized FFmpeg
        logger.info(f"Job {job_id}: Rendering video with subtitles...")
        try:
            # Usar configurações otimizadas do FFmpeg
            (
                ffmpeg
                .input(video_path)
                .output(
                    final_output_path,
                    vf=f"subtitles='{ass_path}':fontsdir=./fonts",
                    acodec='copy',  # Copy audio without re-encoding
                    vcodec='libx264',  # Ensure compatibility
                    preset='fast',  # Fast encoding preset
                    crf=23  # Good quality/speed balance
                )
                .overwrite_output()
                .run(quiet=True)  # Suppress FFmpeg output unless there's an error
            )
            logger.info(f"Job {job_id}: Video rendering completed")
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode('utf-8') if e.stderr else "Unknown FFmpeg error"
            logger.error(f"Job {job_id}: FFmpeg error: {error_msg}")
            
            # Cleanup files
            cleanup_files([video_path, ass_path])
            
            return ({"error": f"Video rendering failed: {error_msg}"}, "/v1/video/caption", 500)
        
        # 5. Cleanup intermediate files
        cleanup_files([video_path, ass_path])
        
        # 6. Verify final output
        if not os.path.exists(final_output_path):
            logger.error(f"Job {job_id}: Final output file not created")
            return ({"error": "Output file not created"}, "/v1/video/caption", 500)
        
        file_size = os.path.getsize(final_output_path)
        if file_size == 0:
            logger.error(f"Job {job_id}: Final output file is empty")
            return ({"error": "Generated file is empty"}, "/v1/video/caption", 500)
        
        logger.info(f"Job {job_id}: Success! Output ready: {final_output_path} ({file_size:,} bytes)")
        
        # 7. Generate download URL
        base_url = request.url_root.rstrip('/')
        download_url = f"{base_url}/download/{final_filename}"
        
        return ({"download_url": download_url, "file_size": file_size, "job_id": job_id}, "/v1/video/caption", 200)
        
    except Exception as e:
        logger.error(f"Job {job_id}: Unexpected error: {str(e)}", exc_info=True)
        # Try to cleanup any files that might exist
        try:
            cleanup_files([
                os.path.join(LOCAL_STORAGE_PATH, f"{job_id}.mp4"),
                os.path.join(LOCAL_STORAGE_PATH, f"{job_id}.ass")
            ])
        except:
            pass
        
        return ({"error": str(e)}, "/v1/video/caption", 500)

def cleanup_files(file_paths):
    """Helper function to cleanup files safely"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path}: {e}")
