Strawberry Music Player Database Utilities
==========================================

This repository contains Python utilities to modify the open source
[Strawberry Music Player](https://www.strawberrymusicplayer.org/) [SQLite3](https://sqlite.org/index.html) database.
Typically this consists of bulk updates to the track play counts, skip counts, and last played dates.
These were produced in my process of transitioning from iTunes to Strawberry, and wanting
to retain my play analytics for a sizeable (> 20K tracks) music library.

These utilities perform the following functions:

- iTunes2Strawberry.py: Converts play analytics of an exported iTunes library to a Strawberry database.
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

# Manual Database Investigation

Strawberry's database is a SQLite3 database. On MacOS, that database can be accessed with
the `sqlite3` command, but as noted above, duplicating the file to another directory, and safely run:

```
cp ~/Library/Application\ Support/Strawberry/Strawberry/strawberry.db .
/usr/bin/sqlite3 strawberry.db
```

The schema can be shown with:

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

