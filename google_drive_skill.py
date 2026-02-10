"""
Google Drive Skill for AutoMinds Intelligence (AMI)
Provides functionality to interact with Google Drive.

- List files in a folder
- Download files
- Authenticate using user's credentials
"""

import io
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from models import ConnectedAccount
from config import settings

logger = logging.getLogger(__name__)

def _get_drive_service(account: ConnectedAccount):
    """Builds a Google Drive service object from user credentials."""
    if account.provider != "google":
        raise ValueError("Google Drive skill requires a Google account.")

    creds = Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(account: ConnectedAccount, folder_id: str) -> list[dict]:
    """
    Lists all files in a given Google Drive folder.
    """
    service = _get_drive_service(account)
    files = []
    page_token = None
    try:
        while True:
            response = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break
        logger.info(f"Found {len(files)} files in folder '{folder_id}'.")
        return files
    except Exception as e:
        logger.error(f"Error listing files in Google Drive folder '{folder_id}': {e}", exc_info=True)
        raise


def download_file(account: ConnectedAccount, file_id: str) -> io.BytesIO:
    """
    Downloads a file from Google Drive by its ID.
    Returns the file content as a BytesIO object.
    """
    service = _get_drive_service(account)
    try:
        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            logger.info(f"Download {int(status.progress() * 100)}%.")
        
        file_buffer.seek(0)
        logger.info(f"Successfully downloaded file '{file_id}'.")
        return file_buffer
    except Exception as e:
        logger.error(f"Error downloading file '{file_id}' from Google Drive: {e}", exc_info=True)
        raise
