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
import logging
from services.local_storage import save_file_locally

logger = logging.getLogger(__name__)

def upload_file(file_path: str) -> str:
    """
    Save file locally and return download URL
    (Replaces the old cloud storage upload)
    """
    try:
        logger.info(f"Saving file locally: {file_path}")
        download_url = save_file_locally(file_path)
        logger.info(f"File saved successfully. Download URL: {download_url}")
        return download_url
    except Exception as e:
        logger.error(f"Error saving file locally: {e}")
        raise
