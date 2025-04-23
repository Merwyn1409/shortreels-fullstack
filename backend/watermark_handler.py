from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, TextClip
from config import WATERMARK_PATH

def apply_watermark(video_clip, watermark_path=WATERMARK_PATH):
    """Professional static watermark with perfect positioning"""
    
    if not hasattr(video_clip, 'duration'):
        raise ValueError("Input video must have duration set")

    # Base watermark settings
    main_logo = (ImageClip(watermark_path)
                .set_duration(video_clip.duration)
                .resize(height=min(120, video_clip.h//4)
                ))  # Larger center logo

    # Precise positions (relative coordinates)
    positions = [
        # Corners (15% from edges)
        (0.15, 0.15),  # Top-left
        (0.85, 0.15),  # Top-right
        (0.15, 0.85),  # Bottom-left
        (0.85, 0.85),  # Bottom-right
        
        # Mid-points (perfectly balanced)
        (0.5, 0.25),   # Upper-center
        (0.5, 0.75),   # Lower-center
        (0.25, 0.5),   # Middle-left
        (0.75, 0.5)    # Middle-right
    ]

    # Build elements
    elements = [video_clip]
    
    # Add all positioned watermarks
    for i, pos in enumerate(positions):
        opacity = 0.25 if i < 4 else 0.2  # Corners more visible than mid-points
        size = 0.1 if i < 4 else 0.06    # Corners slightly larger
        
        elements.append(
            main_logo.resize(height=video_clip.h*size)
            .set_opacity(opacity)
            .set_position(pos, relative=True)
        )

    # Optional faint text overlay
    text = (TextClip("PREVIEW ONLY",
                    fontsize=video_clip.h//15,
                    color='white',
                    font='Arial-Bold',
                    stroke_color='black',
                    stroke_width=1)
           .set_duration(video_clip.duration)
           .set_opacity(0.25)
           .set_position('center'))
    
    elements.append(text)

    return CompositeVideoClip(elements)