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
from urllib.parse import quote
from flask import request

logger = logging.getLogger(__name__)

class LocalStorageProvider:
    def __init__(self, storage_path="/tmp"):
        self.storage_path = storage_path
        
    def save_file(self, file_path: str) -> str:
        """
        Move file to local storage and return download URL
        """
        try:
            # O arquivo já está em /tmp, só precisamos gerar a URL
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
                
            filename = os.path.basename(file_path)
            logger.info(f"File saved locally: {file_path}")
            
            # Gerar URL de download baseada no request atual
            base_url = request.url_root.rstrip('/')
            encoded_filename = quote(filename)
            download_url = f"{base_url}/download/{encoded_filename}"
            
            logger.info(f"Generated download URL: {download_url}")
            return download_url
            
        except Exception as e:
            logger.error(f"Error saving file locally: {e}")
            raise
    
    def get_file_path(self, filename: str) -> str:
        """
        Get full path of a file in local storage
        """
        return os.path.join(self.storage_path, filename)
    
    def file_exists(self, filename: str) -> bool:
        """
        Check if file exists in local storage
        """
        return os.path.exists(self.get_file_path(filename))
    
    def delete_file(self, filename: str) -> bool:
        """
        Delete file from local storage
        """
        try:
            file_path = self.get_file_path(filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"File deleted: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file {filename}: {e}")
            return False

def save_file_locally(file_path: str) -> str:
    """
    Save file locally and return download URL
    """
    provider = LocalStorageProvider()
    return provider.save_file(file_path)
