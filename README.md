Strawberry Music Player Database Utilities
==========================================

This repository contains Python utilities to modify the open source
[Strawberry Music Player](https://www.strawberrymusicplayer.org/) [SQLite3](https://sqlite.org/index.html) database.
Typically this consists of bulk updates to the track play counts, skip counts, and last played dates.
These were produced in my process of transitioning from iTunes to Strawberry, and wanting
to retain my play analytics for a sizeable (> 20K tracks) music library.

These utilities perform the following functions:

- iTunes2Strawberry.py: Converts play analytics of an exported iTunes library to a Strawberry database.
- iTunesPlayLists2Strawberry.py: Adds non-smart playlists from an iTunes library file as an equivalent Strawberry favorite playlist.
- updateStrawberry.py: Updates play analytics of a Strawberry database from another Strawberry database.
- consolidateTracks.py: Merge the play analytics between two nominated tracks in a Strawberry database.

While these Python utilities should run correctly on Linux, MacOS and Windows platforms,
only MacOS has been tested, and documented here.

# Utility Usage

Each utility requires Python 3.7 or greater. The tools are run from the Terminal
console. The command line flags and usage are documented with the `-h` flag, e.g:

```
python3 iTunes2Strawberry.py -h
```

# Strawberry Database 

Strawberry's database resides at:

`~/Library/Application Support/Strawberry/Strawberry/strawberry.db`

on MacOS X.

The utilities will modify the Strawberry database `strawberry.db`.

**They can potentially damage your data if you make a mistake! Use at your own risk!!**

Obviously do not do modifications directly on `strawberry.db` used by the application,
make a copy to another directory, modify that, backup the working application version,
before overwriting it with your modified version. Launch Strawberry and carefully check
the modifications did what you want.

# Example Usage

First run and configure Strawberry, adding the directory that contains the audio files
which were within iTunes, and update the collection to ensure they are read and appear
within Strawberry. You can move/rename the directory, but you will then need to use the URL
replacement commands as demonstrated below. You will see all the playcounts and dates are
reset, of course.

Here is a typical set of commands to execute to safely import all play analytics from
iTunes on a MacOS machine, updating only those tracks in Strawberry which have no
plays. The Strawberry database is copied locally, a local backup is made, the script is
run, then the updated database replaces the version in use:

```
cp ~/Library/Application\ Support/Strawberry/Strawberry/strawberry.db strawberry.db
cp strawberry.db strawberry_backup.db
python3 iTunes2Strawberry.py -s strawberry.db -i Library.xml -p
cp strawberry.db ~/Library/Application\ Support/Strawberry/Strawberry/strawberry.db
```

Obviously ensure you have quit Strawberry before running these commands!

An example which limits the updates to a single album in the collection, and dumps out the
maximum diagnostics, while managing the move of the audio files from the iTunes directory
to another location (`Media` in this case) and change of artist formatting for Strawberry is:

```
python3 iTunes2Strawberry.py -v -v -s strawberry.db -i Library.xml -p -r 'iTunes/iTunes%20Music/Brian%20Eno%20_%20David%20Byrne' -w 'Media/Brian%20Eno%20&%20David%20Byrne' -f 'My Life in the Bush of Ghosts'
```

# Manual Database Investigation

Strawberry's database is a SQLite3 database. On MacOS, that database can be accessed with
the `sqlite3` command, but as noted above, duplicating the file to another directory, and safely run:

```
cp ~/Library/Application\ Support/Strawberry/Strawberry/strawberry.db .
/usr/bin/sqlite3 strawberry.db
```

The songs schema can be shown with:

```
.schema songs
```

Typical SQL can be used for queries, e.g:

```
SELECT COUNT(1) FROM songs;
SELECT COUNT(1) FROM songs WHERE playcount = 0;
SELECT title,artist,url,playcount,lastplayed,skipcount FROM songs WHERE artist = 'Big Black';
SELECT title,artist,album,url,lastplayed,skipcount FROM songs WHERE playcount = 0;
SELECT title,artist,album,url,lastplayed,skipcount FROM songs WHERE playcount = 0 AND lastplayed <> -1;
```

Updates to the database such as bulk change of the path of audio files would be, e.g:

```
UPDATE songs
SET url = REPLACE(url, 'file:///Volumes/Music-NAS/Music/iTunes/iTunes%20Music/Music', 'file:///Volumes/Music-NAS/Music/Media');
```

