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

def SQLEncodeString(queryString):
    """
    Escape quote characters in string for SQL use.
    """
    return queryString.replace("'", "''")

def createPlaylist(dbCursor, playlistName):
    """
    Create the playlist as a "favorite" of the given name in the strawberry database.
    Returns the row id of the newly created playlist, or -1 if there is an error creating it.
    """
    encodedPlaylistName = SQLEncodeString(playlistName)
    # Verify if a new playlist is created. Should we be adding to an existing one?
    playlistExistsAlready = f"SELECT COUNT(1) FROM playlists WHERE name = '{encodedPlaylistName}'"
    appLogger.debug(playlistExistsAlready)
    dbCursor.execute(playlistExistsAlready)
    row = dbCursor.fetchone()
    if row[0] == 0:
        addPlaylist = f"INSERT INTO playlists (name, ui_order, is_favorite) VALUES ('{encodedPlaylistName}', -1, 1)"
        appLogger.debug(addPlaylist)
        dbCursor.execute(addPlaylist)
        return dbCursor.lastrowid # The playlists rowid just created
    else:
        appLogger.error(f"Playlist named {playlistName} already present in strawberry database, not overwriting")
    return -1

def writePlayListItem(dbCursor, playlistName, playlistId, url):
    """
    Write each of the 'rowid's as 'collection_ids' for tracks in 'songs' that match the cleaned URLs to 'url' to playlist_items
    """
    findURL = f"SELECT rowid FROM songs WHERE url='{SQLEncodeString(url)}'"
    appLogger.debug(findURL)
    # These were determined by inspection of the database.
    item_type = 2  # These are hardwired to signal to Strawberry to refer back to the collection id when updating.
    source_type = 2 # Hardwired.
    dbCursor.execute(findURL)
    row = dbCursor.fetchone()
    if row is not None:
        collection_id = row[0] # songs rowid, i.e. the collection_id
        writePlaylistItem = f"INSERT INTO playlist_items (playlist, collection_id, type, source) VALUES ({playlistId}, {collection_id}, {item_type}, {source_type})"
        appLogger.debug(writePlaylistItem)
        dbCursor.execute(writePlaylistItem)
        # Check the insertion worked 
        dbCursor.execute('SELECT changes() FROM playlist_items')
        result = dbCursor.fetchone()
        return result[0] > 0
    else:
        appLogger.warning(f"Unable to find {url} in strawberry database to insert into {playlistName}")
    return False

def importPlaylists(iTunesTree, strawberryDatabaseCursor, replaceURLList, onlyPlaylist = None, includeSmartPlaylists = False):
    """
    Create strawberry playlists from either all iTunes playlists or a single playlist.
    :param iTunesTree: Reads from the iTunes dictionary tree.
    :param strawberryDatabaseCursor: writes to the strawberry database indexed by this cursor.
    :param replaceURLList: A list of tuples, each containing a regular expression and it's replacement to apply to the URL.
    :param onlyPlaylist: If not None, only the named playlist will be imported.
    :param includeSmartPlaylists: if True, convert iTunes smart playlists into Strawberry static playlists.
    """
    appLogger.debug(iTunesTree.keys())
    appLogger.info("Searching for playlist {onlyPlaylist} tracks in database in iTunes library file v{Major Version}.{Minor Version} created {Date}".format(onlyPlaylist = onlyPlaylist, **iTunesTree))
    
    updateCount = 0
    # iTunes include some playlists which hold the entire collection, so we exclude
    # creating those, unless they are explicitly named as an onlyPlaylist.
    excludePlaylists = ['Library', 'Music', 'Downloaded']
    for playlistCount, playlist in enumerate(iTunesTree['Playlists']):
        smartPlaylist = 'Smart Criteria' in playlist
        appLogger.debug(f"Playlist {playlistCount}: {playlist['Name']}, {playlist['Description']}, Smart playlist {smartPlaylist}")
        if (playlist['Name'] not in excludePlaylists and onlyPlaylist is None) or playlist['Name'] == onlyPlaylist:
            if 'Playlist Items' not in playlist:
                appLogger.warning(f"No items in {playlist['Name']}, not creating.")
            elif smartPlaylist and not includeSmartPlaylists:
                appLogger.warning(f"Smart playlist '{playlist['Name']}' excluded, needs manual recreation in Strawberry.")
            else:
                strawberryPlayListId = createPlaylist(strawberryDatabaseCursor, playlist['Name'])
                if strawberryPlayListId < 0:
                    continue
                for itemPosition, playlistItem in enumerate(playlist['Playlist Items']):
                    trackId = str(playlistItem['Track ID'])
                    if trackId in iTunesTree['Tracks']:
                        trackToAdd = iTunesTree['Tracks'][trackId]
                        # For some crazy reason we can have entries in the iTunes Library without file URLs?
                        if 'Location' not in trackToAdd:
                            appLogger.warning(f"No Location field, skipping {trackId} '{trackToAdd['Name']}' by {trackToAdd['Artist']}.")
                            continue

                        # Retrieve the URL, apply the cleaning and replacement to search for
                        # the equivalent song in strawberry database.
                        cleanedURL = convertURL(trackToAdd['Location'])
                        alternateURL = cleanedURL
                        # Apply all substitutions to the same cleaned URL
                        for URLreplace, replaceWith in replaceURLList:
                            alternateURL = re.sub(URLreplace, replaceWith, alternateURL, count = 1)
                            # appLogger.debug(f"{URLreplace} replaced by {replaceWith} producing {alternateURL}")
                        appLogger.info(f"Searching for track id: {trackId} at {alternateURL} in strawberry")
                        if writePlayListItem(strawberryDatabaseCursor, playlist['Name'], strawberryPlayListId, alternateURL):
                            updateCount += 1
                        else:
                            appLogger.error(f"Unable to write {alternateURL} to playlist {playlist['Name']} at position {itemPosition}.")
                    else:
                        appLogger.warning(f"Can't find track id: {trackId} in iTunes library?")
    return updateCount

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Alters a Strawberry music player database, adding playlists from the iTunes Library XML file.')
    parser.add_argument('-v', '--verbose', action = 'count', help = 'Verbose output. Specify twice for debugging.', default = 0)
    parser.add_argument('-s', '--strawberry', action = 'store', help = 'Path to the Strawberry database file. Defaults to %(default)s.', type = str, default = 'strawberry.db')
    parser.add_argument('-i', '--itunes', action = 'store', help = 'Path to the iTunes exported Library.xml file. Defaults to %(default)s.', type = str, default = 'Library.xml')
    parser.add_argument('--convert-smart-playlists', action = 'store_true', help = 'Convert iTunes smart playlists to Strawberry static playlists.')
    parser.add_argument('-p', '--import-playlist', action = 'store', help = 'Only import the named playlist.', default = None)
    parser.add_argument('-r', '--replace-url', action = 'append', nargs=2, help = 'The URL regexp to replace, and the URL fragment to replace with.')
    
    args = parser.parse_args()

    # We set the logging value here so it's available to the core and master nodes.
    appLogger = logging.getLogger("iTunesPlayLists2Strawberry")
    logging.basicConfig()

    if args.verbose > 1:
        appLogger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        appLogger.setLevel(logging.INFO)

    sqlClient = sqlite3.connect(args.strawberry)
    cursor = sqlClient.cursor()

    with open(args.itunes, 'rb') as libraryFile:
        root = plistlib.load(libraryFile, fmt = plistlib.FMT_XML)
        updateCount = importPlaylists(root, cursor, args.replace_url,
                                      onlyPlaylist = args.import_playlist,
                                      includeSmartPlaylists = args.convert_smart_playlists)

    # Save (commit) the changes
    appLogger.info(f"Added {updateCount} tracks")
    if updateCount > 0:
        # Save (commit) the changes
        sqlClient.commit()

    sqlClient.close()
