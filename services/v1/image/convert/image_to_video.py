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
import logging
from services.file_management import download_file
from PIL import Image
from config import LOCAL_STORAGE_PATH

logger = logging.getLogger(__name__)

def process_image_to_video(image_url, length, frame_rate, zoom_speed, job_id, webhook_url=None, enable_zoom=False):
    try:
        # Download the image file
        image_path = download_file(image_url, LOCAL_STORAGE_PATH)
        logger.info(f"Downloaded image to {image_path}")
        
        # Get image dimensions using Pillow
        with Image.open(image_path) as img:
            width, height = img.size
        logger.info(f"Original image dimensions: {width}x{height}")
        
        # Prepare the output path
        output_path = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}.mp4")
        
        # Determine orientation and set appropriate dimensions
        if width > height:
            output_dims = "1920x1080"
        else:
            output_dims = "1080x1920"
        
        logger.info(f"Output dimensions: {output_dims}")
        logger.info(f"Video length: {length}s, Frame rate: {frame_rate}fps")
        
        # Build video filter chain based on zoom preference
        if enable_zoom:
            # With zoom (slower but with effect)
            total_frames = int(length * frame_rate)
            zoom_factor = 1 + (zoom_speed * length)
            scale_dims = "7680:4320" if width > height else "4320:7680"
            
            vf_chain = f"scale={scale_dims},zoompan=z='min(1+({zoom_speed}*{length})*on/{total_frames}, {zoom_factor})':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={output_dims}"
            logger.info(f"Using zoom with final zoom factor: {zoom_factor}")
        else:
            # Without zoom (fastest processing)
            vf_chain = f"scale={output_dims}"
            logger.info("Zoom disabled for maximum speed")
        
        # Optimized FFmpeg command for maximum speed
        cmd = [
            'ffmpeg', 
            '-framerate', str(frame_rate), 
            '-loop', '1', 
            '-i', image_path,
            '-vf', vf_chain,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Seu preset preferido
            '-crf', '28',            # Seu CRF preferido
            '-r', str(frame_rate), 
            '-t', str(length), 
            '-pix_fmt', 'yuv420p',
            '-y',  # Overwrite output file without asking
            output_path
        ]
        
        logger.info(f"Running optimized FFmpeg command: {' '.join(cmd)}")
        
        # Run FFmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg command failed. Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        
        logger.info(f"Video created successfully: {output_path}")
        
        # Clean up input file
        os.remove(image_path)
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error in process_image_to_video: {str(e)}", exc_info=True)
        raise
