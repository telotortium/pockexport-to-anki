import json
import logging
import os
import os.path
import pocket
import random
import requests
import sys
import time

import importlib.machinery
import importlib.util

from itertools import islice

# Create logger that logs to standard error
logger = logging.getLogger("pockexport-to-anki")
# These 2 lines prevent duplicate log lines.
logger.handlers.clear()
logger.propagate = False
level = os.environ.get("POCKEXPORT_TO_ANKI_LOGLEVEL", logging.INFO)
logger.setLevel(level)

# Create handler that logs to standard error
handler = logging.StreamHandler()
handler.setLevel(level)

# Create formatter and add it to the handler
formatter = logging.Formatter('[%(levelname)8s %(asctime)s - %(name)s] %(message)s')
handler.setFormatter(formatter)

# Add handler to the logger
logger.addHandler(handler)

# Load secrets from pockexport for use by pocket module.
loader = importlib.machinery.SourceFileLoader(
      'secrets', os.path.expanduser('~/.config/pockexport/secrets.py'))
spec = importlib.util.spec_from_loader('secrets', loader)
secrets = importlib.util.module_from_spec(spec)
loader.exec_module(secrets)

ANKI_SUSPENDED_TAG = "anki:suspend"
FAVORITE_TAG = "marked"
anki_url = "http://localhost:8765"
version = 6

def batched(iterable, n):
    "Batch data into tuples of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while batch := tuple(islice(it, n)):
        yield batch

def ankiconnect_request(payload):
   logger.debug("payload = %s", payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   logger.debug("response = %s", response)
   if response['error'] is not None:
      logger.warning("payload %s had response error: %s", payload, response)
   return response

def main():
   payload = {
      "action": "sync",
      "version": version,
   }
   logger.info(payload)
   response = ankiconnect_request(payload)

   with open(sys.argv[1]) as f:
      data = json.load(f)

   deck_name = 'Articles'
   note_type = 'Pocket Article'

   note_ids = set()
   archive_items = set()
   readd_items = set()
   favorite_items = set()
   unfavorite_items = set()
   card_to_time_added = list()
   tag_updated_notes = dict()
   tag_updated_items = dict()
   try:
      nitem = len(data['list'])
      for i, item in enumerate(data['list'].values()):
         logger.debug(f"ITERATION {i}/{nitem}")
         item_id = item['item_id']
         try:
            pocket_tags = set(item['tags'].keys())
         except KeyError:
            pocket_tags = set()
         fields = {
            'item_id': item_id,
            'given_url': item.get('given_url', ''),
            'given_title': item.get('given_title', ''),
            'resolved_url': item.get('resolved_url', ''),
            'resolved_title': item.get('resolved_title', ''),
            'time_added': item.get('time_added', ''),
            'word_count': item.get('word_count', ''),
            'time_to_read': str(item.get('time_to_read', '')),
            'excerpt': item.get('excerpt', ''),
            'authors': ", ".join(
               author['name']
               for author in item.get('authors', dict()).values()),
         }

         response = ankiconnect_request({
            "action": "findNotes",
            "version": version,
            "params": {
               "query": f"item_id:{item_id}",
            },
         })
         notes_existing = response['result']
         note_id = None
         mod_time = 0
         note_last_sync_time = 0
         if notes_existing:
            note_id = notes_existing[0]
            response = ankiconnect_request({
               "action": "notesInfo",
               "version": version,
               "params": {
                  "notes": [note_id],
               },
            })
            note_info = response['result'][0]
            cards = note_info['cards']
            response = ankiconnect_request({
               "action": "cardsModTime",
               "version": version,
               "params": {
                  "cards": cards,
               },
            })
            mod_time = max(x["mod"] for x in response['result'])
            try:
               note_last_sync_time = int(note_info['fields']
                                         ['time_last_synced']['value'])
            except (KeyError, ValueError):
               note_last_sync_time = 0

            response = ankiconnect_request({
               "action": "updateNoteFields",
               "version": version,
               "params": {
                  "note": {
                     "id": note_id,
                     "fields": fields,
                  }
               }
            })

         else:
            payload = {
               "action": "addNote",
               "version": version,
               "params": {
                  "note": {
                     "deckName": deck_name,
                     "modelName": note_type,
                     "fields": fields,
                     "tags": list(pocket_tags),
                  }
               }
            }
            response = json.loads(requests.post(anki_url, json=payload).text)
            if (response['error'] is not None
                   and response['error'] !=
                   "cannot create note because it is a duplicate"):
               logger.warning("payload %s had response error: %s",
                              payload, response)
               continue
            note_id = response['result']

         note_ids.add(note_id)

         response = ankiconnect_request({
            "action": "notesInfo",
            "version": version,
            "params": {
               "notes": [note_id],
            },
         })
         note_info = response['result'][0]
         cards = note_info['cards']
         if cards is None:
            logger.warning(response)
            continue
         note_tags = set(note_info['tags'])
         note_favorited = FAVORITE_TAG in note_tags
         should_favorite = note_favorited
         if note_favorited and item['favorite'] == "0":
            if int(item.get('time_favorited', '0')) > mod_time:
               should_favorite = False
            else:
               should_favorite = True
         elif not note_favorited and item['favorite'] == "1":
            if int(item.get('time_favorited', '0')) > mod_time:
               should_favorite = True
            else:
               should_favorite = False
         note_tags -= {FAVORITE_TAG, ANKI_SUSPENDED_TAG}
         merged_tags = note_tags - {FAVORITE_TAG, ANKI_SUSPENDED_TAG}
         pocket_real_tags = (
               pocket_tags - {FAVORITE_TAG, ANKI_SUSPENDED_TAG})
         if note_tags != pocket_tags:
            # Overwrite `pocket_tags` only if Pocket for sure has not been
            # updated since the last sync. Otherwise, merge `pocket_tags` into
            # the existing note tags.
            if not (mod_time > note_last_sync_time and
                    note_last_sync_time > int(item.get('time_updated', '0'))):
               merged_tags |= pocket_tags
         if should_favorite:
            merged_tags |= {FAVORITE_TAG}
            if item['favorite'] == "0":
               favorite_items |= {item_id}
               unfavorite_items -= {item_id}
         else:
            merged_tags -= {FAVORITE_TAG}
            if item['favorite'] == "1":
               favorite_items -= {item_id}
               unfavorite_items |= {item_id}
         response = ankiconnect_request({
            "action": "cardsInfo",
            "version": version,
            "params": {
               "cards": cards,
            },
         })
         for cardInfo in response['result']:
            # `cardInfo` field meanings taken from
            # https://github.com/ankidroid/Anki-Android/wiki/Database-Structure#cards
            card_reviewed = cardInfo['type'] == 2
            if card_reviewed and item.get('status', '0') == '0':
               archive_items |= {item_id}
            # TODO: uncomment the below if I ever get through my backlog.
            #elif not card_reviewed and item.get('status', '0') == '1':
            #   readd_items |= {item_id}
            # Sync suspended status to tags, mostly for easier viewing in
            # Pocket interface.
            card_new = cardInfo['type'] == 0 and cardInfo['queue'] == 0
            card_suspended = cardInfo['queue'] == -1
            if card_suspended:
               merged_tags |= {ANKI_SUSPENDED_TAG}
               archive_items |= {item_id}
            else:
               merged_tags -= {ANKI_SUSPENDED_TAG}
            if card_new and not card_suspended:
               try:
                  time_added = int(
                        cardInfo['fields']['time_added']['value'])
               except (KeyError, ValueError):
                  time_added = 0
               card_to_time_added.append((cardInfo['cardId'], time_added))
         if merged_tags != note_tags:
            logger.debug(f"tag_updated_notes[{note_id}]: merged_tags {merged_tags} note_tags {note_tags}")
            tag_updated_notes[note_id] = merged_tags
         # FAVORITE_TAG not added to Pocket since Pocket has separate Favorite
         # status.
         if (merged_tags - {FAVORITE_TAG}) != pocket_tags:
            logger.debug(f"tag_updated_items[{item_id}]: merged_tags {merged_tags - {FAVORITE_TAG}} pocket_tags {pocket_tags}")
            tag_updated_items[item_id] = merged_tags - {FAVORITE_TAG}

   except KeyboardInterrupt:
      pass

   BATCH_SIZE = 100
   def pocket_batch(collection, f_per_item, f_commit):
      if collection:
         for batch in batched(collection, BATCH_SIZE):
            for x in batch:
               f_per_item(x)
            f_commit()
   logger.info("Pocket API")
   pocket_client = pocket.Pocket(secrets.consumer_key, secrets.access_token)
   logger.info(f"tag_updated_items: {tag_updated_items}")
   pocket_batch(
         list(tag_updated_items.items()),
         lambda x: print(x) or pocket_client.tags_replace(int(x[0]), ",".join(sorted(x[1]))),
         lambda: pocket_client.commit(),
   )
   logger.info(f"favorite_items: {favorite_items}")
   pocket_batch(
         favorite_items,
         lambda item_id: pocket_client.favorite(int(item_id)),
         lambda: pocket_client.commit(),
   )
   logger.info(f"unfavorite_items: {unfavorite_items}")
   pocket_batch(
         unfavorite_items,
         lambda item_id: pocket_client.unfavorite(int(item_id)),
         lambda: pocket_client.commit(),
   )
   logger.info(f"archive_items: {archive_items}")
   pocket_batch(
         archive_items,
         lambda item_id: pocket_client.archive(int(item_id)),
         lambda: pocket_client.commit(),
   )
   logger.info(f"readd_items: {readd_items}")
   pocket_batch(
         readd_items,
         lambda item_id: pocket_client.readd(int(item_id)),
         lambda: pocket_client.commit(),
   )

   # Adjust new card order - generally I'd like to review the most recent
   # additions to Pocket first, but mix in some older material as well - 70%
   # recent, 30% randomly selected.
   # First sort most recent to least recent time_added.
   card_to_time_added.sort(key=(lambda x: x[1]), reverse=True)
   # Next, shuffle 30% of the entries to random positions.
   for i in range(len(card_to_time_added)-1):
      if random.random() < 0.7:
         continue
      j = random.randint(i, len(card_to_time_added)-1)
      card_to_time_added[i], card_to_time_added[j] = (
         card_to_time_added[j], card_to_time_added[i])
   # Finally, write back to Anki
   import pprint; logger.debug(f"card_to_time_added = {pprint.pformat(card_to_time_added)}")
   due = 0
   for batch in batched(card_to_time_added, BATCH_SIZE):
      actions = []
      for card_id, time_added in batch:
         actions.append({
            "action": "setSpecificValueOfCard",
            "params": {
               "card": card_id,
               "keys": ["due"],
               "newValues": [due],
            },
         })
         due += 1

      response = ankiconnect_request({
         "action": "multi",
         "version": version,
         "params": {"actions": actions},
      })

   payload = {
      "action": "findCards",
      "version": version,
      "params": {
         "query": 'deck:Articles note:"Pocket article" is:new -is:suspended',
      }
   }
   logger.info(payload)

   # script_sync_time has to be updated at the end so that we can tell if
   # Pocket was updated *after* this script ran, which is important for tags.
   script_sync_time = int(time.time())
   if note_ids:
      for batch in batched(note_ids, BATCH_SIZE):
         actions = []
         for note_id in batch:
            actions.append({
               "action": "updateNoteFields",
               "params": {
                  "note": {
                     "id": note_id,
                     "fields": {
                        "time_last_synced": str(script_sync_time),
                     },
                  },
               },
            })
            if note_id in tag_updated_notes:
               actions.append({
                  "action": "updateNoteTags",
                  "params": {
                     "note": note_id,
                     "tags": list(tag_updated_notes[note_id]),
                  },
               })

         response = ankiconnect_request({
            "action": "multi",
            "version": version,
            "params": {"actions": actions},
         })

   payload = {
      "action": "sync",
      "version": version,
   }
   logger.info(payload)
   response = ankiconnect_request(payload)
