#!/usr/bin/env python
"""
Updates the Strawberry music player SQLite database, using another Strawberry database, with the play and skip counts, and the last played date and time.
"""

import plistlib
import logging
import argparse
import sqlite3
import re
from datetime import datetime, timezone
from urllib.parse import quote, unquote, urlparse, urlunparse
import unicodedata

def dumpAllPlayed(cursor):
    findPlayed = "SELECT title,artist,url,playcount,lastplayed,skipcount FROM songs WHERE playcount <> 0"
    appLogger.debug(findPlayed)
    cursor.execute(findPlayed)
    for row in cursor.fetchall():
        print(row[0], row[1], row[2], row[3], datetime.fromtimestamp(row[4]), row[5])

def convertURL(iTunesURL):
    """
    Converts the iTunes URLs to a URL that can be found in the Strawberry database.
    """
    # Convert XML encoding of ampersands in the URL.
    iTunesURL = iTunesURL.replace('&#38;', '&')
    # iTunes encodes URLs, using UTF-8 encoding, but using a character and the combining diacritic,
    # instead of the noramlized, singular combined character including the diacritic, that Strawberry uses.
    # For example, iTunes: "n%CC%83", Strawberry: "%C3%B1"
    # So we need to decode the URL encoding, normalize the characters to the Normal Form
    # Composed form, then decode the unicode encoding into UTF-8, then reencode the URL.
    parsedURL = urlparse(iTunesURL) # parse the URL to ensure the URL separators don't get encoded.
    decodedPath = unquote(parsedURL.path)
    normalizedUnicodePath = unicodedata.normalize('NFC', decodedPath)
    # While Strawberry encodes the URL, it leaves a lot of characters unquoted.
    encodedURL = urlunparse((parsedURL.scheme,
                             parsedURL.netloc,
                             quote(normalizedUnicodePath, safe = "/&'(),[];!+=@"),
                             parsedURL.params,
                             parsedURL.query,
                             parsedURL.fragment))
    return encodedURL

def updatePlayDetails(strawberryDatabaseCursor, cleanedURL, newPlayCount, newLastPlayed, newSkipCount):
    # Set the track with the unassigned play count, last played date, and skip counts to the iTunes values:
    # Escape quote characters in URL for SQL use.
    cleanedURL = cleanedURL.replace("'", "''")
    updateCounts = f"UPDATE songs SET playcount = {newPlayCount}, skipcount = {newSkipCount}, lastplayed = {newLastPlayed} WHERE url = '{cleanedURL}'"
    appLogger.debug(updateCounts)
    strawberryDatabaseCursor.execute(updateCounts)
    # Determine if the field was updated.
    strawberryDatabaseCursor.execute('SELECT changes() FROM songs')
    result = strawberryDatabaseCursor.fetchone()
    if result[0] == 0:
        appLogger.warning(f"Unable to update {cleanedURL}")
        return False
    else:
        print(f"Updated Track: {cleanedURL} to play count {newPlayCount}, last played {newLastPlayed}, skip count {newSkipCount}")
        return True
    
def consolidateStrawberryTracks(updateDatabaseCursor, fromTrack, toTrack, do_update):
    """
    Update the to-track from the from-track, by using the latest lastplayed of the two
    tracks, and summing the playcounts.
    Returns the number of updates performed.
    """
    latestPlay = max(fromTrack['lastplayed'], toTrack['lastplayed'])
    totalPlays = fromTrack['playcount'] + toTrack['playcount']
    totalSkips = fromTrack['skipcount'] + toTrack['skipcount']
    cleanedURL = convertURL(toTrack['url'])
    appLogger.info(f"Updating URL {cleanedURL} to play count {totalPlays} last played {latestPlay} skip count {totalSkips}")
    updateCount = 0
    if (totalPlays > 0 or latestPlay > 0 or totalSkips > 0) and do_update:
        if updatePlayDetails(updateDatabaseCursor, cleanedURL, totalPlays, latestPlay, totalSkips):
            updateCount += 1
    else:
        appLogger.warning(f"Unplayed or skipped in the from and to tracks, not altering.")
    return updateCount

def findTrack(databaseCursor, trackURL):
    """
    Returns a dictionary containing the track found, or None if no matching track.
    """
    findSong = f"SELECT url, artist, title, playcount, lastplayed, skipcount FROM songs WHERE url LIKE '%{trackURL}%'"
    appLogger.debug(findSong)
    databaseCursor.execute(findSong)
    firstRow = databaseCursor.fetchone()
    if firstRow is not None:
        track = {
            'url': firstRow[0],
            'artist': firstRow[1],
            'title': firstRow[2],
            'playcount': firstRow[3],
            'lastplayed': firstRow[4],
            'skipcount': firstRow[5]
            # album TEXT,
            # albumartist TEXT,
            # track INTEGER NOT NULL DEFAULT -1,
            # disc INTEGER NOT NULL DEFAULT -1,
            # year INTEGER NOT NULL DEFAULT -1,
            # originalyear INTEGER NOT NULL DEFAULT -1,
            # genre TEXT,
            # compilation INTEGER NOT NULL DEFAULT 0,
            # composer TEXT,
            # performer TEXT,
            # grouping TEXT,
            # comment TEXT,
            # lyrics TEXT,
        }
        return track
    else:
        return None

def displayTrack(description, track):
    """
    Displays the track, supplied as a dictionary
    """
    print(description + ':', track)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Alters a Strawberry music player database, merging the play and skip counts, and last played date and time, from one track to another.')
    parser.add_argument('-v', '--verbose', action = 'count', help = 'Verbose output. Specify twice for debugging.', default = 0)
    parser.add_argument('-u', '--update-db', action = 'store', help = 'Path to the Strawberry database file to update.', type = str, default = 'strawberry.db')
    parser.add_argument('-w', '--write-updates', action = 'store_true', help = 'Write the update to the database, if not enabled, will simply show a dry run.', default = False)
    parser.add_argument('from_track', action = 'store', type = str, help = 'URL fragment of track to update from.')
    parser.add_argument('to_track', action = 'store', type = str, help = 'URL fragment of track to update.')
    
    args = parser.parse_args()

    # We set the logging value here so it's available to the core and master nodes.
    appLogger = logging.getLogger("consolidateTracks")
    logging.basicConfig()

    if args.verbose > 1:
        appLogger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        appLogger.setLevel(logging.INFO)

    updateSQLClient = sqlite3.connect(args.update_db)
    updateCursor = updateSQLClient.cursor()

    toTrack = findTrack(updateCursor, args.to_track)
    if toTrack is None:
        appLogger.error(f"No track found matching {args.from_track} to update to.")
    else:
        displayTrack('Update', toTrack)
    fromTrack = findTrack(updateCursor, args.from_track)
    if fromTrack is None:
        appLogger.error(f"No track found matching {args.from_track} to update from.")
    else:
        displayTrack('From', fromTrack)

    if toTrack is not None and fromTrack is not None:
        updateCount = consolidateStrawberryTracks(updateCursor, fromTrack, toTrack, args.write_updates)
        appLogger.info(f"Updated {updateCount} tracks")
        if updateCount > 0 and args.write_updates:
            # Save (commit) the changes.
            updateSQLClient.commit()

    updateSQLClient.close()
