#!/usr/bin/env python
"""
Converts an iTunes exported library XML file, updating the Strawberry music player SQLite
database, with the play and skip counts, and the last played date and time.
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

def SQLEncodeURL(url):
    """
    Escape quote characters in URL for SQL use.
    """
    return url.replace("'", "''")

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

def updatePlayDetails(strawberryDatabaseCursor, track, cleanedURL, alternateURL):
    # convert the Play Date UTC value into the integer used by Strawberry:
    newLastPlayed = int(track['Play Date UTC'].timestamp())
    # Set the track with the unassigned play count, last played date, and skip counts to the iTunes values:
    updateCounts = "UPDATE songs SET playcount = {Play Count}, skipcount = {Skip Count}, lastplayed = {newLastPlayed} WHERE (url = '{cleanedURL}' OR url = '{alternateURL}') AND playcount = 0".format(newLastPlayed = newLastPlayed, cleanedURL = SQLEncodeURL(cleanedURL), alternateURL = SQLEncodeURL(alternateURL), **track)
    appLogger.debug(updateCounts)
    strawberryDatabaseCursor.execute(updateCounts)
    # Determine if the field was updated.
    strawberryDatabaseCursor.execute('SELECT changes() FROM songs')
    result = strawberryDatabaseCursor.fetchone()
    if result[0] == 0:
        appLogger.warning(f"Unable to update {cleanedURL}")
        return False
    else:
        appLogger.info("Updated Track: {Name}, {Artist}, {Play Count}, {Play Date UTC}, {Skip Count}, {Skip Date}, {Location}".format(**track))
        return True
    
def processUnplayedStrawberyFiles(iTunesTree, strawberryDatabaseCursor, replaceURL,
                                  replaceWith, findClause = ''):
    """
    Only update files in the strawberry database which have play counts of zero.
    Returns the number of updates performed.
    """
    appLogger.debug(iTunesTree.keys())
    appLogger.info("Searching for unplayed tracks in database in iTunes library file v{Major Version}.{Minor Version} created {Date}".format(**iTunesTree))
    URLreplace = re.compile(replaceURL)
    allUnplayedSongs = "SELECT url, artist, title, playcount, skipcount, lastplayed FROM songs WHERE playcount = 0"
    if findClause is not None and len(findClause) > 0:
        allUnplayedSongs += ' AND ' + findClause
    appLogger.debug(allUnplayedSongs)
    updateCount = 0
    strawberryDatabaseCursor.execute(allUnplayedSongs)
    for row in strawberryDatabaseCursor.fetchall():
        appLogger.debug(row[0])
        found = False
        # Now we need to iterate through the tree, which is unsorted, so exhaustively searching it.
        # TODO Perhaps sort?
        for trackCount, (trackNumber, track) in enumerate(iTunesTree['Tracks'].items()):
            # For some crazy reason we can have entries in the iTunes Library without file URLs?
            if 'Location' not in track:
                continue
            cleanedURL = convertURL(track['Location'])
            # Generate the alternative version of the URL, with the specified replacements prefix.
            alternateURL = URLreplace.sub(replaceWith, cleanedURL, count = 1)
            # Find the track in iTunes
            track = imputeTrackFields(track)
            if row[0] == cleanedURL or row[0] == alternateURL:
                found = True
                appLogger.debug(f"Matched URL {cleanedURL}, {alternateURL}")
                if track['Play Count'] > 0:
                    if updatePlayDetails(strawberryDatabaseCursor, track, cleanedURL, alternateURL):
                        updateCount += 1
                else:
                    appLogger.warning(f"Unplayed in iTunes database, not altering play count: {row[0]}")
                break
            elif row[1] == track['Artist'] and row[2] == track['Name']:
                found = True
                appLogger.debug("Perhaps this track # {trackNumber}: {Name}, {Artist}, {Play Count}, {Play Date UTC}, {Skip Count}, {Skip Date}, {Location}".format(trackNumber = trackNumber, **track))
                appLogger.debug(f"In database {row[0]}")
                if updatePlayDetails(strawberryDatabaseCursor, track, row[0], ''):
                    updateCount += 1
                break
        if not found:
            appLogger.warning(f"Unable to find {row[0]}")
    return updateCount

def processAlliTunesFiles(iTunesTree, strawberryDatabaseCursor,
                          findClause, updateExisting, replaceURL, replaceWith):
    """
    Iterate through all tracks in the iTunes library tree structure.

    :param findClause: A dictionary of keys and regexps to match on.
    :param updateExisting:
    :param replaceURL: 
    :param replaceWith:
    """
    appLogger.debug(iTunesTree.keys())
    appLogger.info("Reading {trackCount} tracks from iTunes library file v{Major Version}.{Minor Version} created {Date}".format(trackCount = len(iTunesTree['Tracks']), **iTunesTree))
    URLreplace = re.compile(replaceURL)

    updateCount = 0
    for trackCount, (trackNumber, track) in enumerate(iTunesTree['Tracks'].items()):
        # For some crazy reason we can have entries in the iTunes Library without file URLs?
        if 'Location' not in track:
            appLogger.warning(f"No Location field, skipping {track}")
            continue
        track = imputeTrackFields(track)
        # convert the Play Date UTC value into the integer used by Strawberry:
        newLastPlayed = int(track['Play Date UTC'].timestamp())
        appLogger.debug("New last played timestamp {}".format(newLastPlayed))

        try:
            appLogger.debug("Track # {trackNumber}: {Name}, {Artist}, {Play Count}, {Play Date UTC}, {Skip Count}, {Skip Date}, {Location}".format(trackNumber = trackNumber, **track))
        except Exception as e:
            appLogger.error("Missing {} in {}".format(e, track))

        cleanedURL = convertURL(track['Location'])
        # Generate the alternative version of the URL, with the specified replacements prefix.
        alternateURL = URLreplace.sub(replaceWith, cleanedURL, count = 1)
        didUpdate = False
        if updateExisting:
            # If there are tracks already in the SQLite DB, just update the play count
            # adding the count from iTunes, but leave the last played date unchanged.
            updateCounts = "UPDATE songs SET playcount = playcount + {Play Count}, skipcount = skipcount + {Skip Count} WHERE (url = '{cleanedURL}' OR url = '{alternateURL}') AND playcount <> 0".format(cleanedURL = SQLEncodeURL(cleanedURL), alternateURL = SQLEncodeURL(alternateURL), **track)
            appLogger.debug(updateCounts)
            strawberryDatabaseCursor.execute(updateCounts)
            # Determine if the field was updated.
            strawberryDatabaseCursor.execute('SELECT changes() FROM songs')
            result = strawberryDatabaseCursor.fetchone()
            didUpdate = result[0] > 0
            updateCount += 1
        if not didUpdate:
            # TODO updatePlayDetails(strawberryDatabaseCursor, track)
            # Set all tracks with unassigned play counts, last played date, and skip counts to the iTunes values:
            updateCounts = "UPDATE songs SET playcount = {Play Count}, skipcount = {Skip Count}, lastplayed = {newLastPlayed} WHERE (url = '{cleanedURL}' OR url = '{alternateURL}') AND playcount = 0".format(newLastPlayed = newLastPlayed, cleanedURL = SQLEncodeURL(cleanedURL), alternateURL = SQLEncodeURL(alternateURL), **track)
            # updateCounts = "SELECT playcount, skipcount, lastplayed FROM songs WHERE (url = '{Location}' OR url = '{alternateURL}') AND lastplayed = -1".format(newLastPlayed = newLastPlayed, alternateURL = alternateURL, **track)
            appLogger.debug(updateCounts)
            strawberryDatabaseCursor.execute(updateCounts)
            # Determine if the field was updated.
            strawberryDatabaseCursor.execute('SELECT changes() FROM songs')
            result = strawberryDatabaseCursor.fetchone()
            if result[0] == 0:
                appLogger.debug(f"Unable to update {cleanedURL}")
            else:
                appLogger.info("Updated Track # {trackNumber}: {Name}, {Artist}, {Play Count}, {Play Date UTC}, {Skip Count}, {Skip Date}, {Location}".format(trackNumber = trackNumber, **track))
    return updateCount
    
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Alters a Strawberry music player database, setting the play and skip counts, and last played date and time from the iTunes Library XML file.')
    parser.add_argument('-v', '--verbose', action = 'count', help = 'Verbose output. Specify twice for debugging.', default = 0)
    parser.add_argument('-s', '--strawberry', action = 'store', help = 'Path to the Strawberry database file.', type = str, default = 'strawberry.db')
    parser.add_argument('-i', '--itunes', action = 'store', help = 'Path to the iTunes exported Library.xml file.', type = str, default = 'Library.xml')
    parser.add_argument('-f', '--find', action = 'store', help = 'Only update the named album', default = '')
    parser.add_argument('-p', '--update-unplayed', action = 'store_true', help = 'Update existing records if they have a zero play count')
    parser.add_argument('-u', '--update-existing', action = 'store_true', help = 'Update the existing records if they already have play counts')
    parser.add_argument('-d', '--dump-existing', action = 'store_true', help = 'Display the existing tracks if they already have play counts')
    parser.add_argument('-r', '--replace-url', action = 'store', help = 'The URL regexp to replace', default = '')
    parser.add_argument('-w', '--replace-with', action = 'store', help = 'The URL fragment to replace with', default = '')
    
    args = parser.parse_args()

    # We set the logging value here so it's available to the core and master nodes.
    appLogger = logging.getLogger("iTunes2Strawberry")
    logging.basicConfig()

    if args.verbose > 1:
        appLogger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        appLogger.setLevel(logging.INFO)

    sqlClient = sqlite3.connect(args.strawberry)
    cursor = sqlClient.cursor()

    if args.dump_existing:
        dumpAllPlayed(cursor)
    
    with open(args.itunes, 'rb') as libraryFile:
        root = plistlib.load(libraryFile, fmt = plistlib.FMT_XML)
        findClause = f"album = '{args.find}'" if len(args.find) > 0 else ''
        if args.update_unplayed:
            updateCount = processUnplayedStrawberyFiles(root, cursor, args.replace_url, args.replace_with,
                                                        findClause = findClause)
        else:
            updateCount = processAlliTunesFiles(root, cursor, findClause, args.update_existing, args.replace_url, args.replace_with)

    # Save (commit) the changes
    appLogger.info(f"Updated {updateCount} tracks")
    if updateCount > 0:
        # Save (commit) the changes
        sqlClient.commit()

    sqlClient.close()
