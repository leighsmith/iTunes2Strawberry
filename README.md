Strawberry's database resides at:

`~/Library/Application\ Support/Strawberry/Strawberry/strawberry.db`

on MacOS X.

This is a SQLite3 database. On MacOS, that database can be accessed with the sqlite3
command:

```
/usr/bin/sqlite3 ~/Library/Application\ Support/Strawberry/Strawberry/strawberry.db
```

```
.schema songs
```

```
SELECT COUNT(1) FROM songs;
```

```
SELECT title,artist,url,playcount,lastplayed,skipcount FROM songs WHERE artist = 'Big Black';
```

```
UPDATE songs
SET url = REPLACE(url, 'file:///Volumes/Music-NAS/Music/iTunes/iTunes%20Music/Music', 'file:///Volumes/Music-NAS/Music/Media');
```
