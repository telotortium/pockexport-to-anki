import json
import logging
import os
import os.path
import pocket
import requests
import sys

import importlib.machinery
import importlib.util

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

anki_url = "http://localhost:8765"
version = 6

def ankiconnect_request(payload):
   logger.debug("payload = %s", payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   logger.debug("response = %s", response)
   if response['error'] is not None:
      logger.warning("payload %s had response error: %s", payload, response)
   return response

def main():
   with open(sys.argv[1]) as f:
      data = json.load(f)

   deck_name = 'Articles'
   note_type = 'Pocket Article'

   suspend_cards = set()
   unsuspend_cards = set()
   suspend_items = set()
   unsuspend_items = set()
   archive_items = set()
   readd_items = set()
   favorite_items = set()
   marked_notes = set()
   unfavorite_items = set()
   unmarked_notes = set()
   tag_updated_items = dict()
   try:
      for item in data['list'].values():
         item_id = item['item_id']
         try:
            pocket_tags = list(item['tags'].keys())
         except KeyError:
            pocket_tags = []
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
         if notes_existing:
            note_id = notes_existing[0]
            response = ankiconnect_request({
               "action": "findCards",
               "version": version,
               "params": {
                  "query": f"nid:{note_id}",
               },
            })
            cards = response['result']
            response = ankiconnect_request({
               "action": "cardsModTime",
               "version": version,
               "params": {
                  "cards": cards,
               },
            })
            mod_time = max(x["mod"] for x in response['result'])

            response = ankiconnect_request({
               "action": "getNoteTags",
               "version": version,
               "params": {
                  "note": note_id,
               },
            })

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
                     "tags": pocket_tags,
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

         response = ankiconnect_request({
            "action": "notesInfo",
            "version": version,
            "params": {
               "notes": [note_id],
            },
         })
         note_info = response['result'][0]
         note_tags = set(note_info['tags'])
         note_favorited = "marked" in note_tags
         should_favorite = note_favorited
         if note_favorited and item['favorite'] == "0":
            if int(item.get('time_favorited', '0')) > mod_time:
               unmarked_notes |= {note_id}
            else:
               favorite_items |= {item_id}
               should_favorite = True
         elif not note_favorited and item['favorite'] == "1":
            if int(item.get('time_favorited', '0')) > mod_time:
               marked_notes |= {note_id}
               should_favorite = True
            else:
               unfavorite_items |= {item_id}
         note_tags -= {"marked"}
         if note_tags != set(pocket_tags):
            if mod_time >= int(item.get('time_updated', '0')):
               tag_updated_items[item_id] = list(note_tags)
            else:
               response = ankiconnect_request({
                  "action": "updateNoteTags",
                  "version": version,
                  "params": {
                     "note": note_id,
                     "tags": list(note_tags) + (
                        ["marked"] if should_favorite else []),
                  },
               })

         response = ankiconnect_request({
            "action": "findCards",
            "version": version,
            "params": {
               "query": f"item_id:{item_id}",
            },
         })
         cards = response['result']
         if cards is None:
            logging.warning(response)
            continue
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
            cardReviewed = cardInfo['type'] == 2
            if cardReviewed and item.get('status', '0') == '0':
               archive_items |= {item_id}
            # TODO: uncomment the below if I ever get through my backlog.
            #elif not cardReviewed and item.get('status', '0') == '1':
            #   readd_items |= {item_id}
            cardSuspended = cardInfo['queue'] == -1
            if mod_time >= int(item.get('time_updated', '0')):
               if 'anki:suspended' in pocket_tags and not cardSuspended:
                  unsuspend_items.add(item_id)
               elif 'anki:suspended' not in note_tags and cardSuspended:
                  suspend_items.add(item_id)
            else:
               if 'anki:suspended' in pocket_tags and not cardSuspended:
                  suspend_cards.add(cardInfo['cardId'])
               elif 'anki:suspended' not in note_tags and cardSuspended:
                  unsuspend_cards.add(cardInfo['cardId'])
   except KeyboardInterrupt:
      pass

   payload = {
      "action": "suspend",
      "version": version,
      "params": {
         "cards": list(suspend_cards),
      },
   }
   logger.info(payload)
   response = ankiconnect_request(payload)
   payload = {
      "action": "unsuspend",
      "version": version,
      "params": {
         "cards": list(unsuspend_cards),
      },
   }
   logger.info(payload)
   response = ankiconnect_request(payload)

   payload = {
      "action": "addTags",
      "version": version,
      "params": {
         "notes": list(marked_notes),
         "tags": "marked",
      },
   }
   logger.info(payload)
   response = ankiconnect_request(payload)
   payload = {
      "action": "removeTags",
      "version": version,
      "params": {
         "notes": list(unmarked_notes),
         "tags": "marked",
      },
   }
   logger.info(payload)
   response = ankiconnect_request(payload)

   payload = {
      "action": "sync",
      "version": version,
   }
   logger.info(payload)
   response = ankiconnect_request(payload)

   logger.info("Pocket API")
   pocket_client = pocket.Pocket(secrets.consumer_key, secrets.access_token)
   logger.info(f"tag_updated_items: {tag_updated_items}")
   if tag_updated_items:
      for item_id, tags in tag_updated_items.items():
         pocket_client.tags_replace(int(item_id), ",".join(sorted(tags)))
      pocket_client.commit()
   logger.info(f"suspend_items: {suspend_items}")
   if suspend_items:
      for item_id in suspend_items:
         pocket_client.tags_add(int(item_id), "anki:suspend")
      pocket_client.commit()
   logger.info(f"unsuspend_items: {unsuspend_items}")
   if unsuspend_items:
      for item_id in unsuspend_items:
         pocket_client.tags_remove(int(item_id), "anki:suspend")
      pocket_client.commit()
   logger.info(f"favorite_items: {favorite_items}")
   if favorite_items:
      for item_id in favorite_items:
         pocket_client.favorite(int(item_id))
      pocket_client.commit()
   logger.info(f"unfavorite_items: {unfavorite_items}")
   if unfavorite_items:
      for item_id in unfavorite_items:
         pocket_client.unfavorite(int(item_id))
      pocket_client.commit()
   logger.info(f"archive_items: {archive_items}")
   if archive_items:
      for item_id in archive_items:
         pocket_client.archive(int(item_id))
      pocket_client.commit()
   logger.info(f"readd_items: {readd_items}")
   if readd_items:
      for item_id in readd_items:
         pocket_client.readd(int(item_id))
      pocket_client.commit()
