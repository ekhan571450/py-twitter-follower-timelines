#!/usr/bin/python3

"""
Filename: followers.py
"""

import sys
import argparse
import json
import time
import math
import tweepy
import couchdb

"""
  Function Definitions
"""

# This function retrieves a list of unique user IDs from a CouchDB view
def get_queue ( db_tweets ):
  i = 0
  queue = []
  try:
    for row in db_tweets.view('app/users_simple', wrapper=None, group='true'):
      queue.append(row.key)
      i += 1
    return queue
  except:
    print ('Failed to retrieve view: ' + db_tweets.name + '/app/_view/users_simple\n\n')
    raise

# This function stores a tweet to a CouchDB database
def store_tweet ( tweet, database ):
  # Store the serialisable JSON data in a string (tweet is a 'Status' object)
  tweet_str = json.dumps(tweet._json)
  # Decode JSON string
  tweet_doc = json.loads(tweet_str)
  # Store the unique tweet ID as the document _id for CouchDB
  tweet_doc.update({'_id': tweet.id_str})
  # Attempt to save tweet to CouchDB
  try:
    database.save(tweet_doc)
    print ("Tweet " + tweet.id_str + " stored in database " + str(database.name))
  # A ResourceConflict exception is raised if the _id already exists
  except ResourceConflict:
    print ("Tweet " + tweet.id_str + " already exists in database " + str(database.name))
  # A ResourceNotFound exception is raised if the PUT request returns HTTP 404
  except ResourceNotFound:
    print ("Tweet " + tweet.id_str + "store attempt failed... trying again in 5 seconds...")
    # There's no point continuing iterating if tweets aren't being stored, so try again when CouchDB is back
    time.sleep(5)
    store_tweet( tweet, database )
  # If it's an unknown error, continue for now, but warn the user
  except:
    print ("Unexpected error storing tweet " + tweet.id_str + ": " + str(sys.exc_info()[0]))
    pass

""" --------------------------
    Main Program
-------------------------- """
 
# Create a log file
#log_file = open("message.log","w")
#sys.stdout = log_file

# Parse command line arguments
parser = argparse.ArgumentParser(description='')
parser.add_argument('--id', '-i', type=int, default=0, help='The unique node ID: The first node should have an ID of 0')
parser.add_argument('--nodes', '-n', type=int, default=1, help='The total number of harvesting nodes')
parser.add_argument('--couchip', '-c', required=True, help='The IP address of the CouchDB instance')
parser.add_argument('--consumerkey', '-ck', required=True, help='Twitter API Consumer Key')
parser.add_argument('--consumersecret', '-cs', required=True, help='Twitter API Consumer Secret')
parser.add_argument('--tokenkey', '-tk', required=True, help='Twitter Access Token Key')
parser.add_argument('--tokensecret', '-ts', required=True, help='Twitter Access Token Secret')
args = parser.parse_args()

# Initialise Twitter communication
auth = tweepy.OAuthHandler(args.consumerkey, args.consumersecret)
auth.set_access_token(args.tokenkey, args.tokensecret)
try:
  api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)
  # tweepy.API constructor does not seem to throw an exception for OAuth failure
  # Use API.verify_credentials() to validate OAuth instead
  cred = api.verify_credentials()
  print ("OAuth connection with Twitter established through user @" + cred.screen_name + "\n")
except tweepy.TweepError as oauth_error:
  print ("OAuth connection with Twitter could not be established\n\n")
  raise oauth_error
except:
  raise

# Initialise CouchDB communication
db_tweets_str = 'tweets'
db_tweets_etc_str = 'tweets_etc'
try:
  couch = couchdb.Server('http://' + args.couchip + ':5984/')
  print ("Connected to CouchDB server at http://" + args.couchip + ":5984\n")
except:
  print ("Failed to connect to CouchDB server at http://" + args.couchip + ":5984\n\n")
  raise
try:
  db_tweets = couch[db_tweets_str]
  print ("Connected to " + db_tweets_str + " database")
# The python-couchdb documentation says that a PreconditionFailed exception is raised when a DB isn't found
# But in practice it throws a ResourceNotFound exception
except couchdb.ResourceNotFound:
  try:
    db_tweets = couch.create(db_tweets_str)
    print ("Creating new database: " + db_tweets_str)
    """
    Note: This program relies on a view existing in database at /app/_view/users_simple.
    In the future this program should create this view if a new database is created, but the database
    needs to have at least one user in it for the view & program to work.
    """
  except:
    raise
except:
  raise
try:
  db_tweets_etc = couch[db_tweets_etc_str]
  print ("Connected to " + db_tweets_etc_str + " database\n")
# The couchdb documentation says that a PreconditionFailed exception is raised when a DB isn't found
# But in practice it throws a ResourceNotFound exception
except couchdb.ResourceNotFound:
  try:
    db_tweets_etc = couch.create(db_tweets_etc_str)
    print ("Creating new database: " + db_tweets_etc_str + "\n")
  except:
    raise
except:
  raise

# Download list of users from the tweets database
try:
  queue = get_queue(db_tweets)
except:
  raise
queue_len = len(queue)

# While (searching)
j = int(math.floor(queue_len / args.nodes) * args.id)
print ("Starting at position " + str(j) + " in the queue.")
searching = 1
while searching:
  # For each user
  j += 1

  # If the user iterator (j) exceeds a point in the array
  if j > (queue_len - 1):
    # Re-download user queue from tweets database
    try:
      queue = get_queue(db_tweets)
    except:
      raise
    # If the queue has now extended
    if (j <= (len(queue) - 1)):
      # Save a new queue length and continue
      queue_len = len(queue)
    # Otherwise start again at the beginning of the queue
    else:
      j = 0

  # Download the timeline of the user
  try:
    for tweet in tweepy.Cursor(api.user_timeline, id=queue[j]).items():
      # Try access place.name (may not exist and will throw an exception)
      try:
        city = tweet.place.name
        if tweet.place.name == 'Melbourne':
          store_tweet(tweet, db_tweets)
        else:
          store_tweet(tweet, db_tweets_etc)
      except:
        store_tweet(tweet, db_tweets_etc)
    print ("Retrieving tweets for user ID " + str(queue[j]))
  # We don't need to handle for RateLimitError because the Cursor automatically waits on
  except tweepy.TweepError:
    print ("Failed to retrieve tweets for user ID " + str(queue[j]))

  # Download the followers of the user
  try:
    for follower in tweepy.Cursor(api.followers, id=queue[j]).items():
      print ("Retrieving tweets for follower " + str(queue[j]))
      # Download the timeline of the follower
      try:
        for tweet in tweepy.Cursor(api.user_timeline, id=follower.id_str).items():
          # Try access place.name (may not exist and will throw an exception)
          try:
            city = tweet.place.name
            if tweet.place.name == 'Melbourne':
              store_tweet(tweet, db_tweets)
            else:
              store_tweet(tweet, db_tweets_etc)
          except:
            store_tweet(tweet, db_tweets_etc)
            #pass
      # We don't need to handle for RateLimitError because the Cursor automatically waits on
      except tweepy.TweepError:
        print ("Failed to retrieve tweets for follower " + follower.id_str)
  
  # We don't need to handle for RateLimitError because the Cursor automatically waits on
  except tweepy.TweepError:
    print ("Failed to retrieve followers for user ID " + str(queue[j]))

# Close the log file
#log_file.close()