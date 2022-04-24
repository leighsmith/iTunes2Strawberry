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
    # Finally escape quote characters in URL for SQL use.
    return encodedURL.replace("'", "''")

def imputeTrackFields(track):
    """
    Clean up the track parameters if there are missing fields.
    """
    if 'Skip Count' not in track:
        track['Skip Count'] = 0
    if 'Skip Date' not in track:
        track['Skip Date'] = 0 # TODO Not right.
    if 'Artist' not in track:
        track['Artist'] = 'Unknown'
    if 'Name' not in track:
        track['Name'] = 'Untitled'
    if 'Play Count' not in track:
        track['Play Count'] = 0
    if 'Play Date UTC' not in track:
        track['Play Date UTC'] = datetime.utcnow()
    return track

def updatePlayDetails(strawberryDatabaseCursor, cleanedURL, newPlayCount, newLastPlayed, newSkipCount):
    # Set the track with the unassigned play count, last played date, and skip counts to the iTunes values:
    updateCounts = f"UPDATE songs SET playcount = {newPlayCount}, skipcount = {newSkipCount}, lastplayed = {newLastPlayed} WHERE url = '{cleanedURL}' AND playcount = 0"
    #appLogger.debug(updateCounts)
    # return False
    strawberryDatabaseCursor.execute(updateCounts)
    # Determine if the field was updated.
    strawberryDatabaseCursor.execute('SELECT changes() FROM songs')
    result = strawberryDatabaseCursor.fetchone()
    if result[0] == 0:
        appLogger.warning(f"Unable to update {cleanedURL}")
        return False
    else:
        appLogger.info(f"Updated Track: {cleanedURL} to {newPlayCount}, {newLastPlayed}, {newSkipCount}")
        return True
    
def processUnplayedStrawberyFiles(updateDatabaseCursor, fromDatabaseCursor):
    """
    Only update files in the strawberry database which have play counts of zero.
    Returns the number of updates performed.
    """
    appLogger.info("Searching for unplayed tracks in database in the from database")
    allUnplayedSongs = "SELECT url, artist, title, playcount, lastplayed, skipcount FROM songs WHERE playcount = 0"
    appLogger.debug(allUnplayedSongs)
    updateCount = 0
    updateDatabaseCursor.execute(allUnplayedSongs)
    for index, row in enumerate(updateDatabaseCursor.fetchall()):
        cleanedURL = convertURL(row[0])
        # retrieveSong = f"SELECT url, artist, title, playcount, skipcount, lastplayed FROM songs WHERE url='{row[0]}'"
        retrieveSong = f"SELECT url, artist, title, playcount, lastplayed, skipcount FROM songs WHERE url='{cleanedURL}'"
        appLogger.debug(retrieveSong)
        fromDatabaseCursor.execute(retrieveSong)
        found = False
        for fromRow in fromDatabaseCursor.fetchall():
            appLogger.info(f"Matched URL {fromRow[0]}, play count {fromRow[3]} last played {fromRow[4]} skip count {fromRow[5]}")
            found = True
            if fromRow[3] > 0:
                if updatePlayDetails(updateDatabaseCursor, cleanedURL, fromRow[3], fromRow[4], fromRow[5]):
                    updateCount += 1
                break
            else:
                appLogger.warning(f"Unplayed in the from database, not altering play count: {row[0]}")
        if not found:
            appLogger.debug(f"Unable to find {row[0]}")
    return updateCount


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Alters a Strawberry music player database, setting the play and skip counts, and last played date and time from the iTunes Library XML file.')
    parser.add_argument('-v', '--verbose', action = 'count', help = 'Verbose output. Specify twice for debugging.', default = 0)
    parser.add_argument('-u', '--update-db', action = 'store', help = 'Path to the Strawberry database file to update.', type = str, default = 'strawberry.db')
    parser.add_argument('-f', '--from-db', action = 'store', help = 'Path to the Strawberry database to update from.', default = '')
    parser.add_argument('-d', '--dump-existing', action = 'store_true', help = 'Display the existing tracks if they already have play counts')
    
    args = parser.parse_args()

    # We set the logging value here so it's available to the core and master nodes.
    appLogger = logging.getLogger("strawberry2Strawberry")
    logging.basicConfig()

    if args.verbose > 1:
        appLogger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        appLogger.setLevel(logging.INFO)

    # replaceOriginal = 'iTunes%20Music/(?!Music/)'
    # replaceWith = 'iTunes%20Music/Music/'
    
    updateSQLClient = sqlite3.connect(args.update_db)
    updateCursor = updateSQLClient.cursor()

    fromSQLClient = sqlite3.connect(args.from_db)
    fromCursor = fromSQLClient.cursor()
    
    if args.dump_existing:
        dumpAllPlayed(updateCursor)
    
    updateCount = processUnplayedStrawberyFiles(updateCursor, fromCursor)
    appLogger.info(f"Updated {updateCount} tracks")
    if updateCount > 0:
        # Save (commit) the changes
        updateSQLClient.commit()

    updateSQLClient.close()

    fromSQLClient.close()
