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
import logging
import requests
import subprocess
from services.file_management import download_file

# Set the default local storage directory
STORAGE_PATH = "/tmp/"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the path to the fonts directory
FONTS_DIR = '/usr/share/fonts/custom'

# Create the FONT_PATHS dictionary by reading the fonts directory
FONT_PATHS = {}
if os.path.exists(FONTS_DIR):
    for font_file in os.listdir(FONTS_DIR):
        if font_file.endswith('.ttf') or font_file.endswith('.TTF'):
            font_name = os.path.splitext(font_file)[0]
            FONT_PATHS[font_name] = os.path.join(FONTS_DIR, font_file)

logger.info(f"Available fonts in custom directory: {list(FONT_PATHS.keys())}")

# Get system fonts using fontconfig
def get_available_system_fonts():
    """Get list of available system fonts using fontconfig."""
    try:
        result = subprocess.run(['fc-list', ':family'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            fonts = []
            for line in result.stdout.split('\n'):
                if line.strip():
                    # Handle multiple families in one line (separated by comma)
                    families = line.split(',')
                    for family in families:
                        font_name = family.strip()
                        if font_name and font_name not in fonts:
                            fonts.append(font_name)
            return fonts
        else:
            logger.error(f"Error getting system fonts: {result.stderr}")
            return []
    except Exception as e:
        logger.error(f"Exception while getting system fonts: {str(e)}")
        return []

# Get available system fonts
SYSTEM_FONTS = get_available_system_fonts()
logger.info(f"Available system fonts: {len(SYSTEM_FONTS)} fonts found")

# Create a list of acceptable font names
ACCEPTABLE_FONTS = list(FONT_PATHS.keys()) + SYSTEM_FONTS

# Font fallback mapping for common fonts
FONT_FALLBACKS = {
    'Arial': ['Liberation Sans', 'DejaVu Sans', 'Noto Sans'],
    'Times': ['Liberation Serif', 'DejaVu Serif', 'Noto Serif'],
    'Courier': ['Liberation Mono', 'DejaVu Sans Mono', 'Noto Mono'],
    'Helvetica': ['Liberation Sans', 'DejaVu Sans', 'Noto Sans'],
    'Times New Roman': ['Liberation Serif', 'DejaVu Serif', 'Noto Serif']
}

def get_best_font(requested_font):
    """Get the best available font with intelligent fallback."""
    logger.info(f"Looking for font: {requested_font}")
    
    # 1. Check if font exists in custom fonts directory
    if requested_font in FONT_PATHS:
        logger.info(f"Found {requested_font} in custom fonts")
        return requested_font, 'custom'
    
    # 2. Check if font exists in system fonts
    if requested_font in SYSTEM_FONTS:
        logger.info(f"Found {requested_font} in system fonts")
        return requested_font, 'system'
    
    # 3. Try fallback mapping
    if requested_font in FONT_FALLBACKS:
        for fallback_font in FONT_FALLBACKS[requested_font]:
            if fallback_font in SYSTEM_FONTS:
                logger.info(f"Using fallback: {fallback_font} for {requested_font}")
                return fallback_font, 'system'
            elif fallback_font in FONT_PATHS:
                logger.info(f"Using custom fallback: {fallback_font} for {requested_font}")
                return fallback_font, 'custom'
    
    # 4. Try common alternatives
    alternatives = []
    if 'arial' in requested_font.lower():
        alternatives = ['Liberation Sans', 'DejaVu Sans', 'Noto Sans']
    elif 'times' in requested_font.lower():
        alternatives = ['Liberation Serif', 'DejaVu Serif', 'Noto Serif']
    elif 'courier' in requested_font.lower() or 'mono' in requested_font.lower():
        alternatives = ['Liberation Mono', 'DejaVu Sans Mono', 'Noto Mono']
    else:
        alternatives = ['Liberation Sans', 'DejaVu Sans', 'Noto Sans']
    
    for alt in alternatives:
        if alt in SYSTEM_FONTS:
            logger.info(f"Using alternative: {alt} for {requested_font}")
            return alt, 'system'
        elif alt in FONT_PATHS:
            logger.info(f"Using custom alternative: {alt} for {requested_font}")
            return alt, 'custom'
    
    # 5. Final fallback - use first available system font that contains "Sans"
    for font in SYSTEM_FONTS:
        if 'Sans' in font and 'UI' not in font:
            logger.warning(f"Using final fallback: {font} for {requested_font}")
            return font, 'system'
    
    # 6. If we have custom fonts, use the first one
    if FONT_PATHS:
        default_font = list(FONT_PATHS.keys())[0]
        logger.warning(f"Using custom default: {default_font} for {requested_font}")
        return default_font, 'custom'
    
    # 7. Absolute last resort - use any available system font
    if SYSTEM_FONTS:
        final_font = SYSTEM_FONTS[0]
        logger.error(f"Using absolute fallback: {final_font} for {requested_font}")
        return final_font, 'system'
    
    # If all else fails, raise an error with available fonts
    error_msg = f"Font '{requested_font}' not available."
    available_fonts = list(FONT_PATHS.keys()) + SYSTEM_FONTS[:20]  # Limit to first 20 system fonts
    raise ValueError({
        "error": error_msg,
        "available_fonts": sorted(available_fonts)
    })

# Match font files with fontconfig names
def match_fonts():
    try:
        result = subprocess.run(['fc-list', ':family'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            fontconfig_fonts = result.stdout.split('\n')
            fontconfig_fonts = list(set(fontconfig_fonts))  # Remove duplicates
            matched_fonts = {}
            for font_file in FONT_PATHS.keys():
                for fontconfig_font in fontconfig_fonts:
                    if font_file.lower() in fontconfig_font.lower():
                        matched_fonts[font_file] = fontconfig_font.strip()
            # Parse and output the matched font names
            unique_font_names = set()
            for font in matched_fonts.values():
                if ':' in font:
                    font_name = font.split(':')[1].strip()
                else:
                    font_name = font.strip()
                if font_name:
                    unique_font_names.add(font_name)
            
            # Remove duplicates from font_name and sort them alphabetically
            unique_font_names = sorted(list(set(unique_font_names)))
            
        else:
            logger.error(f"Error matching fonts: {result.stderr}")
    except Exception as e:
        logger.error(f"Exception while matching fonts: {str(e)}")

match_fonts()

def generate_style_line(options):
    """Generate ASS style line from options."""
    style_options = {
        'Name': 'Default',
        'Fontname': options.get('font_name', 'Arial'),
        'Fontsize': options.get('font_size', 12),
        'PrimaryColour': options.get('primary_color', '&H00FFFFFF'),
        'OutlineColour': options.get('outline_color', '&H00000000'),
        'BackColour': options.get('back_color', '&H00000000'),
        'Bold': options.get('bold', 0),
        'Italic': options.get('italic', 0),
        'Underline': options.get('underline', 0),
        'StrikeOut': options.get('strikeout', 0),
        'ScaleX': 100,
        'ScaleY': 100,
        'Spacing': 0,
        'Angle': 0,
        'BorderStyle': 1,
        'Outline': options.get('outline', 1),
        'Shadow': options.get('shadow', 0),
        'Alignment': options.get('alignment', 2),
        'MarginL': options.get('margin_l', 10),
        'MarginR': options.get('margin_r', 10),
        'MarginV': options.get('margin_v', 10),
        'Encoding': options.get('encoding', 1)
    }
    return f"Style: {','.join(str(v) for v in style_options.values())}"

def process_captioning(file_url, caption_srt, caption_type, options, job_id):
    """Process video captioning using FFmpeg."""
    try:
        logger.info(f"Job {job_id}: Starting download of file from {file_url}")
        video_path = download_file(file_url, STORAGE_PATH)
        logger.info(f"Job {job_id}: File downloaded to {video_path}")
        
        subtitle_extension = '.' + caption_type
        srt_path = os.path.join(STORAGE_PATH, f"{job_id}{subtitle_extension}")
        options = convert_array_to_collection(options)
        
        caption_style = ""
        if caption_type == 'ass':
            style_string = generate_style_line(options)
            caption_style = f"""
[Script Info]
Title: Highlight Current Word
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_string}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            logger.info(f"Job {job_id}: Generated ASS style string: {style_string}")

        if caption_srt.startswith("https"):
            # Download the file if caption_srt is a URL
            logger.info(f"Job {job_id}: Downloading caption file from {caption_srt}")
            response = requests.get(caption_srt)
            response.raise_for_status()  # Raise an exception for bad status codes
            if caption_type in ['srt','vtt']:
                with open(srt_path, 'wb') as srt_file:
                    srt_file.write(response.content)
            else:
                # For ASS files from URL, don't prepend caption_style
                with open(srt_path, 'w', encoding='utf-8') as srt_file:
                    srt_file.write(response.text)
            logger.info(f"Job {job_id}: Caption file downloaded to {srt_path}")
        else:
            # Write caption_srt content directly to file
            subtitle_content = caption_style + caption_srt
            with open(srt_path, 'w', encoding='utf-8') as srt_file:
                srt_file.write(subtitle_content)
            logger.info(f"Job {job_id}: SRT file created at {srt_path}")

        output_path = os.path.join(STORAGE_PATH, f"{job_id}_captioned.mp4")
        logger.info(f"Job {job_id}: Output path set to {output_path}")

        # Get the best available font with intelligent fallback
        requested_font = options.get('font_name', 'Arial')
        try:
            best_font, font_type = get_best_font(requested_font)
            logger.info(f"Job {job_id}: Using font: {best_font} (type: {font_type})")
        except ValueError as e:
            # Return detailed error with available fonts
            logger.error(f"Job {job_id}: {str(e)}")
            raise ValueError(e.args[0])

        # For ASS subtitles, use simple subtitles filter
        if subtitle_extension == '.ass':
            subtitle_filter = f"subtitles='{srt_path}'"
            logger.info(f"Job {job_id}: Using ASS subtitle filter: {subtitle_filter}")
        else:
            # Construct FFmpeg filter options for subtitles with detailed styling
            subtitle_filter = f"subtitles={srt_path}:force_style='"
            style_options = {
                'FontName': best_font,  # Use the resolved font name
                'FontSize': options.get('font_size', 24),
                'PrimaryColour': options.get('primary_color', '&H00FFFFFF'),
                'SecondaryColour': options.get('secondary_color', '&H00000000'),
                'OutlineColour': options.get('outline_color', '&H00000000'),
                'BackColour': options.get('back_color', '&H00000000'),
                'Bold': options.get('bold', 0),
                'Italic': options.get('italic', 0),
                'Underline': options.get('underline', 0),
                'StrikeOut': options.get('strikeout', 0),
                'Alignment': options.get('alignment', 2),
                'MarginV': options.get('margin_v', 10),
                'MarginL': options.get('margin_l', 10),
                'MarginR': options.get('margin_r', 10),
                'Outline': options.get('outline', 1),
                'Shadow': options.get('shadow', 0),
                'Blur': options.get('blur', 0),
                'BorderStyle': options.get('border_style', 1),
                'Encoding': options.get('encoding', 1),
                'Spacing': options.get('spacing', 0),
                'Angle': options.get('angle', 0),
                'UpperCase': options.get('uppercase', 0)
            }
            # Add only populated options to the subtitle filter
            subtitle_filter += ','.join(f"{k}={v}" for k, v in style_options.items() if v is not None)
            subtitle_filter += "'"
            logger.info(f"Job {job_id}: Using subtitle filter: {subtitle_filter}")

        try:
            # Log the FFmpeg command for debugging
            logger.info(f"Job {job_id}: Running FFmpeg with filter: {subtitle_filter}")
            # Run FFmpeg to add subtitles to the video
            ffmpeg.input(video_path).output(
                output_path,
                vf=subtitle_filter,
                acodec='copy'
            ).run()
            logger.info(f"Job {job_id}: FFmpeg processing completed, output file at {output_path}")
        except ffmpeg.Error as e:
            # Log the FFmpeg stderr output
            if e.stderr:
                error_message = e.stderr.decode('utf8')
            else:
                error_message = 'Unknown FFmpeg error'
            logger.error(f"Job {job_id}: FFmpeg error: {error_message}")
            raise

        # The upload process will be handled by the calling function
        return output_path
        
        # Clean up local files (this code won't be reached due to return above)
        # os.remove(video_path)
        # os.remove(srt_path)
        # os.remove(output_path)
        # logger.info(f"Job {job_id}: Local files cleaned up")
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error in process_captioning: {str(e)}")
        raise

def convert_array_to_collection(options):
    logger.info(f"Converting options array to dictionary: {options}")
    return {item["option"]: item["value"] for item in options}
