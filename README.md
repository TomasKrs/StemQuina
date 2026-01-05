# StemQuina
StemQuina is a simple multi-track audio player designed for musicians. It allows you to load song stems, manage practice markers, sync lyrics, and more. 

🛠 Installation & Requirements
Before running StemQuina, ensure you have Python 3.11 installed. Install the required libraries using the following command:
Bash

pip install pygame numpy pydub Pillow mutagen

Note: You also need ffmpeg installed on your system for pydub to handle MP3 files correctly.
🎹 Keyboard Shortcuts
Key	Action
Spacebar	Play / Pause
M	Add Marker at current position
1 - 9	Jump to Marker 1 through 9
Ctrl + T	Lyrics Timestamp: Insert timecode at current line (in Edit Mode)
Left Click	Seek to position on waveform
Right Click	Set Loop Point A
Ctrl + Right Click	Set Loop Point B
📖 Detailed Tutorial
1. Preparing Your Library

StemQuina looks for a folder named database in the same directory as the script. Each song must have its own subfolder:

    Original Track: Place your main MP3 file directly in the song folder.

    Lyrics: Put an .lrc file with the same name as the song folder in the song folder.

    Stems: Create a subfolder named stems/ and put your individual tracks (drums.mp3, bass.mp3, etc.) there.

2. Stem Mapping (Track Assignment)

When you load a song, StemQuina tries to auto-assign stems based on keywords (drum, bass, vocal). If it doesn't match correctly, use the Dropdown Menu above each track to manually select the correct file. The "NONE" option hides the track.
3. Synchronizing Lyrics (The Ctrl+T Workflow)

    Click EDIT LYRICS. The text area becomes white and editable.

    If you don't have timecodes, paste your plain text lyrics.

    Start the music.

    Every time the singer starts a new line, place your cursor at the beginning of that line in the editor and press CTRL + T.

    StemQuina will automatically insert the exact timestamp (e.g., [00:42.50]).

    Click SAVE & CLOSE to update the .lrc file.

4. Advanced Practice: A-B Looping

To master a difficult solo:

    Right-click the waveform where the solo starts (Point A).

    Ctrl + Right-click where it ends (Point B).

    Enable REPEAT. The player will now loop this section indefinitely.

    Use the < and > buttons in the footer to "nudge" the points by milliseconds for a perfect loop.
