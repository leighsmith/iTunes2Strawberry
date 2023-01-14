#!/usr/bin/env python
"""
Updates the Strawberry music player SQLite database, with the play counts, and the last
played date and time from a nominated ListenBrainz account.
"""

import logging
import argparse
import sqlite3
import pylistenbrainz
import time

def sql_encode(string):
    """
    Escape quote characters in string for SQL use.
    """
    return string.replace("'", "''")

def get_track_from_strawberry(cursor, listen):
    """
    Returns the object of the track in the strawberry database, matching the listened
    object. Returns None if unable to find it.
    """
    # Search on the track name and the artist name. We need to do it in a case insensitive
    # manner, since the track and artists strings can often differ in capitalisation
    # compared between Strawberry and Listenbrainz.
    find_track = f"SELECT url, playcount, lastplayed FROM songs WHERE artist = '{sql_encode(listen.artist_name)}' AND title = '{sql_encode(listen.track_name)}' COLLATE NOCASE"
    appLogger.debug(find_track)
    cursor.execute(find_track)
    found_track = None
    for row in cursor.fetchall():
        found_track = {
            'url': row[0],
            'playcount': row[1],
            'lastplayed': row[2]
        }
    return found_track

def get_updated_plays(cursor, listens):
    """
    Returns dictionary (keyed by strawberry file URL) of play counts and last played
    times for tracks in the listens which are newer than that in the strawberry database.
    """
    updated_plays = dict()
    for listen in listens:
        appLogger.info(f"Track name: {listen.track_name}")
        appLogger.info(f"Artist name: {listen.artist_name}")
        appLogger.info(f"At: {time.ctime(listen.listened_at)}")
        #appLogger.debug(f"From: {listen.listening_from}")
        strawberry_track = get_track_from_strawberry(cursor, listen)
        if strawberry_track is not None:
            # Check if we should increment the play count, if the last_played timestamp is
            # greater than the strawberry track's last played timestamp.
            appLogger.info("In Strawberry database last played {}".format(time.ctime(strawberry_track['lastplayed'])))
            if listen.listened_at > strawberry_track['lastplayed']: # Needs better fuzzy match.
                # The updated plays are indexed by the strawberry track URL.
                if strawberry_track['url'] not in updated_plays:
                    # Update the play count and the last played time.
                    strawberry_track['lastplayed'] = listen.listened_at
                    strawberry_track['playcount'] += 1
                    updated_plays[strawberry_track['url']] = strawberry_track
                else:
                    updated_plays[strawberry_track['url']]['playcount'] += 1
        else:
            appLogger.warning(f"Track '{listen.track_name}' by '{listen.artist_name}' not in Strawberry database?")
    return updated_plays
                    
def update_database(cursor, updated_plays):
    """
    Updates the Strawberry database with the new play counts and last played timestamps
    for tracks that were determined to be newer than those already in the database.
    """
    update_count = 0
    for track_url, track_plays in updated_plays.items():
        appLogger.info(f"Update {track_url} with {track_plays['playcount']} plays most recently at {time.ctime(track_plays['lastplayed'])}")
        update_plays = f"UPDATE songs SET playcount = {track_plays['playcount']}, lastplayed = {track_plays['lastplayed']} WHERE url = '{sql_encode(track_url)}'"
        appLogger.debug(update_plays)
        cursor.execute(update_plays)
        # Determine if the field was updated.
        cursor.execute('SELECT changes() FROM songs')
        result = cursor.fetchone()
        update_count += int(result[0] > 0)
    return update_count
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Alters a Strawberry music player database, setting the play count, and last played date and time from a ListenBrainz account.')
    parser.add_argument('-v', '--verbose', action = 'count', help = 'Verbose output. Specify twice for debugging.', default = 0)
    parser.add_argument('-s', '--strawberry', action = 'store', help = 'Path to the Strawberry database file.', type = str, default = 'strawberry.db')
    parser.add_argument('-b', '--before', action  = 'store', help = 'Retrieve listens before the given date & time', default = None)
    parser.add_argument('user', action = 'store', help = 'The ListenBrainz user', default = '')
    args = parser.parse_args()

    # We set the logging value here so it's available to the core and master nodes.
    appLogger = logging.getLogger("listenbrainz2strawberry")
    logging.basicConfig()

    if args.verbose > 1:
        appLogger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        appLogger.setLevel(logging.INFO)

    sqlClient = sqlite3.connect(args.strawberry)
    strawberry_db_cursor = sqlClient.cursor()
    listenbrainz_user = args.user
    # Determine the Unix epoch time from the human readable local timezone time.
    max_ts = int(time.mktime(time.strptime(args.before))) if args.before is not None else None
    appLogger.debug(f"Maximum timestamp {max_ts}")

    client = pylistenbrainz.ListenBrainz()
    listens = client.get_listens(username=listenbrainz_user, max_ts=max_ts, count=100)
    updated_plays = get_updated_plays(strawberry_db_cursor, listens)
    # Now update the playcounts and last played using the dictionary
    update_count = update_database(strawberry_db_cursor, updated_plays)

    # Save (commit) the changes
    appLogger.info(f"Updated {update_count} tracks")
    if update_count > 0:
        # Save (commit) the changes
        sqlClient.commit()

    sqlClient.close()
