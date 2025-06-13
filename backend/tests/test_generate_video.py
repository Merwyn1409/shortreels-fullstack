import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from datetime import datetime
import os
import uuid
import asyncio
from app.main import generate_video  # Replace with your actual module path
from app.main import VideoRequest  # Replace with your actual module path
from app.video_processor import sync_audio_video
from app.config import OUTPUT_DIR_AUDIO, VIDEO_CACHE_DIR  # Use your config paths


# Test data
SAMPLE_TEXT = "This is a sample text with more than five words to pass validation."
SHORT_TEXT = "Short"
LONG_TEXT = " ".join(["word"] * 51)  # 51 words

@pytest.fixture
def mock_media_data():
    return [{
        "sentence": "This is a sample sentence",
        "videos": ["/path/to/video1.mp4"],
        "source": "cache"
    }]

@pytest.fixture
def mock_voice_file(tmp_path):
    voice_file = tmp_path / "voice.mp3"
    voice_file.write_text("dummy audio data")
    return str(voice_file)

@pytest.fixture
def mock_video_result(tmp_path):
    video_path = tmp_path / "watermarked.mp4"
    video_path.write_text("dummy video data")
    return {
        "watermarked": str(video_path),
        "non_watermarked": str(tmp_path / "non_watermarked.mp4"),
        "sentences": [{
            "text": "This is a sample sentence",
            "video": "/path/to/video1.mp4",
            "duration": 5.0
        }]
    }

@pytest.mark.asyncio
async def test_generate_video_success(mock_media_data, mock_voice_file, mock_video_result):
    """Test successful video generation"""
    with patch('your_module.fetch_media', new=AsyncMock(return_value=mock_media_data)), \
         patch('your_module.generate_voice', return_value=mock_voice_file), \
         patch('your_module.sync_audio_video', new=AsyncMock(return_value=mock_video_result)):
        
        request = VideoRequest(text=SAMPLE_TEXT)
        result = await generate_video(request)
        
        assert "request_id" in result
        assert "video_url" in result
        assert "filename" in result
        assert result["message"] == "Processing complete"
        assert len(result["metadata"]["sentences"]) == len(mock_media_data)

@pytest.mark.asyncio
async def test_generate_video_empty_text():
    """Test empty text validation"""
    request = VideoRequest(text="")
    with pytest.raises(HTTPException) as exc_info:
        await generate_video(request)
    assert exc_info.value.status_code == 400
    assert "Text is required" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_generate_video_short_text():
    """Test short text validation"""
    request = VideoRequest(text=SHORT_TEXT)
    with pytest.raises(HTTPException) as exc_info:
        await generate_video(request)
    assert exc_info.value.status_code == 400
    assert "between 5 and 50 words" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_generate_video_long_text():
    """Test long text validation"""
    request = VideoRequest(text=LONG_TEXT)
    with pytest.raises(HTTPException) as exc_info:
        await generate_video(request)
    assert exc_info.value.status_code == 400
    assert "between 5 and 50 words" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_generate_video_voice_failure(mock_media_data):
    """Test voice generation failure"""
    with patch('your_module.fetch_media', new=AsyncMock(return_value=mock_media_data)), \
         patch('your_module.generate_voice', return_value=None):
        
        request = VideoRequest(text=SAMPLE_TEXT)
        with pytest.raises(HTTPException) as exc_info:
            await generate_video(request)
        assert exc_info.value.status_code == 500
        assert "Failed to generate voice-over" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_generate_video_processing_failure(mock_media_data, mock_voice_file):
    """Test video processing failure"""
    with patch('your_module.fetch_media', new=AsyncMock(return_value=mock_media_data)), \
         patch('your_module.generate_voice', return_value=mock_voice_file), \
         patch('your_module.sync_audio_video', new=AsyncMock(return_value=None)):
        
        request = VideoRequest(text=SAMPLE_TEXT)
        with pytest.raises(HTTPException) as exc_info:
            await generate_video(request)
        assert exc_info.value.status_code == 500
        assert "Video processing failed" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_generate_video_file_not_ready(mock_media_data, mock_voice_file, mock_video_result):
    """Test when video file isn't ready after processing"""
    mock_video_result["watermarked"] = "/nonexistent/path.mp4"  # File won't exist
    
    with patch('your_module.fetch_media', new=AsyncMock(return_value=mock_media_data)), \
         patch('your_module.generate_voice', return_value=mock_voice_file), \
         patch('your_module.sync_audio_video', new=AsyncMock(return_value=mock_video_result)):
        
        request = VideoRequest(text=SAMPLE_TEXT)
        with pytest.raises(HTTPException) as exc_info:
            await generate_video(request)
        assert exc_info.value.status_code == 500
        assert "Video file could not be accessed" in str(exc_info.value.detail)

@pytest.mark.asyncio
async def test_generate_video_cancellation(mock_media_data, mock_voice_file, mock_video_result):
    """Test request cancellation during processing"""
    from your_module import ongoing_requests  # Import your module's ongoing_requests dict
    
    with patch('your_module.fetch_media', new=AsyncMock(return_value=mock_media_data)), \
         patch('your_module.generate_voice', return_value=mock_voice_file), \
         patch('your_module.sync_audio_video', new=AsyncMock(side_effect=lambda *args, **kwargs: (
             ongoing_requests.update({args[2]: {"status": "cancelled"}}),
             asyncio.sleep(0.1),
             mock_video_result
         ))):
        
        request = VideoRequest(text=SAMPLE_TEXT)
        with pytest.raises(HTTPException) as exc_info:
            await generate_video(request)
        assert exc_info.value.status_code == 499
        assert "Request cancelled by user" in str(exc_info.value.detail)