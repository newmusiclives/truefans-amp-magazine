"""Email-safe audio embed cards for Spotify, YouTube, and Apple Music.

All generated HTML uses inline CSS and table-based layout so it renders
correctly inside email clients that strip ``<style>`` blocks and disallow
``<iframe>`` / ``<script>`` elements.
"""

from __future__ import annotations

from markupsafe import escape


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_CARD_BG = "#1e1e2e"
_CARD_BORDER = "#2e2e3e"
_TEXT_PRIMARY = "#ffffff"
_TEXT_SECONDARY = "#a0a0b0"
_BORDER_RADIUS = "8px"

_SPOTIFY_GREEN = "#1DB954"
_YOUTUBE_RED = "#FF0000"
_APPLE_PINK = "#FA2D48"


# ---------------------------------------------------------------------------
# Individual generators
# ---------------------------------------------------------------------------

def generate_spotify_embed(
    track_or_album_url: str,
    title: str,
    artist_name: str,
    thumbnail_url: str,
) -> str:
    """Return an email-safe HTML card linking to a Spotify track or album.

    The card shows the album/track art, title, artist name and a styled
    "Listen on Spotify" button.
    """
    title_esc = escape(title)
    artist_esc = escape(artist_name)
    thumb_esc = escape(thumbnail_url)
    url_esc = escape(track_or_album_url)

    return f"""\
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;margin:16px auto;border:1px solid {_CARD_BORDER};border-radius:{_BORDER_RADIUS};background:{_CARD_BG};overflow:hidden;">
  <tr>
    <td width="80" style="vertical-align:top;padding:12px;">
      <a href="{url_esc}" target="_blank" style="text-decoration:none;">
        <img src="{thumb_esc}" alt="{title_esc}" width="80" height="80"
             style="display:block;border-radius:4px;object-fit:cover;" />
      </a>
    </td>
    <td style="vertical-align:middle;padding:12px 12px 12px 0;">
      <a href="{url_esc}" target="_blank"
         style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;color:{_TEXT_PRIMARY};text-decoration:none;display:block;line-height:1.3;">
        {title_esc}
      </a>
      <span style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{_TEXT_SECONDARY};display:block;margin-top:2px;">
        {artist_esc}
      </span>
      <a href="{url_esc}" target="_blank"
         style="display:inline-block;margin-top:8px;padding:6px 16px;background:{_SPOTIFY_GREEN};color:#000000;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;text-decoration:none;border-radius:20px;">
        Listen on Spotify
      </a>
    </td>
  </tr>
</table>"""


def generate_youtube_embed(
    video_url: str,
    title: str,
    thumbnail_url: str,
) -> str:
    """Return an email-safe HTML card linking to a YouTube video.

    Shows a thumbnail with a centred play-button overlay, the video title,
    and a "Watch on YouTube" button.
    """
    title_esc = escape(title)
    thumb_esc = escape(thumbnail_url)
    url_esc = escape(video_url)

    return f"""\
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;margin:16px auto;border:1px solid {_CARD_BORDER};border-radius:{_BORDER_RADIUS};background:{_CARD_BG};overflow:hidden;">
  <tr>
    <td style="padding:0;text-align:center;position:relative;">
      <a href="{url_esc}" target="_blank" style="text-decoration:none;display:block;position:relative;">
        <img src="{thumb_esc}" alt="{title_esc}" width="480"
             style="display:block;width:100%;height:auto;border-radius:{_BORDER_RADIUS} {_BORDER_RADIUS} 0 0;" />
        <!--[if !mso]><!-->
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:56px;height:56px;background:rgba(0,0,0,0.7);border-radius:50%;text-align:center;line-height:56px;">
          <span style="font-size:28px;color:#ffffff;margin-left:4px;">&#9654;</span>
        </div>
        <!--<![endif]-->
      </a>
    </td>
  </tr>
  <tr>
    <td style="padding:12px;">
      <a href="{url_esc}" target="_blank"
         style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;color:{_TEXT_PRIMARY};text-decoration:none;display:block;line-height:1.3;">
        {title_esc}
      </a>
      <a href="{url_esc}" target="_blank"
         style="display:inline-block;margin-top:8px;padding:6px 16px;background:{_YOUTUBE_RED};color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;text-decoration:none;border-radius:20px;">
        Watch on YouTube
      </a>
    </td>
  </tr>
</table>"""


def generate_apple_music_embed(
    url: str,
    title: str,
    artist_name: str,
    thumbnail_url: str,
) -> str:
    """Return an email-safe HTML card linking to Apple Music."""
    title_esc = escape(title)
    artist_esc = escape(artist_name)
    thumb_esc = escape(thumbnail_url)
    url_esc = escape(url)

    return f"""\
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;margin:16px auto;border:1px solid {_CARD_BORDER};border-radius:{_BORDER_RADIUS};background:{_CARD_BG};overflow:hidden;">
  <tr>
    <td width="80" style="vertical-align:top;padding:12px;">
      <a href="{url_esc}" target="_blank" style="text-decoration:none;">
        <img src="{thumb_esc}" alt="{title_esc}" width="80" height="80"
             style="display:block;border-radius:4px;object-fit:cover;" />
      </a>
    </td>
    <td style="vertical-align:middle;padding:12px 12px 12px 0;">
      <a href="{url_esc}" target="_blank"
         style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:700;color:{_TEXT_PRIMARY};text-decoration:none;display:block;line-height:1.3;">
        {title_esc}
      </a>
      <span style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{_TEXT_SECONDARY};display:block;margin-top:2px;">
        {artist_esc}
      </span>
      <a href="{url_esc}" target="_blank"
         style="display:inline-block;margin-top:8px;padding:6px 16px;background:{_APPLE_PINK};color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;text-decoration:none;border-radius:20px;">
        Listen on Apple Music
      </a>
    </td>
  </tr>
</table>"""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def generate_embed_html(
    embed_type: str,
    external_id: str,
    embed_url: str,
    thumbnail_url: str,
    title: str,
    artist_name: str,
) -> str:
    """Dispatch to the appropriate embed generator based on *embed_type*.

    Supported types: ``spotify``, ``youtube``, ``apple_music``.
    Returns an empty string for unrecognised types.
    """
    embed_type = embed_type.lower().strip()

    if embed_type == "spotify":
        return generate_spotify_embed(embed_url, title, artist_name, thumbnail_url)
    if embed_type == "youtube":
        return generate_youtube_embed(embed_url, title, thumbnail_url)
    if embed_type in ("apple_music", "apple-music", "applemusic"):
        return generate_apple_music_embed(embed_url, title, artist_name, thumbnail_url)

    return ""
